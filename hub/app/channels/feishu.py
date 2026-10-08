from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.channels.base import ChannelAdapter
from app.channels.types import ChannelReply, IncomingMessage
from app.config import settings
from app.services.feishu import FeishuError, feishu_client
from app.services.feishu_handler import handle_im_message_event
from app.services.feishu_projects import FeishuReply

logger = logging.getLogger(__name__)


class FeishuChannelAdapter(ChannelAdapter):
    name = "feishu"

    def normalize_event(self, event: dict[str, Any]) -> IncomingMessage | None:
        event_type = event.get("type")
        if event_type and event_type not in (
            "im.message.receive_v1",
            "feishu.message.receive",
            None,
        ):
            return None
        chat_id = event.get("chat_id")
        content = (event.get("content") or "").strip()
        if not chat_id or not content:
            return None
        return IncomingMessage(
            channel=self.name,
            chat_id=str(chat_id),
            message_id=event.get("message_id"),
            content=content,
            message_type=event.get("message_type", "text"),
            sender_type=event.get("sender_type")
            or (event.get("sender") or {}).get("sender_type"),
            sender_id=event.get("sender_id"),
            raw_event=event,
        )

    def handle_message(
        self, db: Session, message: IncomingMessage
    ) -> ChannelReply | None:
        if message.sender_type == "bot":
            return None
        if message.message_type != "text":
            return None
        event = self.to_handler_event(message)
        event["type"] = "im.message.receive_v1"
        reply = handle_im_message_event(db, event)
        if not reply:
            return None
        return ChannelReply(text=reply.text, card=reply.card)

    async def send_reply(
        self, message: IncomingMessage, reply: ChannelReply
    ) -> str | None:
        if not settings.feishu_configured:
            return None
        message_id = message.message_id
        chat_id = message.chat_id
        sent_id: str | None = None
        try:
            if reply.card:
                if message_id:
                    sent_id = await feishu_client.reply_interactive(message_id, reply.card)
                elif chat_id:
                    sent_id = await feishu_client.send_interactive_to_chat(
                        chat_id, reply.card
                    )
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
                    raise
            else:
                logger.warning("飞书通知失败: %s", e)
                raise
        return sent_id


def feishu_reply_to_channel(reply: FeishuReply) -> ChannelReply:
    return ChannelReply(text=reply.text, card=reply.card)
