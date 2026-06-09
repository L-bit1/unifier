from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import FeishuChatSession, utcnow
from app.services.orchestrate import get_or_create_project
from app.services.project_catalog import CatalogProject


def get_chat_session(db: Session, chat_id: str) -> FeishuChatSession | None:
    return (
        db.query(FeishuChatSession)
        .filter(FeishuChatSession.chat_id == chat_id)
        .first()
    )


def set_chat_project(
    db: Session,
    chat_id: str,
    project: CatalogProject,
) -> FeishuChatSession:
    get_or_create_project(db, project.github_owner, project.github_repo)
    session = get_chat_session(db, chat_id)
    if session is None:
        session = FeishuChatSession(chat_id=chat_id)
        db.add(session)
    session.github_owner = project.github_owner
    session.github_repo = project.github_repo
    session.display_name = project.display_name
    session.local_path = project.local_path
    session.updated_at = utcnow()
    db.commit()
    db.refresh(session)
    return session


def format_current_project(db: Session, chat_id: str) -> str:
    session = get_chat_session(db, chat_id)
    if not session:
        return "当前未选择项目。发送「项目」打开项目卡片，或回复「选 项目名 / 选 3 / 选 owner/repo」。"
    label = session.display_name or session.github_repo
    lines = [
        f"当前项目：{label}",
        f"仓库：{session.github_owner}/{session.github_repo}",
    ]
    if session.local_path:
        lines.append(f"本地路径：{session.local_path}")
    lines.append("可直接 @机器人 发送任务标题，或「派活 任务名 | feature/分支」。")
    return "\n".join(lines)
