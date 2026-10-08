from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.services.bot_commands import handle_bot_text
from app.services.feishu_projects import FeishuReply, handle_card_action as _handle_card_action


def _strip_bot_mention(text: str) -> str:
    return re.sub(r"@_user_\d+|@\S+", "", text).strip()


def handle_im_message_event(db: Session, event: dict[str, Any]) -> FeishuReply | None:
    """处理 compact 格式的 im.message.receive_v1 事件（委托统一 Bot 层）。"""
    if event.get("type") and event.get("type") != "im.message.receive_v1":
        return None

    chat_id = event.get("chat_id")
    message_id = event.get("message_id")
    message_type = event.get("message_type", "text")
    content = (event.get("content") or "").strip()
    sender_type = event.get("sender_type") or event.get("sender", {}).get("sender_type")

    if sender_type == "bot":
        return None
    if message_type != "text" or not content or not chat_id:
        return None

    reply = handle_bot_text(
        db,
        chat_id,
        content,
        channel="feishu",
        message_id=message_id,
        source_label=f"飞书群 {chat_id}",
    )
    if not reply:
        return None
    return reply.to_feishu()


def handle_card_action(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    return _handle_card_action(db, payload)
