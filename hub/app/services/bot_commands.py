from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.services.devices import connectivity_report, format_connectivity_message, parse_expected_devices
from app.services.feishu_cards import build_project_picker_card
from app.services.feishu_projects import FeishuReply, select_project_by_query
from app.services.feishu_sessions import format_current_project
from app.services.orchestrate import command_status, dispatch_command

DISPATCH_PREFIXES = ("派活", "/task", "/dispatch")
SOUL_PREFIXES = ("灵魂", "/soul", "问灵魂", "soul:")
REPLY_PREFIXES = ("回复", "/reply")
STATUS_PREFIXES = ("状态", "/status")
CONNECT_PREFIXES = ("联通", "/connectivity", "在线")
STACK_PREFIXES = ("套件", "/stack", "灵魂栈", "四项目健康", "栈")
AUTOMATION_PREFIXES = ("自动化", "/automation", "工作流", "/workflows")
SLOT_PREFIXES = ("选配", "/slots", "阵容")
PROJECT_PREFIXES = ("项目", "/projects", "项目列表")
SELECT_PREFIXES = ("选", "/select", "选择")
CURRENT_PREFIXES = ("当前项目", "/current", "当前仓库")
CONFIRM_PREFIXES = ("确认执行", "/confirm", "确认")
DEFER_PREFIXES = ("稍后", "/defer", "晚点执行")
HELP_PREFIXES = ("帮助", "/help", "指令", "命令")


@dataclass
class BotReply:
    text: str
    card: dict | None = None
    projects: list[dict[str, Any]] = field(default_factory=list)
    task_id: int | None = None
    kind: str = "text"

    def to_feishu(self) -> FeishuReply:
        return FeishuReply(text=self.text, card=self.card)

    def to_mobile(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "kind": self.kind,
            "task_id": self.task_id,
            "projects": self.projects,
        }


def _strip_mention(text: str) -> str:
    return re.sub(r"@_user_\d+|@\S+", "", text).strip()


def _starts_with_any(text: str, prefixes: tuple[str, ...]) -> bool:
    raw = _strip_mention(text).strip()
    return any(raw.startswith(p) for p in prefixes)


def _parse_soul_message(text: str) -> str | None:
    raw = _strip_mention(text).strip()
    for prefix in SOUL_PREFIXES:
        if raw.startswith(prefix):
            msg = raw[len(prefix) :].lstrip(":： ").strip()
            return msg or None
    return None


