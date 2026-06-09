from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.services.feishu import FeishuError, feishu_client
from app.services.feishu_handler import handle_im_message_event
from app.services.feishu_projects import FeishuReply, handle_card_action

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


class FeishuCardActionOut(BaseModel):
    toast: dict | None = None
    card: dict | None = None


async def _send_feishu_reply(
    event: dict[str, Any],
    reply: FeishuReply,
) -> str | None:
    message_id = event.get("message_id")
    chat_id = event.get("chat_id")
    sent_id: str | None = None
    if not settings.feishu_configured:
        return None
    try:
        if reply.card:
            if message_id:
                sent_id = await feishu_client.reply_interactive(message_id, reply.card)
            elif chat_id:
                sent_id = await feishu_client.send_interactive_to_chat(chat_id, reply.card)
        if reply.text:
            if message_id:
                sent_id = await feishu_client.reply_text(message_id, reply.text)
            elif chat_id:
                sent_id = await feishu_client.send_text_to_chat(chat_id, reply.text)
    except FeishuError as e:
        if chat_id and message_id and reply.text:
            try:
                sent_id = await feishu_client.send_text_to_chat(chat_id, reply.text)
            except FeishuError:
                logger.warning("飞书通知失败: %s", e)
                raise HTTPException(status_code=502, detail=str(e))
        else:
            logger.warning("飞书通知失败: %s", e)
            raise HTTPException(status_code=502, detail=str(e))
    return sent_id


@router.post("/events", response_model=FeishuEventOut)
async def ingest_feishu_event(body: FeishuEventIn, db: Session = Depends(get_db)):
    """接收 feishu-bridge 转发的 compact 事件，派活/查状态/转发 Agent 回复。"""
    event: dict[str, Any] = body.model_dump(exclude_none=True)
    reply = handle_im_message_event(db, event)
    if not reply:
        return FeishuEventOut(handled=False)

    sent_id = await _send_feishu_reply(event, reply)
    return FeishuEventOut(
        handled=True,
        reply=reply.text,
        card=reply.card,
        message_id=sent_id,
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
    return {
        "configured": settings.feishu_configured,
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
