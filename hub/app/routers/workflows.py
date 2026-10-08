from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import HUB_ROOT, settings
from app.database import get_db
from app.models import Workflow, WorkflowRun, utcnow
from app.services.workflow_engine import (
    execute_workflow,
    parse_graph,
    run_workflow_by_id,
    sync_workflow_meta,
    trigger_webhook,
)
from app.services.workflow_nodes import NODE_CATALOG
from app.services.workflow_presets import import_presets
from app.services.workflow_scheduler import reload_schedules

router = APIRouter(tags=["workflows"])


class WorkflowGraphIn(BaseModel):
    version: int = 1
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)


class WorkflowCreate(BaseModel):
    name: str
    description: str | None = None
    graph: WorkflowGraphIn
    active: bool = False


class WorkflowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    graph: WorkflowGraphIn | None = None
    active: bool | None = None


class WorkflowOut(BaseModel):
    id: int
    name: str
    description: str | None
    graph: dict[str, Any]
    active: bool
    trigger_kind: str
    hook_id: str | None
    schedule_cron: str | None
    preset_key: str | None
    webhook_url: str | None = None

    model_config = {"from_attributes": True}


class WorkflowRunOut(BaseModel):
    id: int
    workflow_id: int
    status: str
    trigger_type: str
    trigger_event: str | None
    error: str | None
    started_at: Any
    finished_at: Any | None


def _workflow_out(wf: Workflow, request: Request | None = None) -> WorkflowOut:
    base = ""
    if request is not None:
        base = str(request.base_url).rstrip("/")
    webhook_url = None
    if wf.hook_id and base:
        webhook_url = f"{base}/api/v1/workflows/hooks/{wf.hook_id}"
    return WorkflowOut(
        id=wf.id,
        name=wf.name,
        description=wf.description,
        graph=parse_graph(wf.graph_json),
        active=wf.active,
        trigger_kind=wf.trigger_kind,
        hook_id=wf.hook_id,
        schedule_cron=wf.schedule_cron,
        preset_key=wf.preset_key,
        webhook_url=webhook_url,
    )


@router.get("/workflows/editor", response_class=HTMLResponse)
def workflow_editor():
    path = HUB_ROOT / "static" / "workflow-editor.html"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="编辑器页面不存在")
    return HTMLResponse(path.read_text(encoding="utf-8"))


@router.get("/api/v1/workflows/nodes")
def list_node_catalog():
    return {"nodes": NODE_CATALOG, "count": len(NODE_CATALOG)}


@router.get("/api/v1/workflows", response_model=list[WorkflowOut])
def list_workflows(request: Request, db: Session = Depends(get_db)):
    items = db.query(Workflow).order_by(Workflow.id.desc()).all()
    return [_workflow_out(w, request) for w in items]


@router.post("/api/v1/workflows", response_model=WorkflowOut, status_code=201)
def create_workflow(body: WorkflowCreate, request: Request, db: Session = Depends(get_db)):
    wf = Workflow(
        name=body.name,
        description=body.description,
        graph_json=json.dumps(body.graph.model_dump(), ensure_ascii=False),
        active=body.active,
    )
    sync_workflow_meta(wf)
    db.add(wf)
    db.commit()
    db.refresh(wf)
    reload_schedules()
    return _workflow_out(wf, request)


@router.get("/api/v1/workflows/{workflow_id}", response_model=WorkflowOut)
def get_workflow(workflow_id: int, request: Request, db: Session = Depends(get_db)):
    wf = db.get(Workflow, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="工作流不存在")
    return _workflow_out(wf, request)


@router.put("/api/v1/workflows/{workflow_id}", response_model=WorkflowOut)
def update_workflow(
    workflow_id: int,
    body: WorkflowUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    wf = db.get(Workflow, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="工作流不存在")
    if body.name is not None:
        wf.name = body.name
    if body.description is not None:
        wf.description = body.description
    if body.graph is not None:
        wf.graph_json = json.dumps(body.graph.model_dump(), ensure_ascii=False)
        sync_workflow_meta(wf)
    if body.active is not None:
        wf.active = body.active
    wf.updated_at = utcnow()
    db.commit()
    db.refresh(wf)
    reload_schedules()
    return _workflow_out(wf, request)


@router.delete("/api/v1/workflows/{workflow_id}", status_code=204)
def delete_workflow(workflow_id: int, db: Session = Depends(get_db)):
    wf = db.get(Workflow, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="工作流不存在")
    db.delete(wf)
    db.commit()
    reload_schedules()


@router.post("/api/v1/workflows/{workflow_id}/activate", response_model=WorkflowOut)
def activate_workflow(workflow_id: int, request: Request, db: Session = Depends(get_db)):
    wf = db.get(Workflow, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="工作流不存在")
    wf.active = True
    wf.updated_at = utcnow()
    db.commit()
    db.refresh(wf)
    reload_schedules()
    return _workflow_out(wf, request)


@router.post("/api/v1/workflows/{workflow_id}/deactivate", response_model=WorkflowOut)
def deactivate_workflow(workflow_id: int, request: Request, db: Session = Depends(get_db)):
    wf = db.get(Workflow, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="工作流不存在")
    wf.active = False
    wf.updated_at = utcnow()
    db.commit()
    db.refresh(wf)
    reload_schedules()
    return _workflow_out(wf, request)


class ManualRunIn(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


@router.post("/api/v1/workflows/{workflow_id}/run", response_model=WorkflowRunOut)
def manual_run_workflow(
    workflow_id: int,
    body: ManualRunIn | None = None,
    db: Session = Depends(get_db),
):
    wf = db.get(Workflow, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="工作流不存在")
    run = execute_workflow(
        db,
        wf,
        event_type="manual.run",
        event_data=(body.payload if body else {}) or {},
        trigger="manual",
    )
    return WorkflowRunOut(
        id=run.id,
        workflow_id=run.workflow_id,
        status=run.status,
        trigger_type=run.trigger_type,
        trigger_event=run.trigger_event,
        error=run.error,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


@router.get("/api/v1/workflows/{workflow_id}/runs", response_model=list[WorkflowRunOut])
def list_workflow_runs(workflow_id: int, db: Session = Depends(get_db)):
    if not db.get(Workflow, workflow_id):
        raise HTTPException(status_code=404, detail="工作流不存在")
    runs = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.workflow_id == workflow_id)
        .order_by(WorkflowRun.id.desc())
        .limit(50)
        .all()
    )
    return [
        WorkflowRunOut(
            id=r.id,
            workflow_id=r.workflow_id,
            status=r.status,
            trigger_type=r.trigger_type,
            trigger_event=r.trigger_event,
            error=r.error,
            started_at=r.started_at,
            finished_at=r.finished_at,
        )
        for r in runs
    ]


@router.post("/api/v1/workflows/hooks/{hook_id}")
async def workflow_webhook(hook_id: str, request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {"body": payload}
    runs = trigger_webhook(hook_id, payload)
    if not runs:
        raise HTTPException(status_code=404, detail="未找到使用该 hook 的激活工作流")
    return {
        "ok": True,
        "runs": [
            {"id": r.id, "workflow_id": r.workflow_id, "status": r.status}
            for r in runs
        ],
    }


@router.post("/api/v1/workflows/import-presets")
def import_preset_workflows(
    request: Request,
    activate: bool = False,
    db: Session = Depends(get_db),
):
    imported = import_presets(db, activate=activate)
    return {
        "imported": len(imported),
        "workflows": [_workflow_out(w, request) for w in imported],
    }
