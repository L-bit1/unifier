from __future__ import annotations

import json
import os
from typing import Any

import httpx

DEFAULT_HUB = "http://127.0.0.1:8787"


def hub_url() -> str:
    return os.environ.get("HUB_URL", DEFAULT_HUB).rstrip("/")


def device_id() -> str:
    return os.environ.get("UNIFIER_DEVICE_ID", os.environ.get("DEVICE_ID", ""))


def agent_id() -> str:
    return os.environ.get("UNIFIER_AGENT_ID", os.environ.get("AGENT_ID", "cursor"))


def reviewer_id() -> str:
    d, a = device_id(), agent_id()
    return f"{d}:{a}" if d else a


def request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> Any:
    url = f"{hub_url()}{path}"
    with httpx.Client(timeout=30.0) as client:
        resp = client.request(method, url, params=params, json=json_body)
        if resp.status_code >= 400:
            try:
                detail = resp.json()
            except Exception:
                detail = resp.text
            raise RuntimeError(f"Hub {resp.status_code}: {detail}")
        if not resp.content:
            return {}
        return resp.json()


def pretty(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)
