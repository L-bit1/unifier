from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import Project, Task, utcnow
from app.services.tasks import review_summary, set_task_status
from app.state_machine import TaskStatus


def get_or_create_project(
    db: Session,
    github_owner: str,
    github_repo: str,
    default_branch: str = "main",
) -> Project:
    project = (
        db.query(Project)
        .filter(
            Project.github_owner == github_owner,
            Project.github_repo == github_repo,
        )
        .first()
    )
    if project:
        return project
    project = Project(
        github_owner=github_owner,
        github_repo=github_repo,
        default_branch=default_branch,
    )
    db.add(project)
    db.flush()
    return project


def command_status(task: Task, db: Session) -> dict[str, Any]:
    summary = review_summary(task, db)
    lines = [
        f"任务 #{task.id} · {task.title}",
        f"仓库分支: {task.branch}",
        f"状态: {task.status}",
        f"执行: {task.assignee_device_id}/{task.assignee_agent_id}",
    ]
    if summary["required"]:
        lines.append(f"待审查: {', '.join(summary['pending']) or '无'}")
        lines.append(f"已通过: {', '.join(summary['approvals']) or '无'}")
        if summary["rejected"]:
            lines.append(f"已驳回: {', '.join(summary['rejected'])}")
    lines.append(
        "可合并: 是" if summary["merge_ready"] else "可合并: 否（审查未全票通过）"
    )
    return {
        "task_id": task.id,
        "title": task.title,
        "status": task.status,
        "merge_ready": summary["merge_ready"],
        "assignee_device_id": task.assignee_device_id,
        "assignee_agent_id": task.assignee_agent_id,
        "review_summary": summary,
        "message": "\n".join(lines),
    }


def dispatch_command(
    db: Session,
    *,
    github_owner: str,
    github_repo: str,
    title: str,
    description: str | None,
    branch: str,
    implementer_device_id: str,
    implementer_agent_id: str,
    required_reviewers: list[str],
    feishu_chat_id: str | None = None,
    feishu_message_id: str | None = None,
) -> tuple[Task, Project]:
    from app.models import Device

    device = (
        db.query(Device)
        .filter(Device.device_id == implementer_device_id)
        .first()
    )
    if not device:
        raise ValueError(f"设备 {implementer_device_id} 未注册，请先 register-device")
    if device.agents and implementer_agent_id not in device.agents:
        raise ValueError(
            f"设备 {implementer_device_id} 登记的 agents 为 {device.agents}，"
            f"不含 {implementer_agent_id}"
        )

    from app.services.agent_slots import assert_can_implement, filter_reviewers

    assert_can_implement(db, implementer_device_id, implementer_agent_id)
    filtered_reviewers = filter_reviewers(db, required_reviewers)
    if required_reviewers and not filtered_reviewers:
        raise ValueError("审查者均未启用（选配关闭），请调整 agent-slots 或任务审查列表")

    project = get_or_create_project(db, github_owner, github_repo)
    task = Task(
        project_id=project.id,
        title=title,
        description=description,
        branch=branch,
        status=TaskStatus.PLANNED.value,
        assignee_device_id=implementer_device_id,
        assignee_agent_id=implementer_agent_id,
    )
    task.required_reviewers = filtered_reviewers
    task.feishu_chat_id = feishu_chat_id
    task.feishu_message_id = feishu_message_id
    db.add(task)
    db.flush()
    set_task_status(task, TaskStatus.ASSIGNED)
    task.updated_at = utcnow()
    db.commit()
    db.refresh(task)
    return task, project
