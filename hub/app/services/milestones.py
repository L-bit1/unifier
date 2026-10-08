"""P2 里程碑进度（非 CoT 流式）。"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import Task
from app.services.agent_replies import submit_agent_reply
from app.services.event_bus import emit_event

MILESTONE_LABELS = {
    "context": "🔍 正在读取代码上下文…",
    "edit": "✍️ 正在修改代码…",
    "test": "🧪 正在运行测试…",
    "commit": "📦 正在生成 Commit…",
    "review": "👀 正在审查…",
    "done": "✅ 阶段完成",
}


def post_milestone(
    db: Session,
    task_id: int,
    *,
    milestone: str,
    detail: str | None = None,
    device_id: str | None = None,
    agent_id: str | None = None,
    notify_feishu: bool = True,
) -> dict[str, Any]:
    task = db.get(Task, task_id)
    if not task:
        raise ValueError(f"任务 #{task_id} 不存在")

    key = (milestone or "").strip().lower()
    label = MILESTONE_LABELS.get(key, f"📍 {milestone}")
    body = label
    if detail:
        body = f"{label}\n{detail.strip()}"

    device = device_id or task.assignee_device_id or "hub"
    agent = agent_id or task.assignee_agent_id or "system"
    reply = submit_agent_reply(
        db,
        task_id,
        device,
        agent,
        body,
        source=f"milestone:{key or 'custom'}",
        notify_feishu=notify_feishu,
    )
    emit_event(
        "task.milestone",
        task=task,
        db=db,
        extra={"milestone": key, "detail": detail},
    )
    return {
        "ok": True,
        "task_id": task_id,
        "milestone": key,
        "reply_id": reply.id,
        "text": body,
    }
