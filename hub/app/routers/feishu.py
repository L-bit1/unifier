from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.channels.registry import get_channel_adapter, list_channel_adapters
from app.database import get_db
from app.services.feishu_projects import handle_card_action

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/feishu", tags=["feishu"])


class FeishuEventIn(BaseModel):
    type: str | None = None
    message_id: str | None = None
    chat_id: str | None = None
    message_type: str | None = None
    content: str | None = None
    sender_type: str | None = None
    sender_id: str | None = None

    model_config = {"extra": "allow"}


class FeishuEventOut(BaseModel):
    handled: bool
    reply: str | None = None
    card: dict | None = None
    message_id: str | None = None
    channel: str = "feishu"


class FeishuCardActionOut(BaseModel):
    toast: dict | None = None
    card: dict | None = None


@router.post("/events", response_model=FeishuEventOut)
async def ingest_feishu_event(body: FeishuEventIn, db: Session = Depends(get_db)):
    """接收 feishu-bridge 转发的 compact 事件（经 ChannelAdapter）。"""
    adapter = get_channel_adapter("feishu")
    event: dict[str, Any] = body.model_dump(exclude_none=True)
    message = adapter.normalize_event(event)
    if not message:
        return FeishuEventOut(handled=False, channel=adapter.name)

    reply = adapter.handle_message(db, message)
    if not reply:
        return FeishuEventOut(handled=False, channel=adapter.name)

    try:
        sent_id = await adapter.send_reply(message, reply)
    except Exception as e:
        logger.warning("飞书回复失败: %s", e)
        raise HTTPException(status_code=502, detail=str(e))

    return FeishuEventOut(
        handled=True,
        reply=reply.text,
        card=reply.card,
        message_id=sent_id,
        channel=adapter.name,
    )


@router.post("/card-actions", response_model=FeishuCardActionOut)
def ingest_feishu_card_action(body: dict[str, Any], db: Session = Depends(get_db)):
    """供 feishu-card-bridge 转发 card.action.trigger 回调。"""
    result = handle_card_action(db, body)
    return FeishuCardActionOut(
        toast=result.get("toast"),
        card=result.get("card"),
    )


@router.get("/status")
def feishu_integration_status():
    from app.config import settings

    return {
        "configured": settings.feishu_configured,
        "channel": "feishu",
        "registered_channels": list_channel_adapters(),
        "default_repo": f"{settings.feishu_default_github_owner}/{settings.feishu_default_github_repo}",
        "commands": [
            "项目 — 扫描工作区/GitHub 并发送项目选择卡片",
            "选 项目名 / 选 3 / 选 owner/repo — 文字选择项目",
            "当前项目 — 查看已选仓库",
            "派活 任务标题 | feature/分支",
            "owner/repo 派活 任务标题 | 分支",
            "（先选项目后）直接 @机器人 任务标题",
            "状态 1",
            "联通 / 在线",
            "选配 / 选配 off win-pc trae / 选配 执行 off mac-a trae",
            "回复 1 mac-a cursor\\nCursor 的回复内容",
        ],
        "workspace_roots": [str(p) for p in settings.workspace_roots_list()],
    }
