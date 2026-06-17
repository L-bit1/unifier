from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.services.devices import connectivity_report, parse_expected_devices
from app.services.feishu_projects import FeishuReply, build_projects_reply, select_project_by_query
from app.services.feishu_sessions import format_current_project
from app.services.orchestrate import command_status, dispatch_command


DISPATCH_PREFIXES = ("派活", "/task", "/dispatch")
SOUL_PREFIXES = ("灵魂", "/soul", "问灵魂", "soul:")
REPLY_PREFIXES = ("回复", "/reply")
STATUS_PREFIXES = ("状态", "/status")
CONNECT_PREFIXES = ("联通", "/connectivity", "在线")
STACK_PREFIXES = ("套件", "/stack", "灵魂栈", "四项目健康", "栈")
AUTOMATION_PREFIXES = ("自动化", "/automation", "n8n")
SLOT_PREFIXES = ("选配", "/slots", "阵容")
PROJECT_PREFIXES = ("项目", "/projects", "项目列表")
SELECT_PREFIXES = ("选", "/select", "选择")
CURRENT_PREFIXES = ("当前项目", "/current", "当前仓库")


def _strip_bot_mention(text: str) -> str:
    return re.sub(r"@_user_\d+|@\S+", "", text).strip()


def _starts_with_any(text: str, prefixes: tuple[str, ...]) -> bool:
    raw = _strip_bot_mention(text).strip()
    return any(raw.startswith(p) for p in prefixes)


def _parse_soul_message(text: str) -> str | None:
    raw = _strip_bot_mention(text).strip()
    for prefix in SOUL_PREFIXES:
        if raw.startswith(prefix):
            msg = raw[len(prefix) :].lstrip(":： ").strip()
            return msg or None
    return None


def _parse_dispatch(
    text: str,
    *,
    chat_id: str | None,
    db: Session,
) -> dict[str, str] | None:
    raw = _strip_bot_mention(text).strip()
    for prefix in DISPATCH_PREFIXES:
        if raw.startswith(prefix):
            raw = raw[len(prefix) :].lstrip(":： ").strip()
            break
    else:
        if not raw or raw.startswith("/"):
            return None
        blocked = (
            REPLY_PREFIXES
            + STATUS_PREFIXES
            + CONNECT_PREFIXES
            + SLOT_PREFIXES
            + PROJECT_PREFIXES
            + SELECT_PREFIXES
            + CURRENT_PREFIXES
            + SOUL_PREFIXES
            + STACK_PREFIXES
            + AUTOMATION_PREFIXES
        )
        if any(raw.startswith(p) for p in blocked):
            return None

    github_owner = settings.feishu_default_github_owner
    github_repo = settings.feishu_default_github_repo

    if chat_id:
        from app.services.feishu_sessions import get_chat_session

        session = get_chat_session(db, chat_id)
        if session:
            github_owner = session.github_owner
            github_repo = session.github_repo

    branch = f"feature/{re.sub(r'[^a-zA-Z0-9_-]+', '-', raw)[:40].strip('-') or 'task'}"

    repo_match = re.match(
        r"^(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)\s+(?P<body>.+)$",
        raw,
    )
    if repo_match:
        github_owner = repo_match.group("owner")
        github_repo = repo_match.group("repo")
        raw = repo_match.group("body").strip()

    if "|" in raw:
        title, branch_part = [p.strip() for p in raw.split("|", 1)]
        if branch_part:
            branch = branch_part
    else:
        title = raw

    if not title:
        return None
    if not github_owner or not github_repo:
        return {"needs_project": True, "title": title, "branch": branch}
    return {
        "github_owner": github_owner,
        "github_repo": github_repo,
        "title": title,
        "branch": branch,
    }


def _parse_reply(text: str) -> tuple[int, str, str, str] | None:
    raw = _strip_bot_mention(text).strip()
    for prefix in REPLY_PREFIXES:
        if raw.startswith(prefix):
            raw = raw[len(prefix) :].lstrip(":： ").strip()
            break
    else:
        return None

    lines = raw.splitlines()
    head = lines[0].strip()
    m = re.match(
        r"(?P<task_id>\d+)\s+(?P<device>[\w-]+)\s+(?P<agent>cursor|trae)\s*(?P<rest>.*)?",
        head,
        re.I,
    )
    if not m:
        m2 = re.match(r"(?P<task_id>\d+)\s*(?P<rest>.*)?", head)
        if not m2:
            return None
        content = "\n".join([m2.group("rest") or ""] + lines[1:]).strip()
        return int(m2.group("task_id")), "", "cursor", content

    content = "\n".join([m.group("rest") or ""] + lines[1:]).strip()
    return (
        int(m.group("task_id")),
        m.group("device"),
        m.group("agent").lower(),
        content,
    )