def _parse_dispatch(text: str, *, session_id: str, db: Session) -> dict[str, str] | None:
    raw = _strip_mention(text).strip()
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
            + HELP_PREFIXES
            + CONFIRM_PREFIXES
            + DEFER_PREFIXES
        )
        if any(raw.startswith(p) for p in blocked):
            return None

    github_owner = settings.feishu_default_github_owner
    github_repo = settings.feishu_default_github_repo

    from app.services.feishu_sessions import get_chat_session

    session = get_chat_session(db, session_id)
    if session:
        github_owner = session.github_owner
        github_repo = session.github_repo

    branch = f"feature/{re.sub(r'[^a-zA-Z0-9_-]+', '-', raw)[:40].strip('-') or 'task'}"

    repo_match = re.match(r"^(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)\s+(?P<body>.+)$", raw)
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
    raw = _strip_mention(text).strip()
    for prefix in REPLY_PREFIXES:
        if raw.startswith(prefix):
            raw = raw[len(prefix) :].lstrip(":： ").strip()
            break
    else:
        return None

    lines = raw.splitlines()
    head = lines[0].strip()
    m = re.match(
        r"(?P<task_id>\d+)\s+(?P<device>[\w-]+)\s+(?P<agent>cursor|trae|dsh)\s*(?P<rest>.*)?",
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
    return int(m.group("task_id")), m.group("device"), m.group("agent").lower(), content


def _parse_status(text: str) -> int | None:
    raw = _strip_mention(text).strip()
    for prefix in STATUS_PREFIXES:
        if raw.startswith(prefix):
            raw = raw[len(prefix) :].lstrip(":： #").strip()
            break
    else:
        return None
    m = re.search(r"\d+", raw)
    return int(m.group()) if m else None


def _parse_select_query(text: str) -> str | None:
    raw = _strip_mention(text).strip()
    for prefix in SELECT_PREFIXES:
        if raw.startswith(prefix):
            raw = raw[len(prefix) :].lstrip(":： ").strip()
            break
    else:
        return None
    return raw or None


def _handle_slot_command(db: Session, content: str) -> str | None:
    from app.services.agent_slots import format_slots_message, update_slot

    raw = _strip_mention(content).strip()
    for prefix in SLOT_PREFIXES:
        if raw.startswith(prefix):
            raw = raw[len(prefix) :].lstrip(":： ").strip()
            break
    else:
        return None

    if not raw or raw.lower() in ("列表", "list"):
        return format_slots_message(db)

    m = re.match(
        r"^(?:(执行|审查)\s+)?(on|off|开|关)\s+(?P<device>[\w-]+)\s+(?P<agent>cursor|trae|dsh)\s*$",
        raw,
        re.I,
    )
    if not m:
        return format_slots_message(db) + "\n\n格式：选配 off device-b trae"

    role = m.group(1)
    on = m.group(2).lower() in ("on", "开")
    device_id = m.group("device")
    agent_id = m.group("agent").lower()

    try:
        if role is None:
            if on:
                update_slot(
                    db, device_id, agent_id,
                    enabled=True, can_implement=True, can_review=True,
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


def _project_items(db: Session) -> list[dict[str, Any]]:
    from app.services.project_catalog import discover_projects, sync_catalog_to_hub

    projects = discover_projects(db)
    sync_catalog_to_hub(db, projects)
    return [
        {
            "index": i,
            "display_name": p.display_name,
            "slug": p.slug,
            "github_owner": p.github_owner,
            "github_repo": p.github_repo,
            "local_path": p.local_path,
            "source": p.source,
        }
        for i, p in enumerate(projects, start=1)
    ]


def help_text() -> str:
    return """联合器 Bot 指令：

项目 — 项目列表
选 3 / 选 owner/repo — 选择项目
当前项目 — 查看已选仓库
派活 任务标题 | 分支 — 派活到电脑
（先选项目后）直接发任务标题也可派活
确认执行 3 — 确认执行任务 #3（半自动）
稍后 3 — 任务稍后执行
状态 3 — 查任务进度
联通 — 设备在线
选配 — Cursor/Trae 阵容
套件 — Head 四项目健康
灵魂 你的问题 — 问自研 AI
帮助 — 本说明"""


def handle_bot_text(
    db: Session,
    session_id: str,
    content: str,
    *,
    channel: str = "mobile",
    message_id: str | None = None,
    source_label: str | None = None,
) -> BotReply | None:
    """统一 Bot 命令处理（飞书 / App / 未来 IM 共用）。"""
    text = (content or "").strip()
    if not text or not session_id:
        return None

    slot_reply = _handle_slot_command(db, text)
    if slot_reply is not None:
        return BotReply(text=slot_reply, kind="slots")

    if _starts_with_any(text, HELP_PREFIXES):
        return BotReply(text=help_text(), kind="help")

    # P1：确认执行 / 稍后
    raw_cmd = _strip_mention(text).strip()
    for prefix in CONFIRM_PREFIXES:
        if raw_cmd.startswith(prefix):
            rest = raw_cmd[len(prefix) :].lstrip(":： #").strip()
            m = re.search(r"\d+", rest)
            if not m:
                return BotReply(text="格式：确认执行 任务ID", kind="error")
            tid = int(m.group())
            try:
                from app.services.exec_confirm import confirm_task
                from app.services.agent_replies import submit_agent_reply
                from app.services.event_bus import emit_event
                from app.models import Task

                data = confirm_task(tid)
                task = db.get(Task, tid)
                if task:
                    submit_agent_reply(
                        db,
                        tid,
                        data.get("device_id") or "hub",
                        data.get("agent_id") or "system",
                        f"✅ 已确认执行任务 #{tid}，正在唤醒 Agent…",
                        source="exec-confirm",
                        notify_feishu=True,
                    )
                    emit_event("task.exec_confirmed", task=task, db=db)
                return BotReply(
                    text=f"✅ 已确认执行任务 #{tid}，电脑即将唤醒 Agent",
                    kind="exec_confirm",
                    task_id=tid,
                )
            except ValueError as e:
                return BotReply(text=str(e), kind="error")

    for prefix in DEFER_PREFIXES:
        if raw_cmd.startswith(prefix):
            rest = raw_cmd[len(prefix) :].lstrip(":： #").strip()
            m = re.search(r"\d+", rest)
            if not m:
                return BotReply(text="格式：稍后 任务ID", kind="error")
            tid = int(m.group())
            try:
                from app.services.exec_confirm import defer_task
                from app.services.agent_replies import submit_agent_reply
                from app.services.event_bus import emit_event
                from app.models import Task

                data = defer_task(tid)
                task = db.get(Task, tid)
                if task:
                    submit_agent_reply(
                        db,
                        tid,
                        data.get("device_id") or "hub",
                        data.get("agent_id") or "system",
                        f"⏸ 任务 #{tid} 已稍后执行",
                        source="exec-defer",
                        notify_feishu=True,
                    )
                    emit_event("task.exec_deferred", task=task, db=db)
                return BotReply(
                    text=f"⏸ 任务 #{tid} 已稍后，需要时再发「确认执行 {tid}」",
                    kind="exec_defer",
                    task_id=tid,
                )
            except ValueError as e:
                return BotReply(text=str(e), kind="error")

    if _starts_with_any(text, PROJECT_PREFIXES):
        from app.services.project_catalog import discover_projects
        from app.services.feishu_sessions import get_chat_session

        raw_projects = discover_projects(db)
        projects = _project_items(db)
        lines = [f"已加载 {len(projects)} 个项目。点击选择或发送「选 序号 / 选 owner/repo」。"]
        card = None
        if channel == "feishu":
            session = get_chat_session(db, session_id)
            card = build_project_picker_card(raw_projects, page=0, session=session)
        return BotReply(
            text="\n".join(lines),
            card=card,
            projects=projects,
            kind="projects",
        )

    if _starts_with_any(text, CURRENT_PREFIXES):
        return BotReply(text=format_current_project(db, session_id), kind="current_project")

    select_query = _parse_select_query(text)
    if select_query is not None:
        feishu_reply = select_project_by_query(db, session_id, select_query)
        return BotReply(text=feishu_reply.text or "", kind="select_project")

    if any(text.startswith(p) for p in CONNECT_PREFIXES):
        from app.models import Device

        report = connectivity_report(
            db.query(Device).order_by(Device.device_id).all(),
            expected_device_ids=parse_expected_devices(),
        )
        return BotReply(
            text="📡 设备联通性\n" + format_connectivity_message(report),
            kind="connectivity",
        )

    if any(text.strip().startswith(p) for p in AUTOMATION_PREFIXES):
        from app.models import Workflow

        wf_active = db.query(Workflow).filter(Workflow.active.is_(True)).count()
        wf_total = db.query(Workflow).count()
        lines = [
            "⚙️ 内置工作流引擎",
            f"启用: {'是' if settings.workflows_enabled else '否'}",
            f"工作流: {wf_active}/{wf_total} 激活",
            "编辑器: /workflows/editor",
        ]
        return BotReply(text="\n".join(lines), kind="automation")

    if any(text.strip().startswith(p) for p in STACK_PREFIXES):
        from app.models import Workflow
        from app.services.n8n_bridge import n8n_health_sync
        from app.services.soul_bridge import stack_health_sync

        stack = stack_health_sync()
        n8n = n8n_health_sync()
        wf_active = db.query(Workflow).filter(Workflow.active.is_(True)).count()
        lines = [
            f"📦 Head 套件 · {stack.get('overall', '?')}",
            f"session: {stack.get('session_id')}",
        ]
        for name, comp in (stack.get("components") or {}).items():
            ok = "✅" if comp.get("ok") else "❌"
            lines.append(f"{ok} {name}: {comp.get('url') or comp.get('error', '')}")
        lines.append(f"{'✅' if settings.workflows_enabled else '❌'} workflow_engine ({wf_active} 激活)")
        if settings.n8n_enabled:
            lines.append(f"{'✅' if n8n.get('ok') else '❌'} n8n: {n8n.get('url')}")
        return BotReply(text="\n".join(lines), kind="stack")

    soul_msg = _parse_soul_message(text)
    if soul_msg is not None:
        from app.services.soul_bridge import soul_chat_sync

        result = soul_chat_sync(message=soul_msg)
        if result.get("ok"):
            reply = (result.get("reply") or "").strip() or "(空回复)"
            if len(reply) > 3500:
                reply = reply[:3500] + "…"
            return BotReply(text=f"🧠 自研AI\n{reply}", kind="soul")
        return BotReply(
            text=f"灵魂层不可用: {result.get('detail') or result.get('error')}",
            kind="error",
        )

    task_id = _parse_status(text)
    if task_id is not None:
        from app.models import Task

        task = db.get(Task, task_id)
        if not task:
            return BotReply(text=f"任务 #{task_id} 不存在", kind="error")
        status = command_status(task, db)
        return BotReply(
            text="📋 任务状态\n" + status["message"],
            kind="status",
            task_id=task_id,
        )

    reply_parsed = _parse_reply(text)
    if reply_parsed:
        from app.services.agent_replies import submit_agent_reply

        tid, device_id, agent_id, body = reply_parsed
        if not body:
            return BotReply(text="回复格式：回复 任务ID 设备 agent\n内容...", kind="error")
        if not device_id:
            device_id = settings.feishu_default_implementer_device
        src = channel if channel != "feishu" else "feishu"
        try:
            submit_agent_reply(db, tid, device_id, agent_id, body, source=src)
            return BotReply(text=f"已转发 {device_id}/{agent_id} 的回复", kind="reply")
        except ValueError as e:
            return BotReply(text=str(e), kind="error")

    parsed = _parse_dispatch(text, session_id=session_id, db=db)
    if not parsed:
        return None

    if parsed.get("needs_project"):
        return BotReply(
            text="请先选择项目：发送「项目」或「选 项目名 / 选 owner/repo」。",
            kind="needs_project",
            projects=_project_items(db),
        )

    from app.services.agent_slots import resolve_dispatch_roles

    label = source_label or f"{channel}:{session_id}"
    try:
        impl_d, impl_a, reviewers = resolve_dispatch_roles(db)
        task, _project = dispatch_command(
            db,
            github_owner=parsed["github_owner"],
            github_repo=parsed["github_repo"],
            title=parsed["title"],
            description=f"来自 {label}",
            branch=parsed["branch"],
            implementer_device_id=impl_d,
            implementer_agent_id=impl_a,
            required_reviewers=reviewers,
            feishu_chat_id=session_id,
            feishu_message_id=message_id,
        )
    except ValueError as e:
        return BotReply(text=f"派活失败：{e}", kind="error")

    status = command_status(task, db)
    repo_label = f"{parsed['github_owner']}/{parsed['github_repo']}"
    from app.services.event_bus import emit_event

    emit_event("task.dispatched", task=task, db=db)
    return BotReply(
        text="✅ 任务已创建\n" + f"项目：{repo_label}\n" + status["message"],
        kind="dispatch",
        task_id=task.id,
    )
