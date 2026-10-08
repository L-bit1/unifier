from __future__ import annotations

from app.channels.base import ChannelAdapter
from app.channels.feishu import FeishuChannelAdapter

_ADAPTERS: dict[str, ChannelAdapter] = {
    "feishu": FeishuChannelAdapter(),
}


def get_channel_adapter(name: str) -> ChannelAdapter:
    adapter = _ADAPTERS.get(name)
    if not adapter:
        raise KeyError(f"未知通道: {name}，已注册: {list(_ADAPTERS)}")
    return adapter


def list_channel_adapters() -> list[str]:
    return list(_ADAPTERS.keys())