def _parse_status(text: str) -> int | None:
    raw = _strip_bot_mention(text).strip()
    for prefix in STATUS_PREFIXES:
        if raw.startswith(prefix):
            raw = raw[len(prefix) :].lstrip(":： #").strip()
            break
    else:
        return None
    m = re.search(r"\d+", raw)
    return int(m.group()) if m else None


def _parse_select_query(text: str) -> str | None:
    raw = _strip_bot_mention(text).strip()
    for prefix in SELECT_PREFIXES:
        if raw.startswith(prefix):
            raw = raw[len(prefix) :].lstrip(":： ").strip()
            break
    else:
        return None
    return raw or None


def _handle_slot_command(db: Session, content: str) -> str | None:
    from app.services.agent_slots import format_slots_message, update_slot

    raw = _strip_bot_mention(content).strip()
    for prefix in SLOT_PREFIXES:
        if raw.startswith(prefix):
            raw = raw[len(prefix) :].lstrip(":： ").strip()
            break
    else:
        return None

    if not raw or raw.lower() in ("列表", "list"):
        return format_slots_message(db)

    m = re.match(
        r"^(?:(执行|审查)\s+)?(on|off|开|关)\s+(?P<device>[\w-]+)\s+(?P<agent>cursor|trae)\s*$",
        raw,
        re.I,
    )
    if not m:
        return format_slots_message(db) + "\n\n格式：选配 off device-b trae · 选配 执行 off device-a trae"

    role = m.group(1)
    on = m.group(2).lower() in ("on", "开")
    device_id = m.group("device")
    agent_id = m.group("agent").lower()

    try:
        if role is None:
            if on:
                update_slot(
                    db,
                    device_id,
                    agent_id,
                    enabled=True,
                    can_implement=True,
                    can_review=True,
                )
            else:
                update_slot(db, device_id, agent_id, enabled=False)
        elif role == "执行":
            update_slot(db, device_id, agent_id, enabled=True, can_implement=on)
        else:
            update_slot(db, device_id, agent_id, enabled=True, can_review=on)
    except Exception as e:
        return f"选配失败：{e}"

    return format_slots_message(db)


