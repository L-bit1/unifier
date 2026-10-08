#!/usr/bin/env python3
"""联合器 MCP Server：供 Cursor / Trae 调用 Hub（派活、收件箱、回复飞书、选配等）。"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from mcp_server.hub_client import (
    agent_id,
    device_id,
    hub_url,
    pretty,
    request,
    reviewer_id,
)

INSTRUCTIONS = """
你是联合器协作控制面的 MCP 工具集。

【圆桌对话】（Cursor ↔ Trae 同场互读，优先于派活任务）
1. unifier_dialogue_list_open — 看是否有 open 房间
2. unifier_dialogue_poll — 拉新消息；看 my_turn / hint
3. 若 my_turn=true → unifier_dialogue_reply（本轮每人最多一条）
4. 若 my_turn=false → 只简短说明「等待对方」，禁止长文假装已读
5. 用户结束房间后可用 transcript 复盘

【任务派活】（旧流程，仍可用）
1. unifier_get_my_inbox → 执行/审查
2. unifier_submit_manifest / unifier_submit_review_vote
3. unifier_submit_agent_reply → 飞书

环境变量 UNIFIER_DEVICE_ID、UNIFIER_AGENT_ID 标识本机身份（如 mac-a + cursor）。
圆桌里的 participant 默认等于 UNIFIER_AGENT_ID（cursor / trae）。
""".strip()

mcp = FastMCP(
    "联合器",
    instructions=INSTRUCTIONS,
)


@mcp.tool()
def unifier_hub_health() -> str:
    """检查联合器 Hub 是否在线。"""
    return pretty(request("GET", "/health"))


@mcp.tool()
def unifier_check_connectivity(expected_devices: str = "") -> str:
    """检查期望设备是否在线、可否派活。"""
    return pretty(
        request("GET", "/api/v1/devices/connectivity", params={"expected": expected_devices})
    )


@mcp.tool()
def unifier_list_agent_slots() -> str:
    """查看各设备 cursor/trae 选配（参与/不参与、执行/审查）。"""
    data = request("GET", "/api/v1/agent-slots")
    return data.get("message", pretty(data))


@mcp.tool()
def unifier_set_agent_slot(
    device: str,
    agent: str,
    enabled: bool | None = None,
    can_implement: bool | None = None,
    can_review: bool | None = None,
) -> str:
    """选配：开启/关闭某台设备的 cursor 或 trae。enabled=false 为完全不参与。"""
    body: dict[str, bool] = {}
    if enabled is not None:
        body["enabled"] = enabled
    if can_implement is not None:
        body["can_implement"] = can_implement
    if can_review is not None:
        body["can_review"] = can_review
    if not body:
        raise ValueError("至少指定 enabled / can_implement / can_review 之一")
    return pretty(
        request("PATCH", f"/api/v1/agent-slots/{device}/{agent}", json_body=body)
    )


@mcp.tool()
def unifier_get_my_inbox() -> str:
    """获取本机当前 Agent 的收件箱（待执行 work / 待审查 review）。"""
    d, a = device_id(), agent_id()
    if not d:
        raise ValueError("请设置环境变量 UNIFIER_DEVICE_ID（或 DEVICE_ID）")
    return pretty(
        request("GET", "/api/v1/tasks/inbox", params={"device_id": d, "agent_id": a})
    )


@mcp.tool()
def unifier_dispatch_task(
    title: str,
    branch: str = "",
    github_owner: str = "",
    github_repo: str = "",
    implementer_device: str = "",
    implementer_agent: str = "",
    require_connectivity: bool = True,
) -> str:
    """创建并派发任务（等同飞书「派活」）。branch 可空则 Hub 使用默认规则。"""
    body: dict = {
        "title": title,
        "branch": branch or f"feature/auto-{title[:24]}",
        "github_owner": github_owner or "your-org",
        "github_repo": github_repo or "your-repo",
        "implementer_device_id": implementer_device or device_id() or "",
        "implementer_agent_id": implementer_agent or agent_id(),
        "required_reviewers": [],
        "require_connectivity": require_connectivity,
    }
    data = request("POST", "/api/v1/orchestrate/dispatch", json_body=body)
    return data.get("message", pretty(data))


@mcp.tool()
def unifier_get_task_status(task_id: int) -> str:
    """查询任务状态与审查进度（等同飞书「状态 N」）。"""
    data = request("GET", f"/api/v1/orchestrate/tasks/{task_id}/status")
    return data.get("message", pretty(data))


@mcp.tool()
def unifier_check_merge_ready(task_id: int) -> str:
    """检查任务是否审查全票通过、允许去 GitHub merge。"""
    return pretty(request("GET", f"/api/v1/tasks/{task_id}/merge-ready"))


@mcp.tool()
def unifier_submit_manifest(
    task_id: int,
    summary: str,
    intent: str = "",
    cot_summary: str = "",
    feishu_message_id: str = "",
    submit_device: str = "",
    submit_agent: str = "",
) -> str:
    """执行者提交 ChangeManifest（改动摘要 + 意图记忆）。"""
    d = submit_device or device_id()
    a = submit_agent or agent_id()
    if not d:
        raise ValueError("请设置 UNIFIER_DEVICE_ID 或传入 submit_device")
    body: dict = {
        "agent_id": a,
        "device_id": d,
        "payload": {"summary": summary, "files": []},
    }
    if intent.strip():
        body["intent"] = intent.strip()
    if cot_summary.strip():
        body["cot_summary"] = cot_summary.strip()
    if feishu_message_id.strip():
        body["feishu_message_id"] = feishu_message_id.strip()
    return pretty(
        request(
            "POST",
            f"/api/v1/tasks/{task_id}/manifest",
            json_body=body,
        )
    )


@mcp.tool()
def unifier_search_manifest_intent(query: str = "", channel: str = "", limit: int = 20) -> str:
    """检索 ChangeManifest 意图记忆（审计 / 复盘）。"""
    params: dict = {"limit": limit}
    if query.strip():
        params["q"] = query.strip()
    if channel.strip():
        params["channel"] = channel.strip()
    return pretty(request("GET", "/api/v1/audit/manifests", params=params))


@mcp.tool()
def unifier_submit_for_review(task_id: int) -> str:
    """执行者完成改动后，将任务提交进入审查流程。"""
    return pretty(request("POST", f"/api/v1/tasks/{task_id}/submit-review"))


@mcp.tool()
def unifier_submit_review_vote(
    task_id: int,
    status: str = "approved",
    note: str = "",
    reviewer: str = "",
) -> str:
    """审查者投票：status 为 approved 或 changes_requested。"""
    rid = reviewer or reviewer_id()
    body: dict = {"reviewer_agent_id": rid, "status": status}
    if note:
        body["note"] = note
    return pretty(request("POST", f"/api/v1/tasks/{task_id}/reviews", json_body=body))


@mcp.tool()
def unifier_submit_agent_reply(
    task_id: int,
    content: str,
    reply_device: str = "",
    reply_agent: str = "",
) -> str:
    """将 Cursor/Trae 的回复内容上报 Hub 并转发到飞书群。"""
    d = reply_device or device_id()
    a = reply_agent or agent_id()
    if not d:
        raise ValueError("请设置 UNIFIER_DEVICE_ID 或传入 reply_device")
    data = request(
        "POST",
        f"/api/v1/tasks/{task_id}/agent-replies",
        json_body={
            "device_id": d,
            "agent_id": a,
            "content": content,
            "source": "mcp",
            "notify_feishu": True,
        },
    )
    return f"已上报并推送飞书\n{pretty(data)}"


@mcp.tool()
def unifier_heartbeat() -> str:
    """向 Hub 发送本机心跳（保持在线）。"""
    d = device_id()
    if not d:
        raise ValueError("请设置 UNIFIER_DEVICE_ID")
    return pretty(request("POST", f"/api/v1/devices/{d}/heartbeat"))


@mcp.tool()
def unifier_whoami() -> str:
    """返回当前 MCP 配置的本机身份与 Hub 地址。"""
    return pretty(
        {
            "hub_url": hub_url(),
            "device_id": device_id() or "(未设置)",
            "agent_id": agent_id(),
            "reviewer_id": reviewer_id(),
        }
    )


# ----- 圆桌对话 -----


@mcp.tool()
def unifier_dialogue_open(
    topic: str,
    title: str = "",
    project_key: str = "maotai",
    participants: str = "cursor,trae",
) -> str:
    """开圆桌：用户抛出话题。participants 逗号分隔，默认 cursor,trae。"""
    parts = [p.strip() for p in participants.split(",") if p.strip()]
    return pretty(
        request(
            "POST",
            "/api/v1/dialogue/rooms",
            json_body={
                "title": title or topic[:80],
                "topic": topic,
                "project_key": project_key,
                "participants": parts or ["cursor", "trae"],
            },
        )
    )


@mcp.tool()
def unifier_dialogue_list_open(project_key: str = "maotai") -> str:
    """仅列出 status=open 的圆桌。若为空，请用 unifier_dialogue_list(open_only=false) 看历史房。"""
    return pretty(
        request(
            "GET",
            "/api/v1/dialogue/rooms",
            params={"project_key": project_key, "open_only": "true"},
        )
    )


@mcp.tool()
def unifier_dialogue_list(project_key: str = "maotai", open_only: bool = False) -> str:
    """列出圆桌。open_only=false（默认）含已结束房间，便于调取历史对话框。"""
    return pretty(
        request(
            "GET",
            "/api/v1/dialogue/rooms",
            params={
                "project_key": project_key,
                "open_only": "true" if open_only else "false",
            },
        )
    )


@mcp.tool()
def unifier_dialogue_poll(room_id: int, since_id: int = 0, as_participant: str = "") -> str:
    """拉圆桌状态：my_turn / waiting_for / 对方新消息 / transcript_tail。
    as_participant 空则用 UNIFIER_AGENT_ID。未轮到你时勿输出长文。"""
    who = (as_participant or agent_id()).strip().lower()
    return pretty(
        request(
            "GET",
            f"/api/v1/dialogue/rooms/{room_id}/poll",
            params={"participant": who, "since_id": since_id},
        )
    )


@mcp.tool()
def unifier_dialogue_reply(
    room_id: int,
    body: str,
    as_participant: str = "",
) -> str:
    """本轮发言（每人每轮最多一条）。as_participant 空则用 UNIFIER_AGENT_ID。"""
    who = (as_participant or agent_id()).strip().lower()
    return pretty(
        request(
            "POST",
            f"/api/v1/dialogue/rooms/{room_id}/reply",
            json_body={"participant": who, "body": body},
        )
    )


@mcp.tool()
def unifier_dialogue_user_message(room_id: int, body: str) -> str:
    """用户追问 / 开新一轮话题（推进 round）。"""
    return pretty(
        request(
            "POST",
            f"/api/v1/dialogue/rooms/{room_id}/user-message",
            json_body={"body": body},
        )
    )


@mcp.tool()
def unifier_dialogue_end(room_id: int) -> str:
    """结束圆桌并落盘 transcript。"""
    return pretty(request("POST", f"/api/v1/dialogue/rooms/{room_id}/end"))


@mcp.tool()
def unifier_dialogue_reopen(room_id: int, note: str = "") -> str:
    """重新打开已结束的圆桌，进入新一轮；可带追问 note。"""
    body = {"body": note} if note.strip() else {"body": f"继续房间 #{room_id}"}
    return pretty(
        request("POST", f"/api/v1/dialogue/rooms/{room_id}/reopen", json_body=body)
    )


@mcp.tool()
def unifier_dialogue_transcript(room_id: int) -> str:
    """拉取圆桌全文（含已结束房间）。"""
    return pretty(request("GET", f"/api/v1/dialogue/rooms/{room_id}/transcript"))


if __name__ == "__main__":
    mcp.run(transport="stdio")
