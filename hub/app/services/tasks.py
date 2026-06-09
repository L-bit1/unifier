from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import Manifest, Review, Task
from app.state_machine import InvalidTransitionError, TaskStatus, assert_transition


def set_task_status(task: Task, target: TaskStatus) -> None:
    current = TaskStatus(task.status)
    assert_transition(current, target)
    task.status = target.value


def review_summary(task: Task, db: Session) -> dict[str, Any]:
    required = task.required_reviewers
    reviews = {r.reviewer_agent_id: r for r in task.reviews}
    approvals = [
        aid for aid in required if reviews.get(aid) and reviews[aid].status == "approved"
    ]
    rejected = [
        aid
        for aid in required
        if reviews.get(aid) and reviews[aid].status == "changes_requested"
    ]
    pending = [aid for aid in required if aid not in reviews]
    merge_ready = (
        len(required) > 0
        and len(pending) == 0
        and len(rejected) == 0
        and len(approvals) == len(required)
        and task.status
        in (TaskStatus.REVIEWING.value, TaskStatus.APPROVED.value)
    )
    return {
        "required": required,
        "approvals": approvals,
        "pending": pending,
        "rejected": rejected,
        "merge_ready": merge_ready,
    }


def apply_review_and_update_status(
    task: Task, db: Session, reviewer_agent_id: str, status: str
) -> dict[str, Any]:
    if reviewer_agent_id not in task.required_reviewers:
        raise ValueError(
            f"reviewer {reviewer_agent_id} 不在 required_reviewers 列表中"
        )

    review = next(
        (r for r in task.reviews if r.reviewer_agent_id == reviewer_agent_id),
        None,
    )
    if review:
        review.status = status
    else:
        review = Review(
            task_id=task.id,
            reviewer_agent_id=reviewer_agent_id,
            status=status,
        )
        db.add(review)
        task.reviews.append(review)

    summary = review_summary(task, db)

    if summary["rejected"]:
        if TaskStatus(task.status) in (
            TaskStatus.REVIEWING,
            TaskStatus.REVIEW_PENDING,
            TaskStatus.APPROVED,
        ):
            set_task_status(task, TaskStatus.CHANGES_REQUESTED)
    elif summary["merge_ready"]:
        set_task_status(task, TaskStatus.APPROVED)
    elif TaskStatus(task.status) == TaskStatus.REVIEW_PENDING:
        set_task_status(task, TaskStatus.REVIEWING)

    return summary


def manifest_payload(m: Manifest) -> dict[str, Any]:
    return json.loads(m.payload_json)
