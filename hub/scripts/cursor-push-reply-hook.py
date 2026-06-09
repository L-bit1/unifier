#!/usr/bin/env python3
"""Cursor Hook：agent 回合结束后自动把回复推送到飞书（经 Hub agent-replies）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# 允许从项目根或 hub/scripts 调用
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from reply_push_lib import (  # noqa: E402
    extract_text_from_transcript,
    try_push_reply,
)


def _log(msg: str) -> None:
    print(msg, file=sys.stderr)


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        _log("[unifier-hook] stdin 非 JSON，跳过")
        print("{}")
        return 0

    event = payload.get("hook_event_name", "")
    status = payload.get("status", "completed")

    text = ""
    if event == "afterAgentResponse":
        text = (payload.get("text") or "").strip()
    elif event == "stop":
        if status != "completed":
            print("{}")
            return 0
        transcript = payload.get("transcript_path")
        if transcript:
            text = extract_text_from_transcript(transcript)
    else:
        print("{}")
        return 0

    if not text:
        print("{}")
        return 0

    ok, msg = try_push_reply(text, source=f"cursor-hook:{event}")
    if ok:
        _log(f"[unifier-hook] {msg}")
    else:
        _log(f"[unifier-hook] 跳过: {msg}")

    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
