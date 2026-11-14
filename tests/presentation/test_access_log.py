import asyncio
import io
import json
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

from presentation.access_log import AccessLogMiddleware, create_access_logger


def build_app(logger, **middleware_kwargs) -> FastAPI:
    test_app = FastAPI()
    test_app.add_middleware(AccessLogMiddleware, logger=logger, **middleware_kwargs)

    @test_app.get("/ping")
    def ping() -> dict[str, bool]:
        return {"ok": True}

    return test_app


def read_payload(stream: io.StringIO) -> dict:
    return json.loads(stream.getvalue().strip())


def test_access_log_emits_json_with_replica_and_request_fields():
    stream = io.StringIO()
    logger = create_access_logger(stream=stream, name="tests.access")
    test_app = build_app(logger, replica="app-test-1")

    with TestClient(test_app) as client:
        response = client.get("/ping")

    assert response.status_code == 200

    payload = read_payload(stream)
    assert payload["event"] == "http_request"
    assert payload["replica"] == "app-test-1"
    assert payload["method"] == "GET"
    assert payload["path"] == "/ping"
    assert payload["status"] == 200
    assert payload["duration_ms"] >= 0
    assert payload["timestamp"].endswith("Z")


def test_access_log_uses_hostname_when_replica_is_not_provided(monkeypatch):
    stream = io.StringIO()
    logger = create_access_logger(stream=stream, name="tests.access.hostname")
    monkeypatch.setattr(
        "presentation.access_log.socket.gethostname",
        lambda: "replica-host-1",
    )
    test_app = build_app(logger)

    with TestClient(test_app) as client:
        client.get("/ping")

    assert read_payload(stream)["replica"] == "replica-host-1"


def test_access_log_records_500_when_handler_raises():
    stream = io.StringIO()
    logger = create_access_logger(stream=stream, name="tests.access.error")
    test_app = FastAPI()
    test_app.add_middleware(AccessLogMiddleware, logger=logger, replica="app-test-1")

    @test_app.get("/boom")
    def boom() -> None:
        raise RuntimeError("boom")

    with TestClient(test_app, raise_server_exceptions=False) as client:
        response = client.get("/boom")

    assert response.status_code == 500
    assert read_payload(stream)["status"] == 500


def test_access_log_ignores_non_http_scopes():
    stream = io.StringIO()
    logger = create_access_logger(stream=stream, name="tests.access.lifespan")
    seen: list[str] = []

    async def inner_app(scope, receive, send) -> None:
        seen.append(scope["type"])

    middleware = AccessLogMiddleware(inner_app, logger=logger, replica="app-test-1")

    async def receive() -> dict:
        return {"type": "lifespan.startup"}

    async def send(_message) -> None:
        return None

    asyncio.run(middleware({"type": "lifespan"}, receive, send))

    assert seen == ["lifespan"]
    assert stream.getvalue() == ""


def test_create_access_logger_defaults_to_stdout():
    logger = create_access_logger(name="tests.access.stdout")
    try:
        assert logger.handlers
        assert logger.handlers[0].stream is sys.stdout
    finally:
        logger.handlers.clear()
