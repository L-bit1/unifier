"""联合器 → n8n 自动化桥接（事件出站 + 健康检查）。"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def n8n_configured() -> bool:
    return settings.n8n_enabled and bool(settings.n8n_webhook_url)


def _ping_sync(url: str, path: str = "/healthz") -> dict[str, Any]:
    target = f"{url.rstrip('/')}{path}"
    try:
        resp = httpx.get(target, timeout=5)
        return {
            "ok": resp.status_code == 200,
            "url": target,
            "status": resp.status_code,
        }
    except Exception as exc:
        return {"ok": False, "url": target, "error": str(exc)}


async def _ping(url: str, path: str = "/healthz") -> dict[str, Any]:
    target = f"{url.rstrip('/')}{path}"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(target)
            return {
                "ok": resp.status_code == 200,
                "url": target,
                "status": resp.status_code,
            }
    except Exception as exc:
        return {"ok": False, "url": target, "error": str(exc)}


def n8n_health_sync() -> dict[str, Any]:
    base = settings.n8n_url.rstrip("/")
    if not settings.n8n_enabled:
        return {
            "ok": False,
            "enabled": False,
            "url": base,
            "webhook_url": settings.n8n_webhook_url or None,
            "error": "n8n 未启用（设置 N8N_ENABLED=true）",
        }
    health = _ping_sync(base)
    return {
        "ok": health.get("ok", False),
        "enabled": True,
        "url": base,
        "webhook_url": settings.n8n_webhook_url,
        "health": health,
    }


async def n8n_health() -> dict[str, Any]:
    base = settings.n8n_url.rstrip("/")
    if not settings.n8n_enabled:
        return {
            "ok": False,
            "enabled": False,
            "url": base,
            "webhook_url": settings.n8n_webhook_url or None,
            "error": "n8n 未启用（设置 N8N_ENABLED=true）",
        }
    health = await _ping(base)
    return {
        "ok": health.get("ok", False),
        "enabled": True,
        "url": base,
        "webhook_url": settings.n8n_webhook_url,
        "health": health,
    }


def emit_to_n8n_sync(event_type: str, data: dict[str, Any]) -> dict[str, Any]:
    """同步发送事件到 n8n Webhook（失败只记日志，不阻断 Hub）。"""
    if not n8n_configured():
        return {"ok": False, "skipped": True, "reason": "n8n 未配置"}

    payload = {
        "event": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "unifier-hub",
        "data": data,
    }
    url = settings.n8n_webhook_url
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if settings.n8n_api_key:
        headers["X-N8N-API-KEY"] = settings.n8n_api_key

    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=10)
        ok = 200 <= resp.status_code < 300
        if not ok:
            logger.warning("n8n webhook %s → HTTP %s: %s", event_type, resp.status_code, resp.text[:200])
        return {"ok": ok, "status": resp.status_code, "url": url}
    except Exception as exc:
        logger.warning("n8n webhook %s 失败: %s", event_type, exc)
        return {"ok": False, "error": str(exc), "url": url}


async def emit_to_n8n(event_type: str, data: dict[str, Any]) -> dict[str, Any]:
    if not n8n_configured():
        return {"ok": False, "skipped": True, "reason": "n8n 未配置"}

    payload = {
        "event": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "unifier-hub",
        "data": data,
    }
    url = settings.n8n_webhook_url
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if settings.n8n_api_key:
        headers["X-N8N-API-KEY"] = settings.n8n_api_key

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload, headers=headers)
            ok = 200 <= resp.status_code < 300
            if not ok:
                logger.warning("n8n webhook %s → HTTP %s", event_type, resp.status_code)
            return {"ok": ok, "status": resp.status_code, "url": url}
    except Exception as exc:
        logger.warning("n8n webhook %s 失败: %s", event_type, exc)
        return {"ok": False, "error": str(exc), "url": url}
