"""IM / 协作通道适配层（飞书、钉钉、企微、Web 等）。"""
from app.channels.registry import get_channel_adapter, list_channel_adapters

__all__ = ["get_channel_adapter", "list_channel_adapters"]
