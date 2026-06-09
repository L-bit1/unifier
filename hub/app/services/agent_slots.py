from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Device, DeviceAgentSlot, utcnow


def reviewer_key(device_id: str, agent_id: str) -> str:
    return f"{device_id}:{agent_id}"


def parse_reviewer_key(key: str) -> tuple[str, str]:
    if ":" in key:
        device_id, agent_id = key.split(":", 1)
        return device_id.strip(), agent_id.strip()
    return "", key.strip()


def get_slot(db: Session, device_id: str, agent_id: str) -> DeviceAgentSlot | None:
    return (
        db.query(DeviceAgentSlot)
        .filter(
            DeviceAgentSlot.device_id == device_id,
            DeviceAgentSlot.agent_id == agent_id,
        )
        .first()
    )


def ensure_slot(
    db: Session,
    device_id: str,
    agent_id: str,
    *,
    enabled: bool = True,
    can_implement: bool = True,
    can_review: bool = True,
) -> DeviceAgentSlot:
    slot = get_slot(db, device_id, agent_id)
    if slot:
        return slot
    slot = DeviceAgentSlot(
        device_id=device_id,
        agent_id=agent_id,
        enabled=enabled,
        can_implement=can_implement,
        can_review=can_review,
    )
    db.add(slot)
    db.flush()
    return slot


def sync_slots_from_device(db: Session, device: Device) -> list[DeviceAgentSlot]:
    slots: list[DeviceAgentSlot] = []
    for agent_id in device.agents:
        slots.append(ensure_slot(db, device.device_id, agent_id))
    db.commit()
    return slots


def list_slots(db: Session, device_id: str | None = None) -> list[DeviceAgentSlot]:
    q = db.query(DeviceAgentSlot).order_by(
        DeviceAgentSlot.device_id, DeviceAgentSlot.agent_id
    )
    if device_id:
        q = q.filter(DeviceAgentSlot.device_id == device_id)
    return q.all()


def slot_status_label(slot: DeviceAgentSlot) -> str:
    if not slot.enabled:
        return "❌ 关闭"
    parts: list[str] = []
    if slot.can_implement:
        parts.append("执行")
    if slot.can_review:
        parts.append("审查")
    if not parts:
        return "⚠️ 已启用但未分配角色"
    return "✅ " + "+".join(parts)


def format_slots_message(db: Session) -> str:
    slots = list_slots(db)
    if not slots:
        return "暂无选配记录，请先 register-device 注册设备。"
    lines = ["📋 设备 Agent 选配（✅参与 ❌不参与）"]
    for slot in slots:
        lines.append(
            f"· {slot.device_id}/{slot.agent_id}: {slot_status_label(slot)}"
        )
    lines.append("")
    lines.append("修改示例：")
    lines.append("  选配 off device-b trae")
    lines.append("  选配 on device-a cursor")
    lines.append("  选配 执行 off device-a trae")
    lines.append("  选配 审查 on device-b cursor")
    return "\n".join(lines)


def _slot_allows_implement(slot: DeviceAgentSlot | None) -> bool:
    return bool(slot and slot.enabled and slot.can_implement)


def _slot_allows_review(slot: DeviceAgentSlot | None, reviewer_key_str: str) -> bool:
    if not slot or not slot.enabled or not slot.can_review:
        return False
    device_id, agent_id = parse_reviewer_key(reviewer_key_str)
    if device_id:
        return slot.device_id == device_id and slot.agent_id == agent_id
    return slot.agent_id == agent_id


def assert_can_implement(db: Session, device_id: str, agent_id: str) -> None:
    slot = get_slot(db, device_id, agent_id)
    if slot is None:
        ensure_slot(db, device_id, agent_id)
        db.commit()
        slot = get_slot(db, device_id, agent_id)
    if not _slot_allows_implement(slot):
        enabled_impl = [
            f"{s.device_id}/{s.agent_id}"
            for s in list_slots(db)
            if _slot_allows_implement(s)
        ]
        hint = f"可选执行者: {', '.join(enabled_impl) or '无'}"
        raise ValueError(
            f"{device_id}/{agent_id} 未启用执行角色（选配关闭）。{hint}"
        )


def filter_reviewers(db: Session, reviewer_ids: list[str]) -> list[str]:
    result: list[str] = []
    for rid in reviewer_ids:
        device_id, agent_id = parse_reviewer_key(rid)
        if device_id:
            slot = get_slot(db, device_id, agent_id)
            if slot is None:
                ensure_slot(db, device_id, agent_id)
                db.commit()
                slot = get_slot(db, device_id, agent_id)
            if _slot_allows_review(slot, rid):
                result.append(rid)
        else:
            # 兼容旧格式 agent-2：任一同名 agent 开启审查即保留
            matching = [
                s
                for s in list_slots(db)
                if s.agent_id == agent_id and s.enabled and s.can_review
            ]
            if matching:
                result.append(rid)
    return result


def resolve_dispatch_roles(db: Session) -> tuple[str, str, list[str]]:
    impl_d = settings.feishu_default_implementer_device.strip()
    impl_a = settings.feishu_default_implementer_agent.strip() or "cursor"
    if not impl_d:
        enabled = [s for s in list_slots(db) if _slot_allows_implement(s)]
        if not enabled:
            raise ValueError(
                "未配置默认执行设备（FEISHU_DEFAULT_IMPLEMENTER_DEVICE），"
                "且无可用的执行 Agent。请先 register-device 并配置 .env"
            )
        impl_d = enabled[0].device_id
        impl_a = enabled[0].agent_id
    assert_can_implement(db, impl_d, impl_a)
    raw_reviewers = [
        x.strip()
        for x in settings.feishu_default_reviewers.split(",")
        if x.strip()
    ]
    reviewers = filter_reviewers(db, raw_reviewers)
    if raw_reviewers and not reviewers:
        raise ValueError("默认审查者均未启用，请用「选配」打开或修改 .env")
    return impl_d, impl_a, reviewers


def update_slot(
    db: Session,
    device_id: str,
    agent_id: str,
    *,
    enabled: bool | None = None,
    can_implement: bool | None = None,
    can_review: bool | None = None,
) -> DeviceAgentSlot:
    slot = get_slot(db, device_id, agent_id)
    if not slot:
        slot = ensure_slot(db, device_id, agent_id)
    if enabled is not None:
        slot.enabled = enabled
        if not enabled:
            slot.can_implement = False
            slot.can_review = False
    if can_implement is not None:
        slot.can_implement = can_implement
    if can_review is not None:
        slot.can_review = can_review
    if slot.enabled and (slot.can_implement or slot.can_review):
        pass
    elif enabled is True and can_implement is None and can_review is None:
        slot.can_implement = True
        slot.can_review = True
    slot.updated_at = utcnow()
    db.commit()
    db.refresh(slot)
    return slot


def slot_to_dict(slot: DeviceAgentSlot) -> dict[str, Any]:
    return {
        "device_id": slot.device_id,
        "agent_id": slot.agent_id,
        "enabled": slot.enabled,
        "can_implement": slot.can_implement,
        "can_review": slot.can_review,
        "status_label": slot_status_label(slot),
        "updated_at": slot.updated_at,
    }


def is_inbox_allowed(
    db: Session, device_id: str, agent_id: str, kind: str
) -> bool:
    slot = get_slot(db, device_id, agent_id)
    if slot is None:
        return True
    if not slot.enabled:
        return False
    if kind == "work":
        return slot.can_implement
    if kind == "review":
        return slot.can_review
    return True
