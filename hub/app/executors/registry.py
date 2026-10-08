from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.executors.base import ExecutorAdapter
from app.executors.handoff import DshQueueExecutor, HandoffExecutor


def _default_executors() -> dict[str, ExecutorAdapter]:
    return {
        "cursor": HandoffExecutor("cursor"),
        "trae": HandoffExecutor("trae"),
        "dsh": DshQueueExecutor(),
        # 同协议 IDE：HANDOFF + wake，避免厂商锁死
        "continue": HandoffExecutor("continue"),
        "opencode": HandoffExecutor("opencode"),
    }


_REGISTRY: dict[str, ExecutorAdapter] = _default_executors()


def register_executor(adapter: ExecutorAdapter) -> None:
    _REGISTRY[adapter.name] = adapter


def get_executor(agent_id: str) -> ExecutorAdapter:
    adapter = _REGISTRY.get(agent_id)
    if not adapter:
        # 未知 IDE：回退 Handoff 协议，避免硬绑厂商
        adapter = HandoffExecutor(agent_id)
        _REGISTRY[agent_id] = adapter
    return adapter


def list_executors() -> list[dict[str, str]]:
    return [
        {"name": a.name, "transport": a.transport}
        for a in _REGISTRY.values()
    ]


class ExecutionSupervisor:
    """任务超时熔断：跟踪活跃执行，超时 git 还原 + 飞书告警。"""

    def __init__(
        self,
        home: Path,
        *,
        timeout_seconds: int | None = None,
        rollback_enabled: bool | None = None,
    ) -> None:
        self.home = home
        self.state_path = home / "active-executions.json"
        self.timeout_seconds = timeout_seconds or int(
            os.environ.get("UNIFIER_EXEC_TIMEOUT_SECONDS", "300")
        )
        self.rollback_enabled = (
            rollback_enabled
            if rollback_enabled is not None
            else os.environ.get("UNIFIER_EXEC_ROLLBACK", "1") == "1"
        )

    def _load(self) -> dict[str, Any]:
        if not self.state_path.is_file():
            return {}
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _save(self, data: dict[str, Any]) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @staticmethod
    def _key(agent_id: str, item: dict[str, Any]) -> str:
        return f"{agent_id}:{item.get('kind')}:{item['task_id']}"

    def register(
        self,
        hub: str,
        device_id: str,
        agent_id: str,
        item: dict[str, Any],
        *,
        workspace_path: str | Path | None = None,
    ) -> None:
        data = self._load()
        key = self._key(agent_id, item)
        data[key] = {
            "task_id": item["task_id"],
            "kind": item.get("kind"),
            "agent_id": agent_id,
            "device_id": device_id,
            "hub_url": hub.rstrip("/"),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "workspace_path": str(workspace_path) if workspace_path else None,
            "project": item.get("project"),
            "title": item.get("title"),
        }
        self._save(data)

    def _git_rollback(self, workspace: str | None) -> str:
        if not self.rollback_enabled or not workspace:
            return "skip"
        root = Path(workspace).expanduser()
        if not (root / ".git").is_dir():
            return "no_git"
        try:
            subprocess.run(
                ["git", "checkout", "--", "."],
                cwd=str(root),
                check=False,
                capture_output=True,
                timeout=60,
            )
            subprocess.run(
                ["git", "clean", "-fd"],
                cwd=str(root),
                check=False,
                capture_output=True,
                timeout=60,
            )
            return "ok"
        except Exception as e:
            return f"fail:{e}"

    def _api_post(self, url: str, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30):
            pass

    def _abort_one(self, key: str, rec: dict[str, Any]) -> None:
        hub = rec["hub_url"]
        tid = rec["task_id"]
        agent = rec["agent_id"]
        device = rec["device_id"]
        rollback = self._git_rollback(rec.get("workspace_path"))
        msg = (
            f"⛔ 任务 #{tid} 执行超时（>{self.timeout_seconds}s）已熔断\n"
            f"标题：{rec.get('title') or '—'}\n"
            f"执行端：{device}/{agent}\n"
            f"工作区回滚：{rollback}\n"
            f"请检查 HANDOFF 后重新派活。"
        )
        try:
            self._api_post(
                f"{hub}/api/v1/tasks/{tid}/execution-abort",
                {
                    "device_id": device,
                    "agent_id": agent,
                    "reason": "execution_timeout",
                    "rollback_status": rollback,
                    "timeout_seconds": self.timeout_seconds,
                },
            )
        except urllib.error.HTTPError:
            # Hub 旧版无 endpoint 时仍推飞书
            self._api_post(
                f"{hub}/api/v1/tasks/{tid}/agent-replies",
                {
                    "device_id": device,
                    "agent_id": agent,
                    "content": msg,
                    "source": "execution-supervisor",
                    "notify_feishu": True,
                },
            )
        except Exception:
            pass

    def check_timeouts(self) -> list[str]:
        """返回已熔断的 task key 列表。"""
        data = self._load()
        if not data:
            return []
        now = datetime.now(timezone.utc)
        fired: list[str] = []
        remaining = dict(data)
        for key, rec in data.items():
            started = datetime.fromisoformat(rec["started_at"])
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            elapsed = (now - started).total_seconds()
            if elapsed < self.timeout_seconds:
                continue
            self._abort_one(key, rec)
            fired.append(key)
            remaining.pop(key, None)
        if fired:
            self._save(remaining)
        return fired

    def complete(self, agent_id: str, item: dict[str, Any]) -> None:
        data = self._load()
        key = self._key(agent_id, item)
        if key in data:
            del data[key]
            self._save(data)
