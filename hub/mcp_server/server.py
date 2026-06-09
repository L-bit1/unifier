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
你是联合器协作控制面的 MCP 工具集。典型流程：
1. unifier_get_my_inbox — 查看本机待执行/待审查任务
2. 在 IDE 内完成代码或审查
3. unifier_submit_manifest / unifier_submit_review_vote — 上报进度
4. unifier_submit_agent_reply — 把 AI 回复摘要发回飞书群
5. unifier_get_task_status / unifier_check_merge_ready — 查进度

环境变量 UNIFIER_DEVICE_ID、UNIFIER_AGENT_ID 标识本机身份（如 mac-a + cursor）。
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
    submit_device: str = "",
    submit_agent: str = "",
) -> str:
    """执行者提交 ChangeManifest（改动摘要）。"""
    d = submit_device or device_id()
    a = submit_agent or agent_id()
    if not d:
        raise ValueError("请设置 UNIFIER_DEVICE_ID 或传入 submit_device")
    return pretty(
        request(
            "POST",
            f"/api/v1/tasks/{task_id}/manifest",
            json_body={
                "agent_id": a,
                "device_id": d,
                "payload": {"summary": summary, "files": []},
            },
        )
    )


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


if __name__ == "__main__":
    mcp.run(transport="stdio")
