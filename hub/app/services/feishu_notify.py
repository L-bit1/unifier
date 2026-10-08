from __future__ import annotations

import asyncio
import logging

from app.config import settings
from app.models import Task
from app.services.feishu import FeishuError, feishu_client
from app.services.orchestrate import command_status

logger = logging.getLogger(__name__)

# P0 任务通知流：统一文案（飞书 / 可复用到 App）
LIFECYCLE_EVENTS = frozenset(
    {
        "task.dispatched",
        "task.inbox_acked",
        "task.manifest_submitted",
        "task.review_started",
        "task.review_waiting",
        "task.review_voted",
        "task.merge_ready",
        "task.changes_requested",
        "task.execution_aborted",
        "task.agent_replied",
        "task.milestone",
    }
)


def _format_agent_reply(device_id: str, agent_id: str, content: str) -> str:
    label = f"{device_id}/{agent_id}"
    if agent_id == "cursor":
        label = f"🖥 Cursor · {device_id}"
    elif agent_id == "trae":
        label = f"🖥 Trae · {device_id}"
    return f"【{label}】\n{content.strip()}"


def _is_feishu_chat(chat_id: str | None) -> bool:
    """mobile:xxx 等非飞书会话不调飞书 API。"""
    if not chat_id:
        return False
    if chat_id.startswith("mobile:"):
        return False
    return True


async def _send_to_task_chat(task: Task, text: str, reply_to_root: bool = True) -> None:
    if not _is_feishu_chat(task.feishu_chat_id) or not settings.feishu_configured:
        return
    try:
        if reply_to_root and task.feishu_message_id:
            await feishu_client.reply_text(task.feishu_message_id, text)
        else:
            await feishu_client.send_text_to_chat(task.feishu_chat_id, text)
    except FeishuError as e:
        logger.warning("飞书通知失败 task=%s: %s", task.id, e)


def notify_task_async(task: Task, text: str, *, reply_to_root: bool = True) -> None:
    if not _is_feishu_chat(task.feishu_chat_id):
        return
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_send_to_task_chat(task, text, reply_to_root))
    except RuntimeError:
        asyncio.run(_send_to_task_chat(task, text, reply_to_root))


def notify_dispatch(task: Task, db) -> None:
    status = command_status(task, db)
    text = f"✅ 任务 #{task.id} 已创建并派活\n" + status["message"]
    notify_task_async(task, text)


def notify_manifest(task: Task, device_id: str, agent_id: str, summary: str) -> None:
    text = _format_agent_reply(device_id, agent_id, f"已提交变更清单\n{summary}")
    notify_task_async(task, text)


def notify_review(task: Task, reviewer_id: str, status: str, note: str | None) -> None:
    icon = "✅" if status == "approved" else "⚠️"
    body = f"{icon} 审查 {reviewer_id}: {status}"
    if note:
        body += f"\n{note}"
    notify_task_async(task, body)


def notify_agent_reply(task: Task, device_id: str, agent_id: str, content: str) -> None:
    text = _format_agent_reply(device_id, agent_id, content)
    notify_task_async(task, text)


def notify_status(task: Task, db) -> None:
    status = command_status(task, db)
    notify_task_async(task, "📋 任务状态\n" + status["message"])


def format_lifecycle_message(
    event_type: str,
    task: Task,
    *,
    db=None,
    extra: dict | None = None,
) -> str | None:
    """P0 任务通知流文案；返回 None 表示本事件不额外推（避免与专用 notify 重复）。"""
    extra = extra or {}
    tid = task.id
    title = (task.title or "").strip() or "(无标题)"

    if event_type == "task.dispatched":
        agent = f"{task.assignee_device_id}/{task.assignee_agent_id}"
        return (
            f"✅ 任务 #{tid} 已派活\n"
            f"标题：{title}\n"
            f"执行端：{agent}\n"
            f"状态：等待电脑收件箱拉取…"
        )

    if event_type == "task.inbox_acked":
        # inbox-auto-runner 已用 agent-reply 推「已收到」文案，此处只驱动工作流
        return None

    if event_type == "task.manifest_submitted":
        return None

    if event_type == "task.review_started":
        return (
            f"⏳ 任务 #{tid} 进入审查\n"
            f"标题：{title}\n"
            f"等待审查者投票…"
        )

    if event_type == "task.review_waiting":
        mins = extra.get("waited_minutes", "?")
        missing = extra.get("missing_reviewers") or []
        miss = "、".join(missing) if missing else "审查者"
        return (
            f"⏳ 等待审查，已等 {mins} 分钟\n"
            f"任务 #{tid} · {title}\n"
            f"仍缺：{miss}"
        )

    if event_type == "task.merge_ready":
        msg = ""
        if db is not None:
            msg = "\n" + command_status(task, db).get("message", "")
        return f"✅ 任务 #{tid} 审查通过，可合并\n标题：{title}{msg}"

    if event_type == "task.changes_requested":
        return (
            f"⚠️ 任务 #{tid} 需要修改\n"
            f"标题：{title}\n"
            f"审查未通过，请按意见继续改"
        )

    if event_type == "task.execution_aborted":
        # execution-abort 已用 agent-reply 推详细原因，避免双发
        return None

    if event_type in ("task.agent_replied", "task.review_voted"):
        return None

    return None


def notify_lifecycle(
    event_type: str,
    task: Task,
    *,
    db=None,
    extra: dict | None = None,
) -> None:
    """P0 任务通知流：飞书推一条 + 写入 agent_replies（App 气泡同源）。"""
    if event_type not in LIFECYCLE_EVENTS:
        return
    text = format_lifecycle_message(event_type, task, db=db, extra=extra)
    if not text:
        return

    # App / 审计：落库（mobile 会话派活文案已在 Bot 回复里，跳过 dispatched 防双条）
    if db is not None:
        skip_persist = event_type == "task.dispatched" and str(
            task.feishu_chat_id or ""
        ).startswith("mobile:")
        if not skip_persist:
            try:
                _persist_lifecycle_for_app(db, task, text, event_type, extra or {})
            except Exception as e:
                logger.warning("lifecycle persist fail task=%s: %s", task.id, e)

    # 飞书通道（mobile: 会话自动跳过）
    notify_task_async(task, text)


def _persist_lifecycle_for_app(
    db,
    task: Task,
    text: str,
    event_type: str,
    extra: dict,
) -> None:
    """写入 agent_replies，避免循环 import submit_agent_reply。"""
    from app.models import AgentReply

    device_id = extra.get("device_id") or task.assignee_device_id or "hub"
    agent_id = extra.get("agent_id") or task.assignee_agent_id or "system"
    source = f"lifecycle:{event_type}"

    # 同任务同事件短时间去重（防 emit 双发）
    recent = (
        db.query(AgentReply)
        .filter(
            AgentReply.task_id == task.id,
            AgentReply.source == source,
            AgentReply.content == text.strip(),
        )
        .order_by(AgentReply.id.desc())
        .first()
    )
    if recent:
        return

    reply = AgentReply(
        task_id=task.id,
        device_id=str(device_id),
        agent_id=str(agent_id),
        content=text.strip(),
        source=source,
    )
    db.add(reply)
    db.commit()
