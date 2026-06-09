from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Device, Task
from app.schemas import CommandDispatch, CommandStatusOut, ConnectivityReportOut, DispatchOut
from app.services.devices import (
    connectivity_report,
    connectivity_report_payload,
    parse_expected_devices,
)
from app.services.orchestrate import command_status, dispatch_command

router = APIRouter(prefix="/api/v1/orchestrate", tags=["orchestrate"])


def _get_task_or_404(task_id: int, db: Session) -> Task:
    task = (
        db.query(Task)
        .options(joinedload(Task.reviews), joinedload(Task.project))
        .filter(Task.id == task_id)
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.get("/connectivity", response_model=ConnectivityReportOut)
def orchestrate_connectivity(
    expected: str | None = None,
    db: Session = Depends(get_db),
):
    """手机端一键检查：Hub 侧看到的设备联通性（与 /devices/connectivity 相同）。"""
    devices = db.query(Device).order_by(Device.device_id).all()
    expected_ids = parse_expected_devices(expected) if expected is not None else None
    report = connectivity_report(devices, expected_device_ids=expected_ids)
    return ConnectivityReportOut(**connectivity_report_payload(report))


@router.post("/dispatch", response_model=DispatchOut, status_code=201)
def dispatch(body: CommandDispatch, db: Session = Depends(get_db)):
    """模拟手机飞书下达命令：创建/绑定项目并派活给指定设备 Agent。"""
    if body.require_connectivity:
        devices = db.query(Device).order_by(Device.device_id).all()
        expected = body.expected_devices or parse_expected_devices()
        report = connectivity_report(devices, expected_device_ids=expected)
        if not report["ready_for_dispatch"]:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "设备未全部在线，拒绝派活",
                    "connectivity": report,
                },
            )

    try:
        required_reviewers = body.required_reviewers
        if not required_reviewers:
            from app.config import settings
            from app.services.agent_slots import filter_reviewers

            raw = [
                x.strip()
                for x in settings.feishu_default_reviewers.split(",")
                if x.strip()
            ]
            required_reviewers = filter_reviewers(db, raw)

        task, project = dispatch_command(
            db,
            github_owner=body.github_owner,
            github_repo=body.github_repo,
            title=body.title,
            description=body.description,
            branch=body.branch,
            implementer_device_id=body.implementer_device_id,
            implementer_agent_id=body.implementer_agent_id,
            required_reviewers=required_reviewers,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    status = command_status(task, db)
    return DispatchOut(
        task_id=task.id,
        project_id=project.id,
        github_owner=project.github_owner,
        github_repo=project.github_repo,
        title=task.title,
        branch=task.branch,
        status=task.status,
        implementer_device_id=task.assignee_device_id or "",
        implementer_agent_id=task.assignee_agent_id or "",
        required_reviewers=task.required_reviewers,
        message=status["message"],
    )


@router.get("/tasks/{task_id}/status", response_model=CommandStatusOut)
def get_command_status(task_id: int, db: Session = Depends(get_db)):
    """手机端轮询任务进度与审查结果（飞书 Bot 未接入前的反馈入口）。"""
    task = _get_task_or_404(task_id, db)
    status = command_status(task, db)
    return CommandStatusOut(**status)
