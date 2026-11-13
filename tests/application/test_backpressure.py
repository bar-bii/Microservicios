import asyncio

import httpx
import pytest

from application.config import ConcurrencyConfig
from application.document_service import DocumentService, QueueFullError
from application.pdf_extractor import ExtractionResult
from presentation.main import app
from presentation.routers.extract import get_document_service

PDF_BYTES = b"%PDF-1.7 fake pdf payload"


class FakeExtractor:
    def extract(self, pdf_bytes: bytes) -> ExtractionResult:
        return ExtractionResult(content="Hello PDF", page_count=1)


class ConcurrencyTracker:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0

    def enter(self) -> None:
        self.active += 1
        self.max_active = max(self.max_active, self.active)

    def exit(self) -> None:
        self.active -= 1


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def controlled_thread(monkeypatch):
    gate = asyncio.Event()
    tracker = ConcurrencyTracker()

    async def fake_to_thread(func, *args, **kwargs):
        tracker.enter()
        try:
            await gate.wait()
        finally:
            tracker.exit()
        return func(*args, **kwargs)

    monkeypatch.setattr(
        "application.document_service.asyncio.to_thread",
        fake_to_thread,
    )
    return gate, tracker


async def wait_until_pending(service: DocumentService, expected: int) -> None:
    async def pending_condition() -> None:
        while service.pending < expected:
            await asyncio.sleep(0)

    await asyncio.wait_for(pending_condition(), timeout=2)


def post_extract(client: httpx.AsyncClient) -> asyncio.Task:
    return asyncio.create_task(
        client.post(
            "/extract",
            files={"file": ("sample.pdf", PDF_BYTES, "application/pdf")},
        )
    )


def test_concurrency_config_reads_environment(monkeypatch):
    monkeypatch.setenv("WORKER_POOL_SIZE", "7")
    monkeypatch.setenv("MAX_QUEUE_SIZE", "250")

    config = ConcurrencyConfig.from_env()

    assert config.worker_pool_size == 7
    assert config.max_queue_size == 250
    assert config.capacity == 257


def test_concurrency_config_uses_defaults(monkeypatch):
    monkeypatch.delenv("WORKER_POOL_SIZE", raising=False)
    monkeypatch.delenv("MAX_QUEUE_SIZE", raising=False)

    config = ConcurrencyConfig.from_env()

    assert config.worker_pool_size == 4
    assert config.max_queue_size == 100
    assert config.capacity == 104


@pytest.mark.parametrize("name", ["WORKER_POOL_SIZE", "MAX_QUEUE_SIZE"])
@pytest.mark.parametrize("raw_value", ["0", "-1", "abc"])
def test_concurrency_config_rejects_invalid_values(monkeypatch, name, raw_value):
    monkeypatch.delenv("WORKER_POOL_SIZE", raising=False)
    monkeypatch.delenv("MAX_QUEUE_SIZE", raising=False)
    monkeypatch.setenv(name, raw_value)

    with pytest.raises(ValueError, match=name):
        ConcurrencyConfig.from_env()


@pytest.mark.anyio
async def test_service_rejects_requests_when_queue_is_full(controlled_thread):
    gate, tracker = controlled_thread
    service = DocumentService(
        FakeExtractor(),
        config=ConcurrencyConfig(worker_pool_size=2, max_queue_size=2),
    )

    accepted = [asyncio.create_task(service.process(PDF_BYTES)) for _ in range(4)]
    await wait_until_pending(service, 4)

    assert tracker.active == 2
    assert service.pending == 4

    with pytest.raises(QueueFullError):
        await service.process(PDF_BYTES)

    assert service.pending == 4

    gate.set()
    results = await asyncio.gather(*accepted)

    assert all(result.content == "Hello PDF" for result in results)
    assert service.pending == 0
    assert tracker.max_active == 2


@pytest.mark.anyio
async def test_extract_returns_503_when_backpressure_queue_is_full(controlled_thread):
    gate, _ = controlled_thread
    service = DocumentService(
        FakeExtractor(),
        config=ConcurrencyConfig(worker_pool_size=2, max_queue_size=2),
    )
    app.dependency_overrides[get_document_service] = lambda: service

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            accepted = [post_extract(client) for _ in range(4)]
            await wait_until_pending(service, 4)

            rejected = await asyncio.gather(*(post_extract(client) for _ in range(20)))

            assert all(response.status_code == 503 for response in rejected)
            assert all(response.headers["retry-after"] == "1" for response in rejected)
            assert all("detail" in response.json() for response in rejected)
            assert service.pending == 4

            gate.set()
            successful = await asyncio.gather(*accepted)

            assert all(response.status_code == 200 for response in successful)
            assert all(
                response.json() == {"content": "Hello PDF", "page_count": 1}
                for response in successful
            )
            assert service.pending == 0
    finally:
        app.dependency_overrides.clear()
