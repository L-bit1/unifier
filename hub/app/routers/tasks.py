from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Manifest, Project, Task, utcnow
from app.schemas import (
    AgentReplyOut,
    AgentReplySubmit,
    ExecutionAbortBody,
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
from app.services.manifests import manifest_payload, resolve_manifest_fields
from app.services.tasks import apply_review_and_update_status, review_summary, set_task_status
from app.state_machine import InvalidTransitionError, TaskStatus

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


def _manifest_out(m: Manifest) -> ManifestOut:
    return ManifestOut(
        id=m.id,
        task_id=m.task_id,
        agent_id=m.agent_id,
        device_id=m.device_id,
        payload=manifest_payload(m),
        intent=m.intent,
        cot_summary=m.cot_summary,
        channel=m.channel or "feishu",
        channel_message_id=m.channel_message_id,
        feishu_message_id=m.channel_message_id if m.channel == "feishu" else None,
        submitted_at=m.submitted_at,
    )


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
    fields = resolve_manifest_fields(
        body.payload,
        intent=body.intent,
        cot_summary=body.cot_summary,
        channel=body.channel,
        channel_message_id=body.channel_message_id,
        feishu_message_id=body.feishu_message_id,
        task=task,
    )
    manifest = Manifest(
        task_id=task.id,
        agent_id=body.agent_id,
        device_id=body.device_id,
        payload_json=fields["payload_json"],
        intent=fields["intent"],
        cot_summary=fields["cot_summary"],
        channel=fields["channel"],
        channel_message_id=fields["channel_message_id"],
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
            "intent": manifest.intent,
            "channel_message_id": manifest.channel_message_id,
        },
    )
    return _manifest_out(manifest)


