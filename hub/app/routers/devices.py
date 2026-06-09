from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Device, utcnow
from app.schemas import (
    ConnectivityReportOut,
    DeviceConnectivityOut,
    DeviceOut,
    DeviceRegister,
)
from app.services.devices import (
    connectivity_report,
    connectivity_report_payload,
    device_connectivity,
    is_online,
    parse_expected_devices,
)
from app.services.agent_slots import sync_slots_from_device

router = APIRouter(prefix="/api/v1/devices", tags=["devices"])


def _device_out(d: Device) -> DeviceOut:
    return DeviceOut(
        id=d.id,
        device_id=d.device_id,
        name=d.name,
        hostname=d.hostname,
        os_name=d.os_name,
        agents=d.agents,
        last_heartbeat_at=d.last_heartbeat_at,
        online=is_online(d),
        created_at=d.created_at,
    )


@router.post("/register", response_model=DeviceOut)
def register_device(body: DeviceRegister, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.device_id == body.device_id).first()
    now = utcnow()
    if device:
        device.name = body.name
        device.hostname = body.hostname
        device.os_name = body.os_name
        device.agents = body.agents
        device.last_heartbeat_at = now
    else:
        device = Device(
            device_id=body.device_id,
            name=body.name,
            hostname=body.hostname,
            os_name=body.os_name,
            last_heartbeat_at=now,
        )
        device.agents = body.agents
        db.add(device)
    db.commit()
    db.refresh(device)
    sync_slots_from_device(db, device)
    return _device_out(device)


@router.post("/{device_id}/heartbeat", response_model=DeviceOut)
def heartbeat(device_id: str, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备未注册，请先 POST /devices/register")
    device.last_heartbeat_at = utcnow()
    db.commit()
    db.refresh(device)
    return _device_out(device)


@router.get("", response_model=list[DeviceOut])
def list_devices(online_only: bool = False, db: Session = Depends(get_db)):
    devices = db.query(Device).order_by(Device.device_id).all()
    out = [_device_out(d) for d in devices]
    if online_only:
        out = [d for d in out if d.online]
    return out


@router.get("/connectivity", response_model=ConnectivityReportOut)
def check_connectivity(
    expected: str | None = None,
    db: Session = Depends(get_db),
):
    """检查全部已注册设备的在线联通性；可选 expected=mac-a,win-pc 覆盖默认期望列表。"""
    devices = db.query(Device).order_by(Device.device_id).all()
    expected_ids = parse_expected_devices(expected) if expected is not None else None
    report = connectivity_report(devices, expected_device_ids=expected_ids)
    return ConnectivityReportOut(**connectivity_report_payload(report))


@router.get("/{device_id}/connectivity", response_model=DeviceConnectivityOut)
def check_device_connectivity(device_id: str, db: Session = Depends(get_db)):
    """检查单台设备与 Hub 的联通状态（基于最近心跳）。"""
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    return DeviceConnectivityOut(**device_connectivity(device))


@router.get("/{device_id}", response_model=DeviceOut)
def get_device(device_id: str, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    return _device_out(device)
