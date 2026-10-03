"""Require HTTPS in production and apply response policy to middleware errors."""

from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse


class TransportSecurityMiddleware:
    def __init__(self, app, *, production=False):
        self.app = app
        self.production = production

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def secure_send(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["Cache-Control"] = "no-store"
                headers["Pragma"] = "no-cache"
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["Referrer-Policy"] = "no-referrer"
                if scope["scheme"] == "https":
                    headers["Strict-Transport-Security"] = (
                        "max-age=31536000; includeSubDomains"
                    )
                if self.production and scope["path"] not in {"/docs", "/redoc"}:
                    headers["Content-Security-Policy"] = (
                        "default-src 'none'; frame-ancestors 'none'"
                    )
            await send(message)

        if self.production and scope["scheme"] != "https":
            response = JSONResponse({"detail": "HTTPS required"}, status_code=400)
            return await response(scope, receive, secure_send)
        await self.app(scope, receive, secure_send)