def handle_im_message_event(db: Session, event: dict[str, Any]) -> FeishuReply | None:
    """处理 compact 格式的 im.message.receive_v1 事件。"""
    if event.get("type") and event.get("type") != "im.message.receive_v1":
        return None

    chat_id = event.get("chat_id")
    message_id = event.get("message_id")
    message_type = event.get("message_type", "text")
    content = (event.get("content") or "").strip()
    sender_type = event.get("sender_type") or event.get("sender", {}).get("sender_type")

    if sender_type == "bot":
        return None
    if message_type != "text" or not content or not chat_id:
        return None

    slot_reply = _handle_slot_command(db, content)
    if slot_reply is not None:
        return FeishuReply(text=slot_reply)

    if _starts_with_any(content, PROJECT_PREFIXES):
        return build_projects_reply(db, chat_id)

    if _starts_with_any(content, CURRENT_PREFIXES):
        return FeishuReply(text=format_current_project(db, chat_id))

    select_query = _parse_select_query(content)
    if select_query is not None:
        return select_project_by_query(db, chat_id, select_query)

    if any(content.startswith(p) for p in CONNECT_PREFIXES):
        from app.models import Device

        report = connectivity_report(
            db.query(Device).order_by(Device.device_id).all(),
            expected_device_ids=parse_expected_devices(),
        )
        from app.services.devices import format_connectivity_message

        return FeishuReply(text="📡 设备联通性\n" + format_connectivity_message(report))

    if any(content.strip().startswith(p) for p in AUTOMATION_PREFIXES):
        from app.services.n8n_bridge import n8n_health_sync

        n8n = n8n_health_sync()
        lines = [
            "⚙️ n8n 自动化",
            f"启用: {'是' if n8n.get('enabled') else '否'}",
            f"状态: {'✅ 在线' if n8n.get('ok') else '❌ 离线/未启用'}",
            f"面板: {n8n.get('url', settings.n8n_url)}",
        ]
        if settings.n8n_webhook_url:
            lines.append(f"Webhook: {settings.n8n_webhook_url}")
        lines.append("\n在 n8n 中导入 hub/workflows/ 预置流后，Hub 任务事件会自动推送。")
        return FeishuReply(text="\n".join(lines))

    if any(content.strip().startswith(p) for p in STACK_PREFIXES):
        from app.services.n8n_bridge import n8n_health_sync
        from app.services.soul_bridge import stack_health_sync

        stack = stack_health_sync()
        n8n = n8n_health_sync()
        lines = [
            f"📦 Head 套件 · {stack.get('overall', '?')}",
            f"session: {stack.get('session_id')}",
        ]
        for name, comp in (stack.get("components") or {}).items():
            ok = "✅" if comp.get("ok") else "❌"
            lines.append(f"{ok} {name}: {comp.get('url') or comp.get('error', '')}")
        if settings.n8n_enabled:
            ok = "✅" if n8n.get("ok") else "❌"
            lines.append(f"{ok} n8n_automation: {n8n.get('url')}")
        return FeishuReply(text="\n".join(lines))

    soul_msg = _parse_soul_message(content)
    if soul_msg is not None:
        from app.services.soul_bridge import soul_chat_sync

        result = soul_chat_sync(message=soul_msg)
        if result.get("ok"):
            reply = (result.get("reply") or "").strip() or "(空回复)"
            if len(reply) > 3500:
                reply = reply[:3500] + "…"
            return FeishuReply(text=f"🧠 自研AI\n{reply}")
        return FeishuReply(
            text=f"灵魂层不可用: {result.get('detail') or result.get('error') or result.get('http_status')}"
        )

    task_id = _parse_status(content)
    if task_id is not None:
        from app.models import Task

        task = db.get(Task, task_id)
        if not task:
            return FeishuReply(text=f"任务 #{task_id} 不存在")
        status = command_status(task, db)
        return FeishuReply(text="📋 任务状态\n" + status["message"])

    reply_parsed = _parse_reply(content)
    if reply_parsed:
        from app.services.agent_replies import submit_agent_reply

        tid, device_id, agent_id, body = reply_parsed
        if not body:
            return FeishuReply(text="回复格式：回复 任务ID 设备 agent\n内容...")
        if not device_id:
            device_id = settings.feishu_default_implementer_device
        try:
            submit_agent_reply(db, tid, device_id, agent_id, body, source="feishu")
            return FeishuReply(text=f"已转发 {device_id}/{agent_id} 的回复到群")
        except ValueError as e:
            return FeishuReply(text=str(e))

    parsed = _parse_dispatch(content, chat_id=chat_id, db=db)
    if not parsed:
        return None

    if parsed.get("needs_project"):
        return FeishuReply(
            text="请先选择项目：发送「项目」打开卡片，或「选 项目名 / 选 owner/repo」。"
        )

    from app.services.agent_slots import resolve_dispatch_roles

    try:
        impl_d, impl_a, reviewers = resolve_dispatch_roles(db)
        task, _project = dispatch_command(
            db,
            github_owner=parsed["github_owner"],
            github_repo=parsed["github_repo"],
            title=parsed["title"],
            description=f"来自飞书群 {chat_id}",
            branch=parsed["branch"],
            implementer_device_id=impl_d,
            implementer_agent_id=impl_a,
            required_reviewers=reviewers,
            feishu_chat_id=chat_id,
            feishu_message_id=message_id,
        )
    except ValueError as e:
        return FeishuReply(text=f"派活失败：{e}")

    status = command_status(task, db)
    repo_label = f"{parsed['github_owner']}/{parsed['github_repo']}"
    from app.services.event_bus import emit_event

    emit_event("task.dispatched", task=task, db=db)
    return FeishuReply(
        text="✅ 任务已创建\n"
        + f"项目：{repo_label}\n"
        + status["message"]
    )
