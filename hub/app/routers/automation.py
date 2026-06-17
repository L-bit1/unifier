"""自动化套件 API：n8n 健康、栈总览、入站 Webhook 测试。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.services.n8n_bridge import n8n_health, n8n_health_sync
from app.services.soul_bridge import stack_health, stack_health_sync

router = APIRouter(prefix="/api/v1/automation", tags=["automation"])


class N8nTestEventIn(BaseModel):
    event: str = "test.ping"
    data: dict[str, Any] = Field(default_factory=dict)


@router.get("/n8n/health")
async def get_n8n_health():
    """n8n 自动化引擎在线状态。"""
    return await n8n_health()


@router.get("/stack")
async def get_stack_health():
    """Head 套件总览（Hub + 灵魂栈 + n8n），类似 NAS 控制面板。"""
    stack = await stack_health()
    n8n = await n8n_health()
    components = dict(stack.get("components") or {})
    components["n8n_automation"] = n8n

    overall = stack.get("overall", "ok")
    if settings.n8n_enabled and not n8n.get("ok"):
        overall = "degraded"

    return {
        "ok": overall == "ok",
        "overall": overall,
        "session_id": stack.get("session_id"),
        "components": components,
        "n8n_webhook_url": settings.n8n_webhook_url or None,
    }


@router.get("/connectors")
def list_connectors():
    """已注册 Connector 列表（内置 + 可选套件）。"""
    n8n = n8n_health_sync()
    return {
        "connectors": [
            {
                "id": "feishu",
                "name": "飞书指挥台",
                "builtin": True,
                "enabled": settings.feishu_configured,
            },
            {
                "id": "device_agent",
                "name": "Device Agent",
                "builtin": True,
                "enabled": True,
            },
            {
                "id": "soul",
                "name": "自研AI 灵魂栈",
                "builtin": True,
                "enabled": True,
                "url": settings.custom_ai_url,
            },
            {
                "id": "n8n",
                "name": "n8n 自动化",
                "builtin": False,
                "enabled": settings.n8n_enabled,
                "ok": n8n.get("ok", False),
                "url": settings.n8n_url,
                "webhook_url": settings.n8n_webhook_url or None,
            },
        ]
    }


@router.post("/n8n/test-event")
async def test_n8n_event(body: N8nTestEventIn, db: Session = Depends(get_db)):
    """手动触发一条测试事件到 n8n Webhook（调试用）。"""
    from app.services.n8n_bridge import emit_to_n8n

    _ = db  # 预留：未来可按 task_id 加载任务
    result = await emit_to_n8n(body.event, body.data)
    return {
        "sent": result.get("ok", False),
        "webhook_url": settings.n8n_webhook_url or None,
        "result": result,
    }
