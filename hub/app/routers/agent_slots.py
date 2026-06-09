from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Device
from app.schemas import AgentSlotOut, AgentSlotUpdate, AgentSlotsReportOut
from app.services.agent_slots import (
    format_slots_message,
    get_slot,
    list_slots,
    slot_to_dict,
    sync_slots_from_device,
    update_slot,
)

router = APIRouter(prefix="/api/v1/agent-slots", tags=["agent-slots"])


@router.get("", response_model=AgentSlotsReportOut)
def get_agent_slots(device_id: str | None = None, db: Session = Depends(get_db)):
    """查看各设备 Cursor/Trae 是否参与派活（执行/审查）。"""
    slots = list_slots(db, device_id)
    return AgentSlotsReportOut(
        slots=[AgentSlotOut(**slot_to_dict(s)) for s in slots],
        message=format_slots_message(db),
    )


@router.get("/{device_id}/{agent_id}", response_model=AgentSlotOut)
def get_agent_slot(device_id: str, agent_id: str, db: Session = Depends(get_db)):
    slot = get_slot(db, device_id, agent_id)
    if not slot:
        device = db.query(Device).filter(Device.device_id == device_id).first()
        if not device:
            raise HTTPException(status_code=404, detail="设备未注册")
        if agent_id not in device.agents:
            raise HTTPException(status_code=404, detail="该设备未登记此 agent")
        slot = sync_slots_from_device(db, device)[0]
        for s in list_slots(db, device_id):
            if s.agent_id == agent_id:
                slot = s
                break
    return AgentSlotOut(**slot_to_dict(slot))


@router.patch("/{device_id}/{agent_id}", response_model=AgentSlotOut)
def patch_agent_slot(
    device_id: str,
    agent_id: str,
    body: AgentSlotUpdate,
    db: Session = Depends(get_db),
):
    """选配：开启/关闭某台设备的 cursor 或 trae，或仅关闭执行/审查角色。"""
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备未注册")
    if agent_id not in device.agents:
        raise HTTPException(
            status_code=400,
            detail=f"设备 {device_id} 登记的 agents 为 {device.agents}",
        )
    slot = update_slot(
        db,
        device_id,
        agent_id,
        enabled=body.enabled,
        can_implement=body.can_implement,
        can_review=body.can_review,
    )
    return AgentSlotOut(**slot_to_dict(slot))