@router.get("/{task_id}/manifests", response_model=list[ManifestOut])
def list_manifests(task_id: int, db: Session = Depends(get_db)):
    task = _get_task_or_404(task_id, db)
    return [
        _manifest_out(m)
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


@router.post("/{task_id}/reviews", response_model=TaskOut)
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
    from app.services.event_bus import emit_event

    summary = review_summary(task, db)
    notify_review(task, body.reviewer_agent_id, body.status, body.note)

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


@router.post("/{task_id}/execution-abort", response_model=AgentReplyOut, status_code=201)
def execution_abort(
    task_id: int, body: ExecutionAbortBody, db: Session = Depends(get_db)
):
    """执行超时熔断：回滚后标记 ChangesRequested 并推飞书。"""
    task = _get_task_or_404(task_id, db)
    if TaskStatus(task.status) in (
        TaskStatus.WORKING,
        TaskStatus.ASSIGNED,
        TaskStatus.REVIEW_PENDING,
    ):
        try:
            set_task_status(task, TaskStatus.CHANGES_REQUESTED)
        except InvalidTransitionError:
            pass
    task.updated_at = utcnow()
    db.commit()
    db.refresh(task)

    lines = [
        f"❌ 任务 #{task_id} 异常，已熔断",
        f"原因：{body.reason}",
    ]
    if body.timeout_seconds:
        lines.append(f"超时阈值：{body.timeout_seconds}s")
    if body.rollback_status:
        lines.append(f"工作区回滚：{body.rollback_status}")
    content = "\n".join(lines)

    try:
        reply = submit_agent_reply(
            db,
            task_id,
            body.device_id,
            body.agent_id,
            content,
            source="execution-supervisor",
            notify_feishu=body.notify_feishu,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    from app.services.event_bus import emit_event

    emit_event(
        "task.execution_aborted",
        task=task,
        db=db,
        extra={
            "reason": body.reason,
            "rollback_status": body.rollback_status,
        },
    )
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


class LifecycleEventBody(BaseModel):
    event: str = Field(..., min_length=1, description="如 task.inbox_acked")
    extra: dict | None = None


@router.post("/{task_id}/lifecycle")
def post_lifecycle_event(
    task_id: int, body: LifecycleEventBody, db: Session = Depends(get_db)
):
    """本机 Runner / Hook 上报生命周期，统一走 event_bus → 飞书通知流。"""
    from app.services.event_bus import emit_event

    task = _get_task_or_404(task_id, db)
    emit_event(body.event, task=task, db=db, extra=body.extra or {})
    return {"ok": True, "task_id": task_id, "event": body.event}


class MilestoneBody(BaseModel):
    milestone: str = Field(..., min_length=1, description="context|edit|test|commit|review|done")
    detail: str | None = None
    device_id: str | None = None
    agent_id: str | None = None
    notify_feishu: bool = True


@router.post("/{task_id}/milestones")
def post_task_milestone(
    task_id: int, body: MilestoneBody, db: Session = Depends(get_db)
):
    """P2 里程碑进度（非 CoT 流式）。"""
    from app.services.milestones import post_milestone

    try:
        return post_milestone(
            db,
            task_id,
            milestone=body.milestone,
            detail=body.detail,
            device_id=body.device_id,
            agent_id=body.agent_id,
            notify_feishu=body.notify_feishu,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class ConfirmExecBody(BaseModel):
    action: str = Field(..., description="confirm | defer | request")
    device_id: str | None = None
    agent_id: str | None = None
    item: dict | None = None


@router.post("/{task_id}/exec-confirm")
def post_exec_confirm(
    task_id: int, body: ConfirmExecBody, db: Session = Depends(get_db)
):
    """P1 半自动：确认执行 / 稍后 / 请求确认。"""
    from app.services.exec_confirm import (
        build_confirm_card,
        confirm_task,
        defer_task,
        request_confirm,
    )
    from app.services.event_bus import emit_event
    from app.services.feishu_notify import notify_task_async
    from app.services.agent_replies import submit_agent_reply

    task = _get_task_or_404(task_id, db)
    action = (body.action or "").strip().lower()

    if action == "request":
        item = body.item or {
            "task_id": task_id,
            "title": task.title,
            "kind": "work",
        }
        data = request_confirm(
            task_id=task_id,
            device_id=body.device_id or task.assignee_device_id or "mac-a",
            agent_id=body.agent_id or task.assignee_agent_id or "cursor",
            item=item,
        )
        text = (
            f"🔔 任务 #{task_id} 已就绪，是否现在执行？\n"
            f"标题：{task.title}\n"
            f"点确认后才会唤醒电脑上的 Agent。"
        )
        submit_agent_reply(
            db,
            task_id,
            data["device_id"],
            data["agent_id"],
            text + "\n\n（App：发送「确认执行 {0}」或「稍后 {0}」）".format(task_id),
            source="exec-confirm-request",
            notify_feishu=False,
        )
        # 飞书富文本卡片
        if task.feishu_chat_id and not str(task.feishu_chat_id).startswith("mobile:"):
            card = build_confirm_card(task_id, task.title or "", data["agent_id"])
            try:
                import asyncio
                from app.config import settings
                from app.services.feishu import FeishuError, feishu_client

                async def _send():
                    try:
                        await feishu_client.send_interactive_to_chat(
                            task.feishu_chat_id, card
                        )
                    except FeishuError:
                        notify_task_async(task, text)

                if not settings.feishu_configured:
                    notify_task_async(task, text)
                else:
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(_send())
                    except RuntimeError:
                        asyncio.run(_send())
            except Exception:
                notify_task_async(task, text)
        else:
            # App 会话：仅靠 agent_replies + /mobile/updates
            pass
        emit_event("task.exec_confirm_requested", task=task, db=db)
        return {"ok": True, "status": "pending", "task_id": task_id}

    if action == "confirm":
        data = confirm_task(task_id)
        submit_agent_reply(
            db,
            task_id,
            data.get("device_id") or "hub",
            data.get("agent_id") or "system",
            f"✅ 已确认执行任务 #{task_id}，正在唤醒 Agent…",
            source="exec-confirm",
            notify_feishu=True,
        )
        emit_event("task.exec_confirmed", task=task, db=db)
        return {"ok": True, "status": "confirmed", "task_id": task_id, "data": data}

    if action == "defer":
        data = defer_task(task_id)
        submit_agent_reply(
            db,
            task_id,
            data.get("device_id") or "hub",
            data.get("agent_id") or "system",
            f"⏸ 任务 #{task_id} 已稍后执行（进队列）",
            source="exec-defer",
            notify_feishu=True,
        )
        emit_event("task.exec_deferred", task=task, db=db)
        return {"ok": True, "status": "deferred", "task_id": task_id, "data": data}

    raise HTTPException(status_code=400, detail="action 须为 request|confirm|defer")
