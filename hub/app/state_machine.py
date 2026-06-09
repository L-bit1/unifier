from __future__ import annotations

from enum import StrEnum


class TaskStatus(StrEnum):
    PLANNED = "Planned"
    ASSIGNED = "Assigned"
    WORKING = "Working"
    REVIEW_PENDING = "ReviewPending"
    REVIEWING = "Reviewing"
    CHANGES_REQUESTED = "ChangesRequested"
    APPROVED = "Approved"
    MERGED = "Merged"


# 允许的状态迁移：当前状态 -> 可进入的下一状态集合
TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PLANNED: {TaskStatus.ASSIGNED, TaskStatus.WORKING},
    TaskStatus.ASSIGNED: {TaskStatus.WORKING, TaskStatus.PLANNED},
    TaskStatus.WORKING: {
        TaskStatus.REVIEW_PENDING,
        TaskStatus.ASSIGNED,
    },
    TaskStatus.REVIEW_PENDING: {
        TaskStatus.REVIEWING,
        TaskStatus.WORKING,
    },
    TaskStatus.REVIEWING: {
        TaskStatus.APPROVED,
        TaskStatus.CHANGES_REQUESTED,
        TaskStatus.WORKING,
    },
    TaskStatus.CHANGES_REQUESTED: {
        TaskStatus.WORKING,
        TaskStatus.REVIEW_PENDING,
    },
    TaskStatus.APPROVED: {TaskStatus.MERGED, TaskStatus.WORKING},
    TaskStatus.MERGED: set(),
}


class InvalidTransitionError(ValueError):
    pass


def can_transition(current: TaskStatus, target: TaskStatus) -> bool:
    if current == target:
        return True
    return target in TRANSITIONS.get(current, set())


def assert_transition(current: TaskStatus, target: TaskStatus) -> None:
    if not can_transition(current, target):
        raise InvalidTransitionError(
            f"不允许从 {current.value} 迁移到 {target.value}"
        )
