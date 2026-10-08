from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class IncomingMessage:
    """通道无关的入站消息。"""

    channel: str
    chat_id: str
    message_id: str | None
    content: str
    message_type: str = "text"
    sender_type: str | None = None
    sender_id: str | None = None
    raw_event: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChannelReply:
    text: str | None = None
    card: dict[str, Any] | None = None
