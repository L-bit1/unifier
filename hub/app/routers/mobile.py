from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.bot_commands import help_text, handle_bot_text
from app.services.feishu_sessions import format_current_project

router = APIRouter(prefix="/api/v1/mobile", tags=["mobile"])


class MobileCommandIn(BaseModel):
    text: str = Field(..., min_length=1)
    session_id: str = Field(default="default", description="会话 ID，对应 Hub 项目选择上下文")


class MobileCommandOut(BaseModel):
    handled: bool
    text: str | None = None
    kind: str | None = None
    task_id: int | None = None
    projects: list[dict] = Field(default_factory=list)


class MobileSelectProjectIn(BaseModel):
    session_id: str = "default"
    github_owner: str
    github_repo: str
    display_name: str | None = None


@router.get("/help")
def mobile_help():
    return {"text": help_text(), "commands": help_text().splitlines()}


@router.get("/session")
def mobile_session(session_id: str = "default", db: Session = Depends(get_db)):
    chat_key = f"mobile:{session_id}"
    return {"session_id": session_id, "current_project": format_current_project(db, chat_key)}


@router.post("/command", response_model=MobileCommandOut)
def mobile_command(body: MobileCommandIn, db: Session = Depends(get_db)):
    """App / 未来 IM 与飞书 Bot 同款的文本命令入口。"""
    chat_key = f"mobile:{body.session_id}"
    reply = handle_bot_text(
        db,
        chat_key,
        body.text,
        channel="mobile",
        source_label=f"联合器 App ({body.session_id})",
    )
    if not reply:
        return MobileCommandOut(
            handled=False,
            text="未识别指令。发送「帮助」查看命令列表。",
            kind="unknown",
        )
    data = reply.to_mobile()
    return MobileCommandOut(handled=True, **data)


@router.post("/select-project")
def mobile_select_project(body: MobileSelectProjectIn, db: Session = Depends(get_db)):
    from app.services.feishu_sessions import set_chat_project
    from app.services.project_catalog import CatalogProject

    chat_key = f"mobile:{body.session_id}"
    project = CatalogProject(
        display_name=body.display_name or body.github_repo,
        github_owner=body.github_owner,
        github_repo=body.github_repo,
        local_path=None,
        source="mobile",
    )
    set_chat_project(db, chat_key, project)
    return {"ok": True, "text": format_current_project(db, chat_key)}


@router.get("/updates")
def mobile_updates(
    session_id: str = "default",
    since_id: int = 0,
    db: Session = Depends(get_db),
):
    """App P0 任务通知流：与飞书同款状态（收件/完成/审查/失败）弹进气泡。"""
    from app.models import AgentReply, Task

    chat_key = f"mobile:{session_id}"
    rows = (
        db.query(AgentReply)
        .join(Task, Task.id == AgentReply.task_id)
        .filter(Task.feishu_chat_id == chat_key, AgentReply.id > since_id)
        .order_by(AgentReply.id.asc())
        .limit(50)
        .all()
    )
    items = []
    for r in rows:
        kind = "status"
        src = r.source or ""
        if src.startswith("lifecycle:") or src.startswith("milestone:"):
            kind = "lifecycle"
        elif src in (
            "inbox-auto-runner",
            "execution-supervisor",
            "exec-confirm-request",
            "exec-confirm",
            "exec-defer",
        ):
            kind = "lifecycle"
        elif src.startswith("cursor") or src in ("agent", "mcp", "auto-push-daemon"):
            kind = "reply"
        # P1：待确认执行 → App 可点按钮
        needs_confirm = src == "exec-confirm-request"
        items.append(
            {
                "id": r.id,
                "task_id": r.task_id,
                "device_id": r.device_id,
                "agent_id": r.agent_id,
                "content": r.content,
                "source": r.source,
                "kind": kind,
                "needs_confirm": needs_confirm,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
        )
    next_since = items[-1]["id"] if items else since_id
    return {"since_id": since_id, "next_since_id": next_since, "count": len(items), "items": items}


class MobileConfirmIn(BaseModel):
    session_id: str = "default"
    task_id: int
    action: str = Field(..., description="confirm | defer")


@router.post("/exec-confirm")
def mobile_exec_confirm(body: MobileConfirmIn, db: Session = Depends(get_db)):
    """App P1：确认执行 / 稍后。"""
    from app.routers.tasks import ConfirmExecBody, post_exec_confirm

    return post_exec_confirm(
        body.task_id,
        ConfirmExecBody(action=body.action),
        db,
    )


@router.get("/exec-confirm/pending")
def mobile_exec_pending(device_id: str | None = None):
    from app.services.exec_confirm import list_pending

    return {"items": list_pending(device_id)}
