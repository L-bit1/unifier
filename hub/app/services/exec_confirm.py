"""P1 半自动：手机/飞书确认后再唤醒执行。"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def unifier_home() -> Path:
    return Path(os.environ.get("UNIFIER_HOME", Path.home() / ".unifier"))


def confirm_root() -> Path:
    root = unifier_home() / "exec-confirm"
    for name in ("pending", "confirmed", "deferred"):
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def confirm_exec_enabled() -> bool:
    return os.environ.get("UNIFIER_CONFIRM_EXEC", "1") not in ("0", "false", "False")


def _path(bucket: str, task_id: int) -> Path:
    return confirm_root() / bucket / f"{task_id}.json"


def _read(bucket: str, task_id: int) -> dict[str, Any] | None:
    p = _path(bucket, task_id)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write(bucket: str, task_id: int, data: dict[str, Any]) -> Path:
    p = _path(bucket, task_id)
    data = {**data, "updated_at": datetime.now(timezone.utc).isoformat()}
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def _clear_others(task_id: int, keep: str) -> None:
    for name in ("pending", "confirmed", "deferred"):
        if name == keep:
            continue
        p = _path(name, task_id)
        if p.is_file():
            p.unlink(missing_ok=True)


def request_confirm(
    *,
    task_id: int,
    device_id: str,
    agent_id: str,
    item: dict[str, Any],
) -> dict[str, Any]:
    data = {
        "task_id": task_id,
        "device_id": device_id,
        "agent_id": agent_id,
        "item": item,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _write("pending", task_id, data)
    _clear_others(task_id, "pending")
    return data


def confirm_task(task_id: int) -> dict[str, Any]:
    data = _read("pending", task_id) or _read("deferred", task_id)
    if not data:
        raise ValueError(f"任务 #{task_id} 不在待确认/稍后队列")
    data["status"] = "confirmed"
    data["confirmed_at"] = datetime.now(timezone.utc).isoformat()
    _write("confirmed", task_id, data)
    _clear_others(task_id, "confirmed")
    return data


def defer_task(task_id: int) -> dict[str, Any]:
    data = _read("pending", task_id) or _read("confirmed", task_id)
    if not data:
        # 允许从 inbox 直接稍后：造空壳
        raise ValueError(f"任务 #{task_id} 不在待确认队列")
    data["status"] = "deferred"
    data["deferred_at"] = datetime.now(timezone.utc).isoformat()
    _write("deferred", task_id, data)
    _clear_others(task_id, "deferred")
    return data


def list_pending(device_id: str | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in sorted((confirm_root() / "pending").glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if device_id and data.get("device_id") != device_id:
            continue
        out.append(data)
    return out


def list_confirmed(device_id: str | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in sorted((confirm_root() / "confirmed").glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if device_id and data.get("device_id") != device_id:
            continue
        out.append(data)
    return out


def pop_confirmed(task_id: int) -> dict[str, Any] | None:
    data = _read("confirmed", task_id)
    if data:
        _path("confirmed", task_id).unlink(missing_ok=True)
    return data


def build_confirm_card(task_id: int, title: str, agent_id: str) -> dict:
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"任务 #{task_id} 待确认执行"},
            "template": "blue",
        },
        "elements": [
            {
                "tag": "markdown",
                "content": (
                    f"**{title or '(无标题)'}**\n"
                    f"执行端：`{agent_id}`\n\n"
                    "点「确认执行」后电脑才会唤醒 Cursor/Trae；点「稍后」进入队列。"
                ),
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "确认执行"},
                        "type": "primary",
                        "value": {"action": "confirm_exec", "task_id": task_id},
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "稍后"},
                        "type": "default",
                        "value": {"action": "defer_exec", "task_id": task_id},
                    },
                ],
            },
        ],
    }
