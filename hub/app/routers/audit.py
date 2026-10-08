from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import (
    ManifestAuditItem,
    ManifestAuditSearchOut,
    TaskManifestDiffOut,
)
from app.services.manifests import compare_task_manifests, search_manifests

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


@router.get("/manifests", response_model=ManifestAuditSearchOut)
def audit_search_manifests(
    q: str | None = Query(default=None, description="关键词：意图、思维链、摘要、任务标题"),
    channel: str | None = Query(default=None, description="来源通道，如 feishu"),
    task_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """意图记忆检索：按关键词搜索 ChangeManifest 及关联任务上下文。"""
    rows = search_manifests(db, q=q, channel=channel, task_id=task_id, limit=limit)
    items = [ManifestAuditItem(**row) for row in rows]
    return ManifestAuditSearchOut(q=q, channel=channel, count=len(items), items=items)


@router.get("/tasks/{task_id}/manifest-diff", response_model=TaskManifestDiffOut)
def audit_task_manifest_diff(task_id: int, db: Session = Depends(get_db)):
    """双/多 Agent manifest 差异报告（按 agent 取最新一份交叉比对）。"""
    data = compare_task_manifests(db, task_id)
    if not data.get("found"):
        raise HTTPException(status_code=404, detail="任务不存在")
    return TaskManifestDiffOut(**data)
