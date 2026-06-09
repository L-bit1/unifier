from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.services.feishu_cards import build_project_picker_card
from app.services.feishu_sessions import format_current_project, set_chat_project
from app.services.project_catalog import CatalogProject, discover_projects, find_project, sync_catalog_to_hub


@dataclass
class FeishuReply:
    text: str | None = None
    card: dict | None = None


def build_projects_reply(db: Session, chat_id: str, page: int = 0) -> FeishuReply:
    from app.services.feishu_sessions import get_chat_session

    projects = discover_projects(db)
    sync_catalog_to_hub(db, projects)
    session = get_chat_session(db, chat_id)
    card = build_project_picker_card(projects, page=page, session=session)
    text = (
        f"已加载 {len(projects)} 个项目。"
        "点击卡片按钮选择，或回复「选 项目名 / 选 序号」。"
    )
    return FeishuReply(text=text, card=card)


def handle_card_action(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    """处理 card.action.trigger，返回飞书回调响应体。"""
    from app.services.feishu_sessions import get_chat_session

    event = payload.get("event") or payload
    action = event.get("action") or {}
    value = action.get("value") or {}
    context = event.get("context") or {}
    chat_id = context.get("open_chat_id") or ""

    action_type = value.get("action")
    projects = discover_projects(db)

    if action_type == "project_page":
        page = int(value.get("page", 0))
        session = get_chat_session(db, chat_id) if chat_id else None
        card = build_project_picker_card(projects, page=page, session=session)
        return {
            "card": {"type": "raw", "data": card},
        }

    if action_type == "project_refresh":
        page = int(value.get("page", 0))
        sync_catalog_to_hub(db, projects)
        session = get_chat_session(db, chat_id) if chat_id else None
        card = build_project_picker_card(projects, page=page, session=session)
        return {
            "toast": {"type": "success", "content": f"已刷新，共 {len(projects)} 个项目"},
            "card": {"type": "raw", "data": card},
        }

    if action_type == "select_project":
        owner = value.get("owner")
        repo = value.get("repo")
        name = value.get("name") or repo
        if not owner or not repo or not chat_id:
            return {"toast": {"type": "error", "content": "无法识别项目或群 ID"}}

        project = CatalogProject(
            display_name=str(name),
            github_owner=str(owner),
            github_repo=str(repo),
            local_path=None,
            source="card",
        )
        for item in projects:
            if item.slug.lower() == project.slug.lower():
                project = item
                break

        set_chat_project(db, chat_id, project)
        session = get_chat_session(db, chat_id)
        return {
            "toast": {
                "type": "success",
                "content": f"已选择 {project.display_name}（{project.slug}）",
            },
            "card": {
                "type": "raw",
                "data": build_project_picker_card(
                    projects,
                    page=0,
                    session=session,
                ),
            },
        }

    return {"toast": {"type": "info", "content": "未知卡片操作"}}


def select_project_by_query(db: Session, chat_id: str, query: str) -> FeishuReply:
    projects = discover_projects(db)
    sync_catalog_to_hub(db, projects)
    project = find_project(projects, query)
    if not project:
        return FeishuReply(
            text=f"未找到项目「{query}」。发送「项目」查看列表，或「选 序号 / 选 owner/repo」。"
        )
    set_chat_project(db, chat_id, project)
    return FeishuReply(text=format_current_project(db, chat_id))
