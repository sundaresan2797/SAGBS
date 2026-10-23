import logging
import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("ems.requests")


class RequestLoggingMiddleware:
    """Pure ASGI middleware (not BaseHTTPMiddleware).

    BaseHTTPMiddleware runs the downstream app in a separate anyio task via
    call_next, which breaks resources bound to a single connection/task (e.g.
    a request-scoped asyncpg session) in some ASGI transports. A plain ASGI
    middleware avoids that extra task hop entirely.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status_code = 0

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        await self.app(scope, receive, send_wrapper)

        duration_ms = (time.perf_counter() - start) * 1000
        logger.info("%s %s -> %s (%.1fms)", scope["method"], scope["path"], status_code, duration_ms)
