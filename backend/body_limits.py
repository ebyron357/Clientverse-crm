"""Request body size limits, enforced on the bytes actually received.

Any visitor can register and administer a tenant, and some routes need no account at all
(the website intake door, the client portal). Without a limit one request can make the
server hold as much as the sender cares to send -- a CSV import grew memory about a
hundred times its body size -- and every tenant shares that process.

A declared `Content-Length` over the limit is refused before anything is read. A body
sent without one (chunked) is counted as it arrives and refused the moment it passes the
limit, so leaving the header out is no way around it. A body within the limit is
buffered and handed to the application unchanged, which keeps raw-body consumers such as
the Stripe signature check exact.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any, Optional

Scope = dict[str, Any]
Message = dict[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

KB = 1024
MB = 1024 * KB

# Longest prefix first. A route not under /api/ (the SPA) carries no body worth limiting.
LIMITS: tuple[tuple[str, int], ...] = (
    ("/api/intake/public/", 16 * KB),   # a few form fields from a public website
    ("/api/portal/", 16 * KB),          # a client's request through a portal link
    ("/api/import/", 3 * MB),           # a CSV of at most MAX_IMPORT_ROWS rows
    ("/api/", 1 * MB),                  # everything else: JSON forms and webhooks
)

BODY_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def limit_for(path: str) -> Optional[int]:
    for prefix, limit in LIMITS:
        if path.startswith(prefix):
            return limit
    return None


class BodySizeLimit:
    """ASGI middleware refusing a request body larger than its route allows (413)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http" or scope.get("method") not in BODY_METHODS:
            await self.app(scope, receive, send)
            return
        limit = limit_for(scope.get("path") or "")
        if limit is None:
            await self.app(scope, receive, send)
            return

        declared = dict(scope.get("headers") or []).get(b"content-length")
        if declared and declared.isdigit() and int(declared) > limit:
            await self._refuse(send, limit)
            return

        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body = message.get("body", b"")
            size += len(body)
            if size > limit:
                await self._refuse(send, limit)
                return
            chunks.append(body)
            if not message.get("more_body", False):
                break

        buffered = b"".join(chunks)
        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": buffered, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)

    @staticmethod
    async def _refuse(send: Send, limit: int) -> None:
        body = json.dumps({"detail": f"Request body too large (limit {limit // KB} KB)"}).encode()
        await send({"type": "http.response.start", "status": 413,
                    "headers": [(b"content-type", b"application/json"),
                                (b"content-length", str(len(body)).encode()),
                                (b"connection", b"close")]})
        await send({"type": "http.response.body", "body": body})
