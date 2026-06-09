#!/usr/bin/env python3
"""飞书卡片回调桥：lark-oapi 长连接收 card.action.trigger → Hub 处理 → 回传 toast/更新卡片。"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

from lark_oapi.core.const import FEISHU_DOMAIN
from lark_oapi.core.enum import LogLevel
from lark_oapi.core.json import JSON
from lark_oapi.event.callback.model.p2_card_action_trigger import (
    P2CardActionTrigger,
    P2CardActionTriggerResponse,
)
from lark_oapi.event.dispatcher_handler import EventDispatcherHandler
from lark_oapi.ws import Client


def post_card_action(hub_url: str, payload: dict) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{hub_url.rstrip('/')}/api/v1/feishu/card-actions",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    hub_url = os.environ.get("HUB_URL", "http://127.0.0.1:8787")
    app_id = os.environ.get("FEISHU_APP_ID") or os.environ.get("LARK_APP_ID")
    app_secret = os.environ.get("FEISHU_APP_SECRET") or os.environ.get("LARK_APP_SECRET")
    if not app_id or not app_secret:
        print(
            "请设置 FEISHU_APP_ID / FEISHU_APP_SECRET（或 LARK_APP_ID / LARK_APP_SECRET）",
            file=sys.stderr,
        )
        return 1

    def on_card_action(event: P2CardActionTrigger) -> P2CardActionTriggerResponse:
        payload = JSON.unmarshal(JSON.marshal(event), dict)
        try:
            result = post_card_action(hub_url, payload)
            print(
                f"[card] chat={getattr(getattr(event.event, 'context', None), 'open_chat_id', '?')} "
                f"→ {result.get('toast', {}).get('content', 'ok')}",
                file=sys.stderr,
            )
            return P2CardActionTriggerResponse(result)
        except urllib.error.URLError as e:
            print(f"[err] Hub 不可达: {e}", file=sys.stderr)
            return P2CardActionTriggerResponse(
                {"toast": {"type": "error", "content": "Hub 不可达，请检查 Hub 是否运行"}}
            )

    handler = (
        EventDispatcherHandler.builder("", "")
        .register_p2_card_action_trigger(on_card_action)
        .build()
    )
    client = Client(
        app_id,
        app_secret,
        log_level=LogLevel.INFO,
        event_handler=handler,
        domain=FEISHU_DOMAIN,
    )
    print(f"飞书卡片回调桥启动 → {hub_url}", file=sys.stderr)
    print("请在飞书开放平台「回调配置」启用：使用长连接接收回调 + 卡片回传交互", file=sys.stderr)
    client.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
