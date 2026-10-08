"""飞书 OA 审批对接骨架（P2 ToB）：回调入库 + 状态查询，审批定义需企业侧配置。"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.config import HUB_ROOT

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/feishu/oa", tags=["feishu-oa"])

_STORE = HUB_ROOT / "data" / "feishu_oa_approvals.jsonl"


class OAApprovalCreate(BaseModel):
    """发起审批占位：真实环境需调飞书 approval/v4/instances。"""
    task_id: int
    approval_code: str = Field(default="", description="飞书审批定义 code")
    comment: str = ""


@router.get("/status")
def oa_status():
    return {
        "ok": True,
        "implemented": "skeleton",
        "message": (
            "OA 审批骨架已就绪：可收回调、可本地落盘。"
            "企业启用时需配置 FEISHU 审批定义 + 事件订阅指向 "
            "POST /api/v1/feishu/oa/callbacks"
        ),
        "callback_path": "/api/v1/feishu/oa/callbacks",
        "store": str(_STORE),
    }


@router.post("/instances")
def create_oa_instance(body: OAApprovalCreate):
    """占位创建：写入本地队列，不调飞书（避免无权限误调）。"""
    rec = {
        "task_id": body.task_id,
        "approval_code": body.approval_code,
        "comment": body.comment,
        "status": "local_queued",
    }
    _append(rec)
    return {"ok": True, "instance": rec, "note": "需配置审批定义后改为真实 OpenAPI"}


@router.post("/callbacks")
async def oa_callback(request: Request):
    """飞书审批事件回调（challenge + 审批实例状态变更）。"""
    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        payload = {}

    # URL 校验
    if payload.get("type") == "url_verification" or "challenge" in payload:
        return {"challenge": payload.get("challenge", "")}

    _append({"event": "callback", "payload": payload})
    logger.info("feishu oa callback stored keys=%s", list(payload.keys()))
    return {"ok": True}


@router.get("/recent")
def oa_recent(limit: int = 20):
    if not _STORE.is_file():
        return {"count": 0, "items": []}
    lines = _STORE.read_text(encoding="utf-8").strip().splitlines()
    items = []
    for line in lines[-max(1, min(limit, 100)) :]:
        try:
            items.append(json.loads(line))
        except Exception:
            continue
    return {"count": len(items), "items": list(reversed(items))}


def _append(rec: dict[str, Any]) -> None:
    _STORE.parent.mkdir(parents=True, exist_ok=True)
    with _STORE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
