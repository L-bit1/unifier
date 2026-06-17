"""联合器事件总线：任务生命周期 → n8n 等自动化 Connector。"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models import Task
from app.services.n8n_bridge import emit_to_n8n, emit_to_n8n_sync, n8n_configured
from app.services.orchestrate import command_status

logger = logging.getLogger(__name__)


def _task_payload(task: Task, db: Session | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {
        "task_id": task.id,
        "project_id": task.project_id,
        "title": task.title,
        "description": task.description,
        "branch": task.branch,
        "status": task.status,
        "assignee_device_id": task.assignee_device_id,
        "assignee_agent_id": task.assignee_agent_id,
        "required_reviewers": task.required_reviewers,
        "feishu_chat_id": task.feishu_chat_id,
    }
    if db is not None:
        status = command_status(task, db)
        data["merge_ready"] = status["merge_ready"]
        data["review_summary"] = status["review_summary"]
        data["message"] = status["message"]
    return data


def emit_event(
    event_type: str,
    *,
    task: Task | None = None,
    db: Session | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """异步友好地发出 Hub 事件（不阻断主流程）。"""
    if not n8n_configured():
        return

    data: dict[str, Any] = {}
    if task is not None:
        data.update(_task_payload(task, db))
    if extra:
        data.update(extra)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(emit_to_n8n(event_type, data))
    except RuntimeError:
        result = emit_to_n8n_sync(event_type, data)
        if not result.get("ok") and not result.get("skipped"):
            logger.debug("event_bus sync emit %s: %s", event_type, result)
