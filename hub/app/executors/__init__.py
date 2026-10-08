"""IDE / Agent 执行端适配层（Cursor MCP、Trae、DSH、Shell Hook 等）。"""
from app.executors.registry import get_executor, list_executors

__all__ = ["get_executor", "list_executors"]
