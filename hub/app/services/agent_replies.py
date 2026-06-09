from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AgentReply, Task
from app.services.feishu_notify import notify_agent_reply


def submit_agent_reply(
    db: Session,
    task_id: int,
    device_id: str,
    agent_id: str,
    content: str,
    *,
    source: str = "agent",
    notify_feishu: bool = True,
) -> AgentReply:
    task = db.get(Task, task_id)
    if not task:
        raise ValueError(f"任务 #{task_id} 不存在")
    if not content.strip():
        raise ValueError("回复内容不能为空")

    reply = AgentReply(
        task_id=task.id,
        device_id=device_id,
        agent_id=agent_id,
        content=content.strip(),
        source=source,
    )
    db.add(reply)
    db.commit()
    db.refresh(reply)

    if notify_feishu:
        notify_agent_reply(task, device_id, agent_id, content.strip())
    return reply
