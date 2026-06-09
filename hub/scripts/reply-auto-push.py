#!/usr/bin/env python3
"""Trae / 备用：监听 Cursor transcript，自动推送 AI 回复到飞书。"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from reply_push_lib import (  # noqa: E402
    extract_text_from_transcript,
    read_active_task,
    try_push_reply,
)


def default_transcript_roots() -> list[Path]:
    roots: list[Path] = []
    cursor_projects = Path.home() / ".cursor" / "projects"
    if cursor_projects.is_dir():
        roots.append(cursor_projects)
    trae_dir = os.environ.get("UNIFIER_TRAE_TRANSCRIPT_DIR")
    if trae_dir:
        roots.append(Path(trae_dir))
    extra = os.environ.get("UNIFIER_TRANSCRIPT_DIRS", "")
    for part in extra.split(":"):
        if part.strip():
            roots.append(Path(part.strip()))
    return roots


def latest_transcript(roots: list[Path], workspace_hint: str = "") -> Path | None:
    candidates: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*.jsonl"):
            if "/subagents/" in str(path):
                continue
            if workspace_hint and workspace_hint not in str(path):
                # 弱过滤：联合器路径含「联合器」
                if "联合器" not in str(path) and workspace_hint not in str(path):
                    continue
            candidates.append(path)
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def poll_once(roots: list[Path], workspace_hint: str) -> tuple[bool, str]:
    if not read_active_task():
        return False, "无 active-task"
    transcript = latest_transcript(roots, workspace_hint)
    if not transcript:
        return False, "未找到 transcript"
    text = extract_text_from_transcript(transcript)
    return try_push_reply(text, source="auto-push-daemon")


def main() -> int:
    parser = argparse.ArgumentParser(description="联合器 AI 回复自动推送守护")
    parser.add_argument("--interval", type=int, default=8)
    parser.add_argument("--once", action="store_true")
    parser.add_argument(
        "--workspace-hint",
        default=os.environ.get("UNIFIER_WORKSPACE_HINT", "联合器"),
    )
    args = parser.parse_args()

    roots = default_transcript_roots()
    print(
        f"reply-auto-push 启动 interval={args.interval}s roots={[str(r) for r in roots]}",
        file=sys.stderr,
    )

    while True:
        ok, msg = poll_once(roots, args.workspace_hint)
        if ok:
            print(f"[push] {msg}", file=sys.stderr)
        if args.once:
            print(msg, file=sys.stderr)
            break
        time.sleep(args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
