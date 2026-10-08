from __future__ import annotations

from abc import ABC, abstractmethod

from app.executors.types import DispatchResult, ExecutionContext


class ExecutorAdapter(ABC):
    """执行器接口：Handoff / DSH Queue / Shell Hook / 未来 Continue 等。"""

    name: str
    transport: str  # handoff | dsh_queue | mcp | shell

    @abstractmethod
    def dispatch(self, ctx: ExecutionContext) -> DispatchResult:
        """将任务投递到本机执行端。"""

    def supports(self, agent_id: str) -> bool:
        return agent_id == self.name
