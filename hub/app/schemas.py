from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.state_machine import TaskStatus


class DeviceRegister(BaseModel):
    device_id: str = Field(..., min_length=1, max_length=128)
    name: str = Field(..., min_length=1)
    hostname: str | None = None
    os_name: str | None = None
    agents: list[str] = Field(default_factory=list)


class DeviceOut(BaseModel):
    id: int
    device_id: str
    name: str
    hostname: str | None
    os_name: str | None
    agents: list[str]
    last_heartbeat_at: datetime | None
    online: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentSlotOut(BaseModel):
    device_id: str
    agent_id: str
    enabled: bool
    can_implement: bool
    can_review: bool
    status_label: str
    updated_at: datetime


class AgentSlotUpdate(BaseModel):
    enabled: bool | None = None
    can_implement: bool | None = None
    can_review: bool | None = None


class AgentSlotsReportOut(BaseModel):
    slots: list[AgentSlotOut]
    message: str


class DeviceConnectivityOut(BaseModel):
    device_id: str
    name: str
    hostname: str | None
    os_name: str | None
    agents: list[str]
    online: bool
    link_status: Literal["online", "offline", "never_seen"]
    last_heartbeat_at: datetime | None
    seconds_since_heartbeat: float | None
    online_threshold_seconds: int


class ConnectivityReportOut(BaseModel):
    checked_at: datetime
    hub_reachable: bool = True
    online_threshold_seconds: int
    expected_device_ids: list[str]
    total_registered: int
    online_count: int
    offline_count: int
    online_device_ids: list[str]
    offline_device_ids: list[str]
    missing_expected: list[str]
    expected_offline: list[str]
    all_expected_online: bool
    ready_for_dispatch: bool
    devices: list[DeviceConnectivityOut]
    message: str


class ProjectCreate(BaseModel):
    github_owner: str
    github_repo: str
    default_branch: str = "main"


class ProjectOut(BaseModel):
    id: int
    github_owner: str
    github_repo: str
    default_branch: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TaskCreate(BaseModel):
    project_id: int
    title: str
    description: str | None = None
    branch: str = "main"
    required_reviewers: list[str] = Field(default_factory=list)


class TaskAssign(BaseModel):
    device_id: str
    agent_id: str


class TaskStatusUpdate(BaseModel):
    status: TaskStatus


class ManifestSubmit(BaseModel):
    agent_id: str
    device_id: str
    payload: dict[str, Any]
    intent: str | None = Field(
        default=None, description="变更意图：为什么改、业务背景"
    )
    cot_summary: str | None = Field(
        default=None, description="思维链摘要：推理过程、权衡点"
    )
    channel: str | None = Field(default=None, description="来源通道，默认 feishu")
    channel_message_id: str | None = Field(
        default=None, description="来源通道消息 ID（通用）"
    )
    feishu_message_id: str | None = Field(
        default=None, description="飞书 message_id（channel=feishu 时写入）"
    )


class ReviewSubmit(BaseModel):
    reviewer_agent_id: str
    status: Literal["approved", "changes_requested"]
    note: str | None = None


class ReviewOut(BaseModel):
    id: int
    task_id: int
    reviewer_agent_id: str
    status: str
    note: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ManifestOut(BaseModel):
    id: int
    task_id: int
    agent_id: str
    device_id: str
    payload: dict[str, Any]
    intent: str | None = None
    cot_summary: str | None = None
    channel: str = "feishu"
    channel_message_id: str | None = None
    feishu_message_id: str | None = None
    submitted_at: datetime

    model_config = {"from_attributes": True}


class ManifestAuditItem(BaseModel):
    id: int
    task_id: int
    task_title: str | None = None
    task_status: str | None = None
    project: str | None = None
    agent_id: str
    device_id: str
    intent: str | None = None
    cot_summary: str | None = None
    channel: str = "feishu"
    channel_message_id: str | None = None
    feishu_message_id: str | None = None
    task_feishu_message_id: str | None = None
    payload: dict[str, Any]
    submitted_at: datetime


class ManifestAuditSearchOut(BaseModel):
    q: str | None = None
    channel: str | None = None
    count: int
    items: list[ManifestAuditItem]


class ManifestFieldDiff(BaseModel):
    field: str
    left_text: str
    right_text: str
    unified_diff: list[str]


class ManifestPairDiff(BaseModel):
    left_agent: str
    right_agent: str
    left_device: str
    right_device: str
    left_manifest_id: int
    right_manifest_id: int
    left_submitted_at: datetime
    right_submitted_at: datetime
    field_diffs: list[ManifestFieldDiff]
    files_only_left: list[str]
    files_only_right: list[str]
    files_common: list[str]


class TaskManifestDiffOut(BaseModel):
    task_id: int
    found: bool = True
    task_title: str | None = None
    task_status: str | None = None
    project: str | None = None
    agents: list[str] = Field(default_factory=list)
    manifest_count: int = 0
    pairs: list[ManifestPairDiff] = Field(default_factory=list)


class TaskOut(BaseModel):
    id: int
    project_id: int
    title: str
    description: str | None
    branch: str
    status: str
    assignee_device_id: str | None
    assignee_agent_id: str | None
    required_reviewers: list[str]
    merge_ready: bool = False
    review_summary: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MergeReadyOut(BaseModel):
    task_id: int
    status: str
    merge_ready: bool
    required_reviewers: list[str]
    approvals: list[str]
    pending: list[str]
    rejected: list[str]


class InboxItem(BaseModel):
    task_id: int
    kind: Literal["work", "review"]
    title: str
    branch: str
    status: str
    project: str
    description: str | None = None


class CommandDispatch(BaseModel):
    github_owner: str
    github_repo: str
    title: str
    description: str | None = None
    branch: str = "main"
    implementer_device_id: str
    implementer_agent_id: str
    required_reviewers: list[str] = Field(default_factory=list)
    require_connectivity: bool = False
    expected_devices: list[str] | None = None


class DispatchOut(BaseModel):
    task_id: int
    project_id: int
    github_owner: str
    github_repo: str
    title: str
    branch: str
    status: str
    implementer_device_id: str
    implementer_agent_id: str
    required_reviewers: list[str]
    message: str


class CommandStatusOut(BaseModel):
    task_id: int
    title: str
    status: str
    merge_ready: bool
    assignee_device_id: str | None
    assignee_agent_id: str | None
    review_summary: dict[str, Any]
    message: str


class AgentReplySubmit(BaseModel):
    device_id: str
    agent_id: str
    content: str = Field(..., min_length=1)
    source: str = "agent"
    notify_feishu: bool = True


class AgentReplyOut(BaseModel):
    id: int
    task_id: int
    device_id: str
    agent_id: str
    content: str
    source: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ExecutionAbortBody(BaseModel):
    device_id: str
    agent_id: str
    reason: str = "execution_timeout"
    rollback_status: str | None = None
    timeout_seconds: int | None = None
    notify_feishu: bool = True


# ----- 圆桌对话 -----


class DialogueOpenBody(BaseModel):
    title: str = ""
    topic: str = Field(..., min_length=1)
    project_key: str = "maotai"
    participants: list[str] = Field(default_factory=lambda: ["cursor", "trae"])


class DialogueUserMessageBody(BaseModel):
    body: str = Field(..., min_length=1)
    auto_reply: bool | None = None  # None=跟 settings.dialogue_auto_reply


class DialogueReplyBody(BaseModel):
    participant: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1)
