from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ExecutionContext:
    """派发到执行端的上下文。"""

    hub_url: str
    device_id: str
    agent_id: str
    item: dict[str, Any]
    home: Path
    handoff_path: Path | None = None
    workspace_path: Path | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class DispatchResult:
    """执行端投递结果。"""

    agent_id: str
    handoff_path: Path | None = None
    wake_path: Path | None = None
    queue_path: Path | None = None
    artifacts: dict[str, str] = field(default_factory=dict)
    message: str = ""
