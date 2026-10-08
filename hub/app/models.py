from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(256))
    hostname: Mapped[str | None] = mapped_column(String(256), nullable=True)
    os_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # JSON 列表，如 ["cursor", "trae"]
    agents_json: Mapped[str] = mapped_column(Text, default="[]")
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    @property
    def agents(self) -> list[str]:
        return json.loads(self.agents_json or "[]")

    @agents.setter
    def agents(self, value: list[str]) -> None:
        self.agents_json = json.dumps(value, ensure_ascii=False)


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("github_owner", "github_repo"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    github_owner: Mapped[str] = mapped_column(String(128))
    github_repo: Mapped[str] = mapped_column(String(256))
    default_branch: Mapped[str] = mapped_column(String(128), default="main")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    tasks: Mapped[list[Task]] = relationship(back_populates="project")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    title: Mapped[str] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    branch: Mapped[str] = mapped_column(String(256), default="main")
    status: Mapped[str] = mapped_column(String(32), default="Planned", index=True)
    assignee_device_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    assignee_agent_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # JSON 列表：必须全部 approve 才能 Approved
    required_reviewers_json: Mapped[str] = mapped_column(Text, default="[]")
    feishu_chat_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    feishu_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    project: Mapped[Project] = relationship(back_populates="tasks")
    manifests: Mapped[list[Manifest]] = relationship(back_populates="task")
    reviews: Mapped[list[Review]] = relationship(back_populates="task")
    agent_replies: Mapped[list[AgentReply]] = relationship(back_populates="task")

    @property
    def required_reviewers(self) -> list[str]:
        return json.loads(self.required_reviewers_json or "[]")

    @required_reviewers.setter
    def required_reviewers(self, value: list[str]) -> None:
        self.required_reviewers_json = json.dumps(value, ensure_ascii=False)


class Manifest(Base):
    __tablename__ = "manifests"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    agent_id: Mapped[str] = mapped_column(String(128))
    device_id: Mapped[str] = mapped_column(String(128))
    payload_json: Mapped[str] = mapped_column(Text)
    # 意图记忆：为什么改、思维链摘要、来源通道消息
    intent: Mapped[str | None] = mapped_column(Text, nullable=True)
    cot_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    channel: Mapped[str] = mapped_column(String(32), default="feishu", index=True)
    channel_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    task: Mapped[Task] = relationship(back_populates="manifests")


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("task_id", "reviewer_agent_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    reviewer_agent_id: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32))  # approved | changes_requested
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    task: Mapped[Task] = relationship(back_populates="reviews")


class AgentReply(Base):
    __tablename__ = "agent_replies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    device_id: Mapped[str] = mapped_column(String(128))
    agent_id: Mapped[str] = mapped_column(String(128))
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32), default="agent")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    task: Mapped[Task] = relationship(back_populates="agent_replies")


class FeishuChatSession(Base):
    """飞书群当前选中的 GitHub 项目（派活默认仓库）。"""

    __tablename__ = "feishu_chat_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    chat_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    github_owner: Mapped[str] = mapped_column(String(128))
    github_repo: Mapped[str] = mapped_column(String(256))
    display_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    local_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class DeviceAgentSlot(Base):
    """每台设备上各 Agent（cursor/trae）是否参与派活/审查。"""

    __tablename__ = "device_agent_slots"
    __table_args__ = (UniqueConstraint("device_id", "agent_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(128), index=True)
    agent_id: Mapped[str] = mapped_column(String(128))
    enabled: Mapped[bool] = mapped_column(default=True)
    can_implement: Mapped[bool] = mapped_column(default=True)
    can_review: Mapped[bool] = mapped_column(default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Workflow(Base):
    """内置可视化工作流（路线 B：单进程自动化引擎）。"""

    __tablename__ = "workflows"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    graph_json: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(default=False, index=True)
    trigger_kind: Mapped[str] = mapped_column(String(32), default="hub_event")
    hook_id: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    schedule_cron: Mapped[str | None] = mapped_column(String(64), nullable=True)
    preset_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    runs: Mapped[list[WorkflowRun]] = relationship(back_populates="workflow")


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    workflow_id: Mapped[int] = mapped_column(ForeignKey("workflows.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="running")
    trigger_type: Mapped[str] = mapped_column(String(32), default="manual")
    trigger_event: Mapped[str | None] = mapped_column(String(128), nullable=True)
    input_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    workflow: Mapped[Workflow] = relationship(back_populates="runs")


class DialogueRoom(Base):
    """圆桌对话房间：Cursor / Trae 等同场互读互回（独立于 Task 状态机）。"""

    __tablename__ = "dialogue_rooms"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_key: Mapped[str] = mapped_column(String(128), default="maotai", index=True)
    title: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)  # open|closed
    current_round: Mapped[int] = mapped_column(default=1)
    # JSON 列表：参与 Agent，如 ["cursor","trae"]
    participants_json: Mapped[str] = mapped_column(Text, default='["cursor","trae"]')
    round_opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    round_complete: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    messages: Mapped[list[DialogueMessage]] = relationship(
        back_populates="room", order_by="DialogueMessage.id"
    )
    acks: Mapped[list[DialogueAck]] = relationship(back_populates="room")

    @property
    def participants(self) -> list[str]:
        return json.loads(self.participants_json or "[]")

    @participants.setter
    def participants(self, value: list[str]) -> None:
        self.participants_json = json.dumps(value, ensure_ascii=False)


class DialogueMessage(Base):
    __tablename__ = "dialogue_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("dialogue_rooms.id"), index=True)
    round: Mapped[int] = mapped_column(index=True)
    role: Mapped[str] = mapped_column(String(32))  # user|agent|system
    participant: Mapped[str] = mapped_column(String(128))  # user|cursor|trae|…
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    room: Mapped[DialogueRoom] = relationship(back_populates="messages")


class DialogueAck(Base):
    """某参与者已读到的最大 message_id。"""

    __tablename__ = "dialogue_acks"
    __table_args__ = (UniqueConstraint("room_id", "participant"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("dialogue_rooms.id"), index=True)
    participant: Mapped[str] = mapped_column(String(128))
    last_seen_message_id: Mapped[int] = mapped_column(default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    room: Mapped[DialogueRoom] = relationship(back_populates="acks")
