import json
import logging
import socket
import sys
import time
from datetime import UTC, datetime
from typing import TextIO

from starlette.types import ASGIApp, Message, Receive, Scope, Send

LOGGER_NAME = "pdf_extractor.access"


def create_access_logger(
    *,
    stream: TextIO | None = None,
    name: str = LOGGER_NAME,
) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers.clear()

    handler = logging.StreamHandler(stream if stream is not None else sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)

    return logger


class AccessLogMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        logger: logging.Logger | None = None,
        replica: str | None = None,
    ) -> None:
        self.app = app
        self._logger = logger or create_access_logger()
        self._replica = replica or socket.gethostname()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            self._logger.info(
                json.dumps(
                    {
                        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                        "event": "http_request",
                        "replica": self._replica,
                        "method": scope.get("method"),
                        "path": scope.get("path"),
                        "status": status_code,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                    },
                    separators=(",", ":"),
                )
            )
