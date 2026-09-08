from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from typing import Any

from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestTooLarge(Exception):
    pass


def max_request_body_bytes() -> int:
    raw = os.getenv("MAX_REQUEST_BODY_BYTES", str(4 * 1024 * 1024))
    try:
        return max(64 * 1024, int(raw))
    except ValueError:
        return 4 * 1024 * 1024


class MaxRequestBodyMiddleware:
    """Bound request bodies without buffering them in application memory."""

    def __init__(self, app: ASGIApp, max_bytes: int | None = None) -> None:
        self.app = app
        self.max_bytes = max_bytes or max_request_body_bytes()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        content_length = _content_length(scope)
        if content_length is not None and content_length > self.max_bytes:
            await _too_large_response(self.max_bytes)(scope, receive, send)
            return

        consumed = 0

        async def limited_receive() -> Message:
            nonlocal consumed
            message = await receive()
            if message["type"] == "http.request":
                consumed += len(message.get("body", b""))
                if consumed > self.max_bytes:
                    raise RequestTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except RequestTooLarge:
            await _too_large_response(self.max_bytes)(scope, receive, send)


class SecurityHeadersMiddleware:
    """Apply conservative browser headers to API and bundled operator UI responses."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path") or "")

        async def secure_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("X-Frame-Options", "DENY")
                headers.setdefault("Referrer-Policy", "no-referrer")
                headers.setdefault(
                    "Permissions-Policy",
                    "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
                )
                if _sensitive_path(path):
                    headers.setdefault("Cache-Control", "no-store")
                if _hsts_enabled():
                    headers.setdefault(
                        "Strict-Transport-Security",
                        "max-age=31536000; includeSubDomains",
                    )
            await send(message)

        await self.app(scope, receive, secure_send)


def _content_length(scope: Scope) -> int | None:
    for raw_name, raw_value in scope.get("headers", []):
        if raw_name.lower() != b"content-length":
            continue
        try:
            return int(raw_value.decode("ascii"))
        except (ValueError, UnicodeDecodeError):
            return None
    return None


def _too_large_response(limit: int) -> JSONResponse:
    return JSONResponse(
        {"detail": f"Request body exceeds the configured {limit}-byte limit"},
        status_code=413,
    )


def _sensitive_path(path: str) -> bool:
    return path.startswith(("/schools/", "/users", "/auth/"))


def _hsts_enabled() -> bool:
    return os.getenv("ENABLE_HSTS", "true").strip().lower() not in {"0", "false", "no", "off"}
