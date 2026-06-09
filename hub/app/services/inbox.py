from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.models import Task
from app.services.agent_slots import is_inbox_allowed
from app.state_machine import TaskStatus

WORK_STATUSES = {
    TaskStatus.PLANNED.value,
    TaskStatus.ASSIGNED.value,
    TaskStatus.WORKING.value,
    TaskStatus.CHANGES_REQUESTED.value,
}

REVIEW_STATUSES = {
    TaskStatus.REVIEW_PENDING.value,
    TaskStatus.REVIEWING.value,
}


def _reviewer_key(device_id: str, agent_id: str) -> str:
    return f"{device_id}:{agent_id}"


def _reviewer_voted(task: Task, reviewer_id: str) -> bool:
    return any(r.reviewer_agent_id == reviewer_id for r in task.reviews)


def _task_reviewer_ids(task: Task) -> set[str]:
    return set(task.required_reviewers)


def inbox_items(device_id: str, agent_id: str, db: Session) -> list[dict[str, Any]]:
    tasks = (
        db.query(Task)
        .options(joinedload(Task.reviews), joinedload(Task.project))
        .order_by(Task.id.desc())
        .all()
    )
    items: list[dict[str, Any]] = []
    reviewer_id = _reviewer_key(device_id, agent_id)
    reviewer_ids = {reviewer_id, agent_id}

    for task in tasks:
        if (
            task.assignee_device_id == device_id
            and task.assignee_agent_id == agent_id
            and task.status in WORK_STATUSES
            and is_inbox_allowed(db, device_id, agent_id, "work")
        ):
            items.append(
                {
                    "task_id": task.id,
                    "kind": "work",
                    "title": task.title,
                    "branch": task.branch,
                    "status": task.status,
                    "project": f"{task.project.github_owner}/{task.project.github_repo}",
                    "description": task.description,
                }
            )
            continue

        required = _task_reviewer_ids(task)
        if not required.intersection(reviewer_ids):
            continue

        matched = reviewer_id if reviewer_id in required else agent_id
        if (
            task.status in REVIEW_STATUSES
            and not _reviewer_voted(task, matched)
            and is_inbox_allowed(db, device_id, agent_id, "review")
        ):
            items.append(
                {
                    "task_id": task.id,
                    "kind": "review",
                    "title": task.title,
                    "branch": task.branch,
                    "status": task.status,
                    "project": f"{task.project.github_owner}/{task.project.github_repo}",
                    "description": task.description,
                }
            )

    return items
