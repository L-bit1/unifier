from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import settings
from app.models import Device


def is_online(device: Device, now: datetime | None = None) -> bool:
    if device.last_heartbeat_at is None:
        return False
    now = now or datetime.now(timezone.utc)
    hb = device.last_heartbeat_at
    if hb.tzinfo is None:
        hb = hb.replace(tzinfo=timezone.utc)
    return (now - hb) <= timedelta(seconds=settings.unifier_device_online_seconds)


def _normalize_dt(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def parse_expected_devices(raw: str | None = None) -> list[str]:
    source = raw if raw is not None else settings.unifier_expected_devices
    return [d.strip() for d in source.split(",") if d.strip()]


def device_connectivity(device: Device, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    online = is_online(device, now)
    last_hb = device.last_heartbeat_at
    seconds_since: float | None = None
    if last_hb is not None:
        seconds_since = (now - _normalize_dt(last_hb)).total_seconds()
    if last_hb is None:
        link_status = "never_seen"
    elif online:
        link_status = "online"
    else:
        link_status = "offline"

    return {
        "device_id": device.device_id,
        "name": device.name,
        "hostname": device.hostname,
        "os_name": device.os_name,
        "agents": device.agents,
        "online": online,
        "link_status": link_status,
        "last_heartbeat_at": last_hb,
        "seconds_since_heartbeat": seconds_since,
        "online_threshold_seconds": settings.unifier_device_online_seconds,
    }


def connectivity_report(
    devices: list[Device],
    *,
    expected_device_ids: list[str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    expected = expected_device_ids if expected_device_ids is not None else parse_expected_devices()
    device_map = {d.device_id: d for d in devices}
    rows = [device_connectivity(d, now) for d in sorted(devices, key=lambda x: x.device_id)]

    online_ids = [r["device_id"] for r in rows if r["online"]]
    offline_ids = [r["device_id"] for r in rows if not r["online"]]

    missing_expected = [eid for eid in expected if eid not in device_map]
    expected_offline = [
        eid for eid in expected if eid in device_map and eid not in online_ids
    ]

    all_expected_online = len(expected) == 0 or (
        len(missing_expected) == 0 and len(expected_offline) == 0
    )
    ready = all_expected_online

    return {
        "checked_at": now,
        "online_threshold_seconds": settings.unifier_device_online_seconds,
        "expected_device_ids": expected,
        "total_registered": len(rows),
        "online_count": len(online_ids),
        "offline_count": len(offline_ids),
        "online_device_ids": online_ids,
        "offline_device_ids": offline_ids,
        "missing_expected": missing_expected,
        "expected_offline": expected_offline,
        "all_expected_online": all_expected_online,
        "ready_for_dispatch": ready,
        "devices": rows,
    }


def format_connectivity_message(report: dict[str, Any]) -> str:
    lines = [
        f"已注册 {report['total_registered']} 台 · 在线 {report['online_count']} · 离线 {report['offline_count']}",
        f"期望设备: {', '.join(report['expected_device_ids']) or '（未配置）'}",
    ]
    if report["missing_expected"]:
        lines.append(f"未注册: {', '.join(report['missing_expected'])}")
    if report["expected_offline"]:
        lines.append(f"期望但未在线: {', '.join(report['expected_offline'])}")
    if report["ready_for_dispatch"]:
        lines.append("联通性: 正常，可派活")
    elif report["expected_device_ids"]:
        lines.append("联通性: 异常，暂不建议派活")
    else:
        lines.append("联通性: 未配置期望设备，仅展示状态")
    return "\n".join(lines)


def connectivity_report_payload(
    report: dict[str, Any],
    *,
    hub_reachable: bool = True,
) -> dict[str, Any]:
    return {
        **report,
        "hub_reachable": hub_reachable,
        "message": format_connectivity_message(report),
    }
