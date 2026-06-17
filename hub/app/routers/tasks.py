from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Manifest, Project, Task, utcnow
from app.schemas import (
    AgentReplyOut,
    AgentReplySubmit,
    InboxItem,
    ManifestOut,
    ManifestSubmit,
    MergeReadyOut,
    ReviewOut,
    ReviewSubmit,
    TaskAssign,
    TaskCreate,
    TaskOut,
    TaskStatusUpdate,
)
from app.services.inbox import inbox_items
from app.services.feishu_notify import notify_manifest, notify_review
from app.services.agent_replies import submit_agent_reply
from app.services.tasks import (
    apply_review_and_update_status,
    manifest_payload,
    review_summary,
    set_task_status,
)
from app.state_machine import InvalidTransitionError, TaskStatus

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


def _task_out(task: Task, db: Session) -> TaskOut:
    summary = review_summary(task, db)
    return TaskOut(
        id=task.id,
        project_id=task.project_id,
        title=task.title,
        description=task.description,
        branch=task.branch,
        status=task.status,
        assignee_device_id=task.assignee_device_id,
        assignee_agent_id=task.assignee_agent_id,
        required_reviewers=task.required_reviewers,
        merge_ready=summary["merge_ready"],
        review_summary=summary,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def _get_task_or_404(task_id: int, db: Session) -> Task:
    task = (
        db.query(Task)
        .options(
            joinedload(Task.reviews),
            joinedload(Task.manifests),
            joinedload(Task.agent_replies),
        )
        .filter(Task.id == task_id)
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.post("", response_model=TaskOut, status_code=201)
def create_task(body: TaskCreate, db: Session = Depends(get_db)):
    if not db.get(Project, body.project_id):
        raise HTTPException(status_code=404, detail="项目不存在")
    task = Task(
        project_id=body.project_id,
        title=body.title,
        description=body.description,
        branch=body.branch,
        status=TaskStatus.PLANNED.value,
    )
    task.required_reviewers = body.required_reviewers
    db.add(task)
    db.commit()
    db.refresh(task)
    return _task_out(task, db)


@router.get("/inbox", response_model=list[InboxItem])
def agent_inbox(
    device_id: str,
    agent_id: str,
    db: Session = Depends(get_db),
):
    """Device Agent 轮询：待执行或待审查的任务。"""
    return inbox_items(device_id, agent_id, db)


@router.get("", response_model=list[TaskOut])
def list_tasks(
    project_id: int | None = None,
    status: str | None = None,
    device_id: str | None = None,
    agent_id: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(Task).options(joinedload(Task.reviews))
    if project_id is not None:
        q = q.filter(Task.project_id == project_id)
    if status is not None:
        q = q.filter(Task.status == status)
    if device_id is not None:
        q = q.filter(Task.assignee_device_id == device_id)
    if agent_id is not None:
        q = q.filter(Task.assignee_agent_id == agent_id)
    tasks = q.order_by(Task.id.desc()).all()
    return [_task_out(t, db) for t in tasks]


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: int, db: Session = Depends(get_db)):
    return _task_out(_get_task_or_404(task_id, db), db)


@router.patch("/{task_id}/status", response_model=TaskOut)
def update_status(
    task_id: int, body: TaskStatusUpdate, db: Session = Depends(get_db)
):
    task = _get_task_or_404(task_id, db)
    try:
        set_task_status(task, body.status)
    except InvalidTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    task.updated_at = utcnow()
    db.commit()
    db.refresh(task)
    return _task_out(task, db)


@router.post("/{task_id}/assign", response_model=TaskOut)
def assign_task(task_id: int, body: TaskAssign, db: Session = Depends(get_db)):
    from app.models import Device

    task = _get_task_or_404(task_id, db)
    device = db.query(Device).filter(Device.device_id == body.device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备未注册")
    if body.agent_id not in device.agents and device.agents:
        raise HTTPException(
            status_code=400,
            detail=f"该设备登记的 agents 为 {device.agents}，不含 {body.agent_id}",
        )
    task.assignee_device_id = body.device_id
    task.assignee_agent_id = body.agent_id
    try:
        if TaskStatus(task.status) == TaskStatus.PLANNED:
            set_task_status(task, TaskStatus.ASSIGNED)
    except InvalidTransitionError:
        pass
    task.updated_at = utcnow()
    db.commit()
    db.refresh(task)
    return _task_out(task, db)


@router.post("/{task_id}/manifest", response_model=ManifestOut, status_code=201)
def submit_manifest(
    task_id: int, body: ManifestSubmit, db: Session = Depends(get_db)
):
    task = _get_task_or_404(task_id, db)
    manifest = Manifest(
        task_id=task.id,
        agent_id=body.agent_id,
        device_id=body.device_id,
        payload_json=json.dumps(body.payload, ensure_ascii=False),
    )
    db.add(manifest)
    if TaskStatus(task.status) in (TaskStatus.ASSIGNED, TaskStatus.PLANNED):
        try:
            set_task_status(task, TaskStatus.WORKING)
        except InvalidTransitionError:
            pass
    task.updated_at = utcnow()
    db.commit()
    db.refresh(manifest)
    db.refresh(task)
    summary = str(body.payload.get("summary", "已提交变更清单"))
    notify_manifest(task, body.device_id, body.agent_id, summary)
    from app.services.event_bus import emit_event

    emit_event(
        "task.manifest_submitted",
        task=task,
        db=db,
        extra={
            "agent_id": body.agent_id,
            "device_id": body.device_id,
            "summary": summary,
        },
    )
    return ManifestOut(
        id=manifest.id,
        task_id=manifest.task_id,
        agent_id=manifest.agent_id,
        device_id=manifest.device_id,
        payload=manifest_payload(manifest),
        submitted_at=manifest.submitted_at,
    )


@router.get("/{task_id}/manifests", response_model=list[ManifestOut])
def list_manifests(task_id: int, db: Session = Depends(get_db)):
    task = _get_task_or_404(task_id, db)
    return [
        ManifestOut(
            id=m.id,
            task_id=m.task_id,
            agent_id=m.agent_id,
            device_id=m.device_id,
            payload=manifest_payload(m),
            submitted_at=m.submitted_at,
        )
        for m in sorted(task.manifests, key=lambda x: x.submitted_at, reverse=True)
    ]


@router.post("/{task_id}/submit-review", response_model=TaskOut)
def submit_for_review(task_id: int, db: Session = Depends(get_db)):
    task = _get_task_or_404(task_id, db)
    if not task.required_reviewers:
        raise HTTPException(status_code=400, detail="未配置 required_reviewers")
    if not task.manifests:
        raise HTTPException(status_code=400, detail="请先提交至少一份 manifest")
    try:
        current = TaskStatus(task.status)
        if current == TaskStatus.WORKING:
            set_task_status(task, TaskStatus.REVIEW_PENDING)
        if TaskStatus(task.status) == TaskStatus.REVIEW_PENDING:
            set_task_status(task, TaskStatus.REVIEWING)
        elif current == TaskStatus.CHANGES_REQUESTED:
            set_task_status(task, TaskStatus.REVIEW_PENDING)
            set_task_status(task, TaskStatus.REVIEWING)
    except InvalidTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    task.updated_at = utcnow()
    db.commit()
    db.refresh(task)
    from app.services.event_bus import emit_event

    emit_event("task.review_started", task=task, db=db)
    return _task_out(task, db)
def submit_review(
    task_id: int, body: ReviewSubmit, db: Session = Depends(get_db)
):
    task = _get_task_or_404(task_id, db)
    if TaskStatus(task.status) not in (
        TaskStatus.REVIEW_PENDING,
        TaskStatus.REVIEWING,
        TaskStatus.CHANGES_REQUESTED,
    ):
        raise HTTPException(
            status_code=400,
            detail=f"当前状态 {task.status} 不接受审查投票",
        )
    try:
        if TaskStatus(task.status) == TaskStatus.REVIEW_PENDING:
            set_task_status(task, TaskStatus.REVIEWING)
        apply_review_and_update_status(
            task, db, body.reviewer_agent_id, body.status
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except InvalidTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    task.updated_at = utcnow()
    db.commit()
    db.refresh(task)
    from app.services.orchestrate import command_status
    from app.services.feishu_notify import notify_task_async

    summary = review_summary(task, db)
    notify_review(task, body.reviewer_agent_id, body.status, body.note)
    from app.services.event_bus import emit_event

    emit_event(
        "task.review_submitted",
        task=task,
        db=db,
        extra={
            "reviewer_agent_id": body.reviewer_agent_id,
            "review_status": body.status,
            "note": body.note,
        },
    )
    if summary["merge_ready"]:
        status = command_status(task, db)
        notify_task_async(task, "🎉 审查全票通过\n" + status["message"])
        emit_event("task.merge_ready", task=task, db=db)
    elif summary["rejected"]:
        emit_event("task.changes_requested", task=task, db=db)
    return _task_out(task, db)


@router.get("/{task_id}/reviews", response_model=list[ReviewOut])
def list_reviews(task_id: int, db: Session = Depends(get_db)):
    task = _get_task_or_404(task_id, db)
    return sorted(task.reviews, key=lambda r: r.reviewer_agent_id)


@router.get("/{task_id}/agent-replies", response_model=list[AgentReplyOut])
def list_agent_replies(task_id: int, db: Session = Depends(get_db)):
    task = _get_task_or_404(task_id, db)
    return sorted(task.agent_replies, key=lambda r: r.created_at, reverse=True)


@router.post("/{task_id}/agent-replies", response_model=AgentReplyOut, status_code=201)
def post_agent_reply(
    task_id: int, body: AgentReplySubmit, db: Session = Depends(get_db)
):
    """Cursor/Trae 回复上报到 Hub，并转发到飞书群。"""
    try:
        reply = submit_agent_reply(
            db,
            task_id,
            body.device_id,
            body.agent_id,
            body.content,
            source=body.source,
            notify_feishu=body.notify_feishu,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return reply


@router.get("/{task_id}/merge-ready", response_model=MergeReadyOut)
def merge_ready(task_id: int, db: Session = Depends(get_db)):
    task = _get_task_or_404(task_id, db)
    s = review_summary(task, db)
    return MergeReadyOut(
        task_id=task.id,
        status=task.status,
        merge_ready=s["merge_ready"],
        required_reviewers=s["required"],
        approvals=s["approvals"],
        pending=s["pending"],
        rejected=s["rejected"],
    )
