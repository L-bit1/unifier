"""自动化套件 API：内置工作流引擎 + 可选 n8n + 栈总览。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Workflow
from app.services.n8n_bridge import n8n_health, n8n_health_sync
from app.services.soul_bridge import stack_health

router = APIRouter(prefix="/api/v1/automation", tags=["automation"])


class N8nTestEventIn(BaseModel):
    event: str = "test.ping"
    data: dict[str, Any] = Field(default_factory=dict)


@router.get("/workflows/health")
def get_workflow_engine_health(db: Session = Depends(get_db)):
    """内置工作流引擎状态。"""
    total = db.query(Workflow).count()
    active = db.query(Workflow).filter(Workflow.active.is_(True)).count()
    return {
        "ok": settings.workflows_enabled,
        "enabled": settings.workflows_enabled,
        "editor_url": "/workflows/editor",
        "workflows_total": total,
        "workflows_active": active,
        "node_types": 13,
    }


@router.get("/n8n/health")
async def get_n8n_health():
    """可选 n8n Sidecar 状态（路线 A 遗留）。"""
    return await n8n_health()


@router.get("/stack")
async def get_stack_health(db: Session = Depends(get_db)):
    """Head 套件总览（Hub + 灵魂栈 + 内置工作流 + 可选 n8n）。"""
    stack = await stack_health()
    n8n = await n8n_health()
    wf_total = db.query(Workflow).count()
    wf_active = db.query(Workflow).filter(Workflow.active.is_(True)).count()

    components = dict(stack.get("components") or {})
    components["workflow_engine"] = {
        "ok": settings.workflows_enabled,
        "enabled": settings.workflows_enabled,
        "editor": "/workflows/editor",
        "workflows_total": wf_total,
        "workflows_active": wf_active,
    }
    components["n8n_automation"] = n8n

    overall = stack.get("overall", "ok")
    if settings.n8n_enabled and not n8n.get("ok"):
        overall = "degraded"

    return {
        "ok": overall == "ok",
        "overall": overall,
        "session_id": stack.get("session_id"),
        "components": components,
        "workflow_editor": "/workflows/editor",
        "n8n_webhook_url": settings.n8n_webhook_url or None,
    }


@router.get("/connectors")
def list_connectors(db: Session = Depends(get_db)):
    """已注册 Connector 列表。"""
    n8n = n8n_health_sync()
    wf_active = db.query(Workflow).filter(Workflow.active.is_(True)).count()
    return {
        "connectors": [
            {
                "id": "workflow_engine",
                "name": "内置工作流",
                "builtin": True,
                "enabled": settings.workflows_enabled,
                "ok": settings.workflows_enabled,
                "editor": "/workflows/editor",
                "active_workflows": wf_active,
            },
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
                "name": "n8n（可选 Sidecar）",
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
    """手动触发一条测试事件到 n8n Webhook（仅 N8N_ENABLED 时）。"""
    from app.services.n8n_bridge import emit_to_n8n

    _ = db
    result = await emit_to_n8n(body.event, body.data)
    return {
        "sent": result.get("ok", False),
        "webhook_url": settings.n8n_webhook_url or None,
        "result": result,
    }
