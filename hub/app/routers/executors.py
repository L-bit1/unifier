from __future__ import annotations

from fastapi import APIRouter

from app.executors.registry import list_executors

router = APIRouter(prefix="/api/v1/executors", tags=["executors"])


@router.get("")
def list_registered_executors():
    """已注册执行器（Cursor/Trae/DSH 等）及传输协议。"""
    return {"executors": list_executors()}
