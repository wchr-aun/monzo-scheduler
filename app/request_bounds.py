"""Bound request parsing and concurrent application work before route execution."""

import asyncio

from starlette.responses import JSONResponse


class RequestBoundsMiddleware:
    def __init__(
        self,
        app,
        *,
        max_body_bytes=16384,
        max_concurrent_requests=64,
        body_timeout_seconds=10,
    ):
        self.app = app
        self.max_body_bytes = max_body_bytes
        self.max_concurrent_requests = max_concurrent_requests
        self.body_timeout_seconds = body_timeout_seconds
        self.active = 0

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def reject(code, detail):
            response = JSONResponse(
                {"detail": detail},
                status_code=code,
                headers={
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                    "Referrer-Policy": "no-referrer",
                    "X-Frame-Options": "DENY",
                },
            )
            await response(scope, receive, send)

        if self.active >= self.max_concurrent_requests:
            return await reject(503, "Request capacity reached")
        self.active += 1
        try:
            for name, value in scope["headers"]:
                if name.lower() == b"content-length":
                    try:
                        length = int(value)
                    except ValueError:
                        return await reject(400, "Invalid Content-Length")
                    if length < 0:
                        return await reject(400, "Invalid Content-Length")
                    if length > self.max_body_bytes:
                        return await reject(413, "Request body too large")
            body = bytearray()
            try:
                async with asyncio.timeout(self.body_timeout_seconds):
                    while True:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            return
                        body.extend(message.get("body", b""))
                        if len(body) > self.max_body_bytes:
                            return await reject(413, "Request body too large")
                        if not message.get("more_body", False):
                            break
            except TimeoutError:
                return await reject(408, "Request body timed out")
            delivered = False

            async def bounded_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {
                        "type": "http.request",
                        "body": bytes(body),
                        "more_body": False,
                    }
                return await receive()

            await self.app(scope, bounded_receive, send)
        finally:
            self.active -= 1
