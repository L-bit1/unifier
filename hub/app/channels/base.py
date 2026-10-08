from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy.orm import Session

from app.channels.types import ChannelReply, IncomingMessage


class ChannelAdapter(ABC):
    """IM / Web 入口适配器：normalize → handle → send。"""

    name: str

    @abstractmethod
    def normalize_event(self, event: dict[str, Any]) -> IncomingMessage | None:
        """将通道原生事件转为 IncomingMessage；无法处理则返回 None。"""

    @abstractmethod
    def handle_message(
        self, db: Session, message: IncomingMessage
    ) -> ChannelReply | None:
        """执行业务逻辑，返回待发送回复。"""

    @abstractmethod
    async def send_reply(
        self, message: IncomingMessage, reply: ChannelReply
    ) -> str | None:
        """发送回复，返回 outbound message_id（若有）。"""

    def to_handler_event(self, message: IncomingMessage) -> dict[str, Any]:
        """供遗留 handler 使用的 compact 事件 dict。"""
        return {
            "type": f"{self.name}.message.receive",
            "channel": self.name,
            "chat_id": message.chat_id,
            "message_id": message.message_id,
            "message_type": message.message_type,
            "content": message.content,
            "sender_type": message.sender_type,
            "sender_id": message.sender_id,
            **message.raw_event,
        }
