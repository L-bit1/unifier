from __future__ import annotations

import asyncio
import logging

from app.config import settings
from app.models import Task
from app.services.feishu import FeishuError, feishu_client
from app.services.orchestrate import command_status

logger = logging.getLogger(__name__)


def _format_agent_reply(device_id: str, agent_id: str, content: str) -> str:
    label = f"{device_id}/{agent_id}"
    if agent_id == "cursor":
        label = f"🖥 Cursor · {device_id}"
    elif agent_id == "trae":
        label = f"🖥 Trae · {device_id}"
    return f"【{label}】\n{content.strip()}"


async def _send_to_task_chat(task: Task, text: str, reply_to_root: bool = True) -> None:
    if not task.feishu_chat_id or not settings.feishu_configured:
        return
    try:
        if reply_to_root and task.feishu_message_id:
            await feishu_client.reply_text(task.feishu_message_id, text)
        else:
            await feishu_client.send_text_to_chat(task.feishu_chat_id, text)
    except FeishuError as e:
        logger.warning("飞书通知失败 task=%s: %s", task.id, e)


def notify_task_async(task: Task, text: str, *, reply_to_root: bool = True) -> None:
    if not task.feishu_chat_id:
        return
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_send_to_task_chat(task, text, reply_to_root))
    except RuntimeError:
        asyncio.run(_send_to_task_chat(task, text, reply_to_root))


def notify_dispatch(task: Task, db) -> None:
    status = command_status(task, db)
    text = "✅ 任务已创建并派活\n" + status["message"]
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
