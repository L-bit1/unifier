#!/usr/bin/env python3
"""飞书长连接桥：lark-cli 收事件 → Hub /api/v1/feishu/events → Bot 回复群。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request


def post_event(hub_url: str, event: dict) -> dict:
    data = json.dumps(event, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{hub_url.rstrip('/')}/api/v1/feishu/events",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    hub_url = os.environ.get("HUB_URL", "http://127.0.0.1:8787")
    cmd = [
        "lark-cli",
        "event",
        "+subscribe",
        "--event-types",
        "im.message.receive_v1",
        "--compact",
        "--quiet",
    ]
    print(f"飞书桥接启动 → {hub_url}", file=sys.stderr)
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            print(f"[skip] 非 JSON: {line[:80]}", file=sys.stderr)
            continue
        try:
            result = post_event(hub_url, event)
            if result.get("handled"):
                print(
                    f"[ok] {event.get('message_id')} → {result.get('reply', '')[:60]}",
                    file=sys.stderr,
                )
        except urllib.error.URLError as e:
            print(f"[err] Hub 不可达: {e}", file=sys.stderr)
    return proc.wait()


if __name__ == "__main__":
    raise SystemExit(main())
