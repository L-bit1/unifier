"""联合器 → 自研AI 灵魂 (:8200) / Aether (:8100) / Lab (:8790) 桥接。"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx

from app.config import settings


def _session_id() -> str:
    return (
        os.environ.get("CUSTOM_AI_SESSION_ID")
        or os.environ.get("SOUL_SESSION_ID")
        or getattr(settings, "custom_ai_session_id", "soul-unified")
    )


async def soul_chat(
    *,
    message: str,
    session_id: str | None = None,
    domain: str = "general",
) -> Dict[str, Any]:
    base = settings.custom_ai_url.rstrip("/")
    sid = session_id or _session_id()
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{base}/v1/chat",
            json={"message": message, "session_id": sid, "domain": domain},
        )
        if resp.status_code == 200:
            data = resp.json()
            return {"ok": True, "reply": data.get("reply", ""), "raw": data}
        return {"ok": False, "http_status": resp.status_code, "detail": resp.text[:500]}


async def aether_task(
    *,
    message: str,
    web_goal: str | None = None,
    session_id: str | None = None,
) -> Dict[str, Any]:
    base = settings.aether_url.rstrip("/")
    sid = session_id or _session_id()
    body: Dict[str, Any] = {"message": message, "session_id": sid}
    if web_goal:
        body["web_goal"] = web_goal
    async with httpx.AsyncClient(timeout=180) as client:
        try:
            resp = await client.post(f"{base}/agent/task", json=body)
            return {"ok": resp.status_code == 200, "status": resp.status_code, "body": resp.json()}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}


async def _ping(url: str, path: str = "/health") -> Dict[str, Any]:
    target = f"{url.rstrip('/')}{path}"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(target)
            body = resp.json() if "json" in resp.headers.get("content-type", "") else {}
            return {
                "ok": resp.status_code == 200,
                "url": target,
                "status": resp.status_code,
                "body": body if isinstance(body, dict) else {},
            }
    except Exception as exc:
        return {"ok": False, "url": target, "error": str(exc)}


async def stack_health() -> Dict[str, Any]:
    soul = await _ping(settings.custom_ai_url)
    aether = await _ping(settings.aether_url)
    lab = await _ping(settings.lab_queue_url)
    hub_ok = True
    overall = "ok"
    for item in (soul, aether, lab):
        if not item.get("ok"):
            overall = "degraded"
    return {
        "ok": hub_ok,
        "overall": overall,
        "session_id": _session_id(),
        "components": {
            "unifier_hub": {"ok": True},
            "custom_ai_soul": soul,
            "aether": aether,
            "lab_queue": lab,
        },
    }


def soul_chat_sync(*, message: str, session_id: str | None = None, domain: str = "general") -> Dict[str, Any]:
    base = settings.custom_ai_url.rstrip("/")
    sid = session_id or _session_id()
    try:
        resp = httpx.post(
            f"{base}/v1/chat",
            json={"message": message, "session_id": sid, "domain": domain},
            timeout=120,
        )
        if resp.status_code == 200:
            data = resp.json()
            return {"ok": True, "reply": data.get("reply", ""), "raw": data}
        return {"ok": False, "http_status": resp.status_code, "detail": resp.text[:500]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _ping_sync(url: str, path: str = "/health") -> Dict[str, Any]:
    target = f"{url.rstrip('/')}{path}"
    try:
        resp = httpx.get(target, timeout=5)
        body = resp.json() if "json" in resp.headers.get("content-type", "") else {}
        return {
            "ok": resp.status_code == 200,
            "url": target,
            "status": resp.status_code,
            "body": body if isinstance(body, dict) else {},
        }
    except Exception as exc:
        return {"ok": False, "url": target, "error": str(exc)}


def stack_health_sync() -> Dict[str, Any]:
    soul = _ping_sync(settings.custom_ai_url)
    aether = _ping_sync(settings.aether_url)
    lab = _ping_sync(settings.lab_queue_url)
    overall = "ok"
    for item in (soul, aether, lab):
        if not item.get("ok"):
            overall = "degraded"
    return {
        "ok": True,
        "overall": overall,
        "session_id": _session_id(),
        "components": {
            "unifier_hub": {"ok": True},
            "custom_ai_soul": soul,
            "aether": aether,
            "lab_queue": lab,
        },
    }
