"""Bind authenticated public requests to isolated storage."""

import sqlite3

from aegis.security.public_limits import public_limits

from anyio import CancelScope
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse

from aegis.api.auth import SECURITY_HEADERS
from aegis.security.public_sessions import public_sessions
from aegis.security.request_storage import (
    database_context,
    public_runtime,
)
from aegis.security.sessions import SessionDenied


class PublicStorageMiddleware:

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not public_runtime():
            await self.app(scope, receive, send)
            return

        if scope["path"] == "/health":
            await self.app(scope, receive, send)
            return

        if not public_limits.slots.acquire(blocking=False):
            response = JSONResponse(
                {"detail": "Public service busy"},
                status_code=429,
                headers={
                    **SECURITY_HEADERS,
                    "Retry-After": "5",
                },
            )
            await response(scope, receive, send)
            return

        try:
            await self.handle_request(scope, receive, send)
        finally:
            public_limits.slots.release()

    async def handle_request(self, scope, receive, send):
        request = Request(scope)

        if request.url.path in {
            "/health",
            "/api/v1/auth/guest",
            "/api/v1/auth/login",
            "/api/v1/chat",
            "/api/v1/inference",
            "/api/v1/conversation",
        }:
            await self.app(scope, receive, send)
            return

        async def reject(status, detail):
            response = JSONResponse(
                {"detail": detail},
                status_code=status,
                headers=SECURITY_HEADERS,
            )
            await response(scope, receive, send)

        for name in (
            "authorization",
            "x-aegis-gateway-token",
            "origin",
        ):
            if len(request.headers.getlist(name)) > 1:
                await reject(400, "Invalid request headers")
                return

        # Authenticate the internal gateway before looking
        # up or extending a visitor session.
        from aegis.security.access import require_gateway
        from fastapi import HTTPException

        try:
            require_gateway(request)
        except HTTPException:
            await reject(403, "Unauthorized gateway")
            return

        if request.headers.get("origin") is not None:
            await reject(403, "Request denied")
            return

        scheme, _, token = request.headers.get(
            "authorization", "",
        ).partition(" ")

        if scheme.lower() != "bearer":
            await reject(401, "Authentication required")
            return

        lease = public_sessions.lease(token)

        try:
            with CancelScope(shield=True):
                path = await run_in_threadpool(lease.__enter__)
        except SessionDenied:
            await reject(401, "Invalid or expired session")
            return
        except (sqlite3.Error, OSError):
            await reject(503, "Session storage unavailable")
            return

        try:
            if not public_limits.allow_request(token):
                await reject(429, "Public request limit reached")
                return

            with database_context(path):
                await self.app(scope, receive, send)
        finally:
            with CancelScope(shield=True):
                await run_in_threadpool(
                    lease.__exit__, None, None, None,
                )
