from __future__ import annotations

import json
import time
from typing import Any

import httpx

from app.config import settings

FEISHU_API = "https://open.feishu.cn/open-apis"


class FeishuError(RuntimeError):
    pass


class FeishuClient:
    def __init__(self) -> None:
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    def _ensure_configured(self) -> None:
        if not settings.feishu_configured:
            raise FeishuError("未配置 FEISHU_APP_ID / FEISHU_APP_SECRET")

    async def tenant_access_token(self) -> str:
        self._ensure_configured()
        now = time.time()
        if self._token and now < self._token_expires_at - 60:
            return self._token

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{FEISHU_API}/auth/v3/tenant_access_token/internal",
                json={
                    "app_id": settings.feishu_app_id,
                    "app_secret": settings.feishu_app_secret,
                },
            )
            data = resp.json()
        if data.get("code") != 0:
            raise FeishuError(f"获取 tenant_access_token 失败: {data.get('msg')}")
        self._token = data["tenant_access_token"]
        self._token_expires_at = now + int(data.get("expire", 7200))
        return self._token

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = await self.tenant_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.request(
                method,
                f"{FEISHU_API}{path}",
                params=params,
                json=json_body,
                headers=headers,
            )
            data = resp.json()
        if data.get("code") != 0:
            raise FeishuError(data.get("msg") or "飞书 API 错误")
        return data

    async def send_text_to_chat(self, chat_id: str, text: str) -> str | None:
        data = await self._request(
            "POST",
            "/im/v1/messages",
            params={"receive_id_type": "chat_id"},
            json_body={
                "receive_id": chat_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
        )
        return (data.get("data") or {}).get("message_id")

    async def reply_text(self, message_id: str, text: str) -> str | None:
        data = await self._request(
            "POST",
            f"/im/v1/messages/{message_id}/reply",
            json_body={
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
        )
        return (data.get("data") or {}).get("message_id")

    async def send_interactive_to_chat(self, chat_id: str, card: dict) -> str | None:
        data = await self._request(
            "POST",
            "/im/v1/messages",
            params={"receive_id_type": "chat_id"},
            json_body={
                "receive_id": chat_id,
                "msg_type": "interactive",
                "content": json.dumps(card, ensure_ascii=False),
            },
        )
        return (data.get("data") or {}).get("message_id")

    async def reply_interactive(self, message_id: str, card: dict) -> str | None:
        data = await self._request(
            "POST",
            f"/im/v1/messages/{message_id}/reply",
            json_body={
                "msg_type": "interactive",
                "content": json.dumps(card, ensure_ascii=False),
            },
        )
        return (data.get("data") or {}).get("message_id")


feishu_client = FeishuClient()
