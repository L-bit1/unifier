"""Hub 连接密码：异网开启时校验。

注意：公网映射进程从本机连 Hub，client 也是 127.0.0.1。
因此 /api/v1/mobile 在有连接密码时必须校验，不能因 loopback 免密。
其它本机 API（心跳、inbox）仍可 loopback 免密。
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


def access_token_path() -> Path:
    home = Path(os.environ.get("UNIFIER_HOME", Path.home() / ".unifier"))
    return home / "access-token.txt"


def current_access_token() -> str:
    path = access_token_path()
    if path.is_file():
        try:
            t = path.read_text(encoding="utf-8").strip()
            if t:
                return t
        except OSError:
            pass
    return (os.environ.get("UNIFIER_ACCESS_TOKEN") or "").strip()


def loopback_bypass_enabled() -> bool:
    return os.environ.get("UNIFIER_ACCESS_TOKEN_LOOPBACK_BYPASS", "1") not in (
        "0",
        "false",
        "False",
    )


def is_loopback(host: str | None) -> bool:
    if not host:
        return False
    h = host.split("%")[0]  # ipv6 zone
    return h in ("127.0.0.1", "::1", "localhost")


def is_mobile_api(path: str) -> bool:
    return path.startswith("/api/v1/mobile")


class AccessTokenMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path or "/"
        if path == "/" or path.startswith(
            ("/health", "/docs", "/openapi", "/redoc", "/static")
        ):
            return await call_next(request)

        token = current_access_token()
        if not token:
            return await call_next(request)

        client = request.client.host if request.client else None
        # 手机 API：有密码就必须带，防止映射进程经 loopback 绕过
        if not is_mobile_api(path):
            if loopback_bypass_enabled() and is_loopback(client):
                return await call_next(request)

        provided = (
            request.headers.get("x-unifier-token")
            or request.headers.get("X-Unifier-Token")
            or ""
        ).strip()
        if not provided:
            auth = request.headers.get("authorization") or ""
            if auth.lower().startswith("bearer "):
                provided = auth[7:].strip()

        if provided != token:
            return JSONResponse(
                status_code=401,
                content={
                    "ok": False,
                    "error": "bad_token",
                    "message": "连接密码不对，回电脑重新复制后再试",
                },
            )
        return await call_next(request)
