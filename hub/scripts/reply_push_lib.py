from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def unifier_home() -> Path:
    return Path(os.environ.get("UNIFIER_HOME", Path.home() / ".unifier"))


def hub_url() -> str:
    return os.environ.get("HUB_URL", "http://127.0.0.1:8787").rstrip("/")


def device_id() -> str:
    return os.environ.get("UNIFIER_DEVICE_ID", os.environ.get("DEVICE_ID", ""))


def agent_id() -> str:
    return os.environ.get("UNIFIER_AGENT_ID", os.environ.get("AGENT_ID", "cursor"))


def auto_push_enabled() -> bool:
    return os.environ.get("UNIFIER_AUTO_PUSH", "1") not in ("0", "false", "False")


def min_chars() -> int:
    return int(os.environ.get("UNIFIER_PUSH_MIN_CHARS", "80"))


def max_chars() -> int:
    return int(os.environ.get("UNIFIER_PUSH_MAX_CHARS", "3500"))


def active_task_file() -> Path:
    return unifier_home() / "active-task.json"


def push_state_file() -> Path:
    return unifier_home() / "push-state.json"


def write_active_task(
    task_id: int,
    *,
    kind: str,
    title: str,
    device: str | None = None,
    agent: str | None = None,
) -> None:
    home = unifier_home()
    home.mkdir(parents=True, exist_ok=True)
    payload = {
        "task_id": task_id,
        "kind": kind,
        "title": title,
        "device_id": device or device_id(),
        "agent_id": agent or agent_id(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    active_task_file().write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def read_active_task() -> dict[str, Any] | None:
    path = active_task_file()
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _content_hash(task_id: int, text: str) -> str:
    return hashlib.sha256(f"{task_id}:{text}".encode("utf-8")).hexdigest()[:16]


def already_pushed(task_id: int, text: str) -> bool:
    path = push_state_file()
    if not path.is_file():
        return False
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    return (
        state.get("task_id") == task_id
        and state.get("last_hash") == _content_hash(task_id, text)
    )


def mark_pushed(task_id: int, text: str) -> None:
    unifier_home().mkdir(parents=True, exist_ok=True)
    push_state_file().write_text(
        json.dumps(
            {
                "task_id": task_id,
                "last_hash": _content_hash(task_id, text),
                "last_pushed_at": datetime.now(timezone.utc).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def extract_text_from_transcript(transcript_path: str | Path) -> str:
    path = Path(transcript_path)
    if not path.is_file():
        return ""

    texts: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("role") != "assistant":
            continue
        message = row.get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            texts.append(content)
            continue
        if not isinstance(content, list):
            continue
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and block.get("text"):
                parts.append(str(block["text"]))
        if parts:
            texts.append("\n".join(parts))

    if not texts:
        return ""
    return texts[-1].strip()


def normalize_reply_text(text: str) -> str:
    text = text.strip()
    text = re.sub(r"\[REDACTED\]", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > max_chars():
        text = text[: max_chars() - 20] + "\n\n…（已截断）"
    return text


def push_agent_reply(
    task_id: int,
    content: str,
    *,
    dev: str | None = None,
    ag: str | None = None,
    source: str = "auto-push",
) -> dict[str, Any]:
    d = dev or device_id()
    a = ag or agent_id()
    if not d:
        raise ValueError("UNIFIER_DEVICE_ID 未设置")
    payload = {
        "device_id": d,
        "agent_id": a,
        "content": content,
        "source": source,
        "notify_feishu": True,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{hub_url()}/api/v1/tasks/{task_id}/agent-replies",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body else {}


def try_push_reply(
    text: str,
    *,
    source: str = "auto-push",
    force: bool = False,
) -> tuple[bool, str]:
    if not auto_push_enabled():
        return False, "UNIFIER_AUTO_PUSH 已关闭"
    if not text or len(text.strip()) < min_chars():
        return False, f"回复过短（<{min_chars()} 字），跳过"

    active = read_active_task()
    if not active or not active.get("task_id"):
        return False, "无 active-task（请先收到联合器 inbox 任务）"

    task_id = int(active["task_id"])
    content = normalize_reply_text(text)
    if not content:
        return False, "正文为空"

    if not force and already_pushed(task_id, content):
        return False, "相同内容已推送过"

    try:
        push_agent_reply(
            task_id,
            content,
            dev=active.get("device_id"),
            ag=active.get("agent_id"),
            source=source,
        )
    except urllib.error.URLError as e:
        return False, f"Hub 不可达: {e}"

    mark_pushed(task_id, content)
    return True, f"已推送 task #{task_id} → 飞书"
