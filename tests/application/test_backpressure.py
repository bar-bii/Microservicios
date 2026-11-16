import asyncio
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest

from application.config import ConcurrencyConfig, UploadConfig
from application.document_service import DocumentService, QueueFullError
from application.pdf_extractor import ExtractionResult, PdfiumPDFExtractor
from presentation.main import app
from presentation.routers.extract import get_document_service, get_upload_config

PDF_BYTES = b"%PDF-1.7 fake pdf payload"
HELLO_PDF = (Path(__file__).parent / "fixtures" / "hello.pdf").read_bytes()
MULTIPART_BOUNDARY = "backpressure-test-boundary"
MULTIPART_HEADERS = {"Content-Type": f"multipart/form-data; boundary={MULTIPART_BOUNDARY}"}


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


@pytest.mark.parametrize("name", ["WORKER_POOL_SIZE", "MAX_QUEUE_SIZE", "MAX_QUEUE_BYTES"])
@pytest.mark.parametrize("raw_value", ["0", "-1", "abc"])
def test_concurrency_config_rejects_invalid_values(monkeypatch, name, raw_value):
    monkeypatch.delenv("WORKER_POOL_SIZE", raising=False)
    monkeypatch.delenv("MAX_QUEUE_SIZE", raising=False)
    monkeypatch.setenv(name, raw_value)

    with pytest.raises(ValueError, match=name):
        ConcurrencyConfig.from_env()


def test_concurrency_config_reads_the_byte_limit(monkeypatch):
    monkeypatch.setenv("MAX_QUEUE_BYTES", "1048576")

    assert ConcurrencyConfig.from_env().max_queue_bytes == 1048576


@pytest.mark.parametrize("raw_value", [None, ""])
def test_concurrency_config_has_no_byte_limit_when_unset_or_empty(monkeypatch, raw_value):
    monkeypatch.delenv("MAX_QUEUE_BYTES", raising=False)
    if raw_value is not None:
        monkeypatch.setenv("MAX_QUEUE_BYTES", raw_value)

    assert ConcurrencyConfig.from_env().max_queue_bytes is None


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


def multipart_body(
    payload: bytes,
    *,
    field: str = "file",
    content_type: str = "application/pdf",
) -> bytes:
    header = (
        f"--{MULTIPART_BOUNDARY}\r\n"
        f'Content-Disposition: form-data; name="{field}"; filename="sample.pdf"\r\n'
        f"Content-Type: {content_type}\r\n"
        "\r\n"
    ).encode("ascii")
    footer = f"\r\n--{MULTIPART_BOUNDARY}--\r\n".encode("ascii")
    return header + payload + footer


def single_slot_service() -> DocumentService:
    return DocumentService(
        FakeExtractor(),
        config=ConcurrencyConfig(worker_pool_size=1, max_queue_size=1),
    )


@pytest.fixture
def pdf_service() -> Iterator[DocumentService]:
    service = DocumentService(
        PdfiumPDFExtractor(),
        config=ConcurrencyConfig(worker_pool_size=1, max_queue_size=1),
    )
    app.dependency_overrides[get_document_service] = lambda: service
    app.dependency_overrides[get_upload_config] = lambda: UploadConfig(
        max_upload_bytes=len(HELLO_PDF)
    )
    try:
        yield service
    finally:
        app.dependency_overrides.clear()


def asgi_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )


def test_admit_reserves_a_slot_until_the_block_exits():
    service = single_slot_service()

    with service.admit():
        assert service.pending == 1

    assert service.pending == 0


def test_admit_releases_the_slot_when_the_block_raises():
    service = single_slot_service()

    with pytest.raises(RuntimeError), service.admit():
        raise RuntimeError("request failed after admission")

    assert service.pending == 0


def test_admit_raises_queue_full_error_at_capacity():
    service = single_slot_service()

    with service.admit(), service.admit():
        with pytest.raises(QueueFullError), service.admit():
            pass

        assert service.pending == 2


@pytest.mark.anyio
async def test_process_admitted_runs_inside_the_existing_reservation():
    service = single_slot_service()

    with service.admit(), service.admit():
        result = await service.process_admitted(PDF_BYTES)

        assert service.pending == 2

    assert result == ExtractionResult(content="Hello PDF", page_count=1)
    assert service.pending == 0


@pytest.mark.anyio
async def test_extract_returns_503_without_reading_body_when_queue_is_full(pdf_service):
    body_was_read = False

    async def body() -> AsyncIterator[bytes]:
        nonlocal body_was_read
        body_was_read = True
        yield multipart_body(HELLO_PDF)

    with pdf_service.admit(), pdf_service.admit():
        async with asgi_client() as client:
            response = await client.post("/extract", content=body(), headers=MULTIPART_HEADERS)

        assert pdf_service.pending == 2

    assert response.status_code == 503
    assert response.headers["retry-after"] == "1"
    assert not body_was_read


@pytest.mark.anyio
async def test_extract_holds_a_reservation_while_reading_the_body(pdf_service):
    pending_when_body_is_read: list[int] = []

    async def body() -> AsyncIterator[bytes]:
        pending_when_body_is_read.append(pdf_service.pending)
        yield multipart_body(HELLO_PDF)

    async with asgi_client() as client:
        response = await client.post("/extract", content=body(), headers=MULTIPART_HEADERS)

    assert response.status_code == 200
    assert response.json() == {"content": "Hello PDF", "page_count": 1}
    assert pending_when_body_is_read == [1]
    assert pdf_service.pending == 0


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("body", "expected_status"),
    [
        pytest.param(multipart_body(HELLO_PDF, content_type="text/plain"), 415, id="mime"),
        pytest.param(multipart_body(HELLO_PDF + b"\n"), 413, id="size"),
        pytest.param(multipart_body(b"not a pdf"), 400, id="invalid-pdf"),
        pytest.param(multipart_body(HELLO_PDF, field="other"), 422, id="missing-file"),
    ],
)
async def test_extract_releases_the_reservation_when_the_upload_is_rejected(
    pdf_service, body, expected_status
):
    async with asgi_client() as client:
        response = await client.post("/extract", content=body, headers=MULTIPART_HEADERS)

    assert response.status_code == expected_status
    assert pdf_service.pending == 0


@pytest.mark.anyio
async def test_extract_answers_499_when_the_client_disconnects_mid_upload(pdf_service):
    incoming = iter(
        [
            {"type": "http.request", "body": multipart_body(HELLO_PDF)[:64], "more_body": True},
            {"type": "http.disconnect"},
        ]
    )
    sent: list[dict] = []

    async def receive() -> dict:
        return next(incoming)

    async def send(message: dict) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/extract",
        "raw_path": b"/extract",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"content-type", MULTIPART_HEADERS["Content-Type"].encode("ascii"))],
        "client": ("testclient", 50000),
        "server": ("test", 80),
    }

    await app(scope, receive, send)

    assert sent[0]["status"] == 499
    assert pdf_service.pending == 0


def byte_limited_service(max_queue_bytes: int) -> DocumentService:
    return DocumentService(
        FakeExtractor(),
        config=ConcurrencyConfig(
            worker_pool_size=1,
            max_queue_size=10,
            max_queue_bytes=max_queue_bytes,
        ),
    )


def test_admit_rejects_a_request_that_does_not_fit_in_the_byte_limit():
    service = byte_limited_service(100)

    with service.admit(60):
        with pytest.raises(QueueFullError), service.admit(41):
            pass

        assert service.pending == 1
        assert service.pending_bytes == 60


def test_admit_accepts_a_smaller_request_that_still_fits():
    service = byte_limited_service(100)

    with service.admit(60), service.admit(40):
        assert service.pending_bytes == 100


def test_admit_releases_the_bytes_when_the_block_exits():
    service = byte_limited_service(100)

    with service.admit(100):
        pass

    with service.admit(100):
        assert service.pending_bytes == 100

    assert service.pending_bytes == 0


def test_admit_releases_the_bytes_when_the_block_raises():
    service = byte_limited_service(100)

    with pytest.raises(RuntimeError), service.admit(100):
        raise RuntimeError("request failed after admission")

    assert service.pending_bytes == 0


def test_an_idle_service_admits_a_request_larger_than_the_byte_limit():
    service = byte_limited_service(100)

    with service.admit(500):
        assert service.pending_bytes == 500

        with pytest.raises(QueueFullError), service.admit(1):
            pass


def test_admit_ignores_sizes_without_a_byte_limit():
    service = single_slot_service()

    with service.admit(10**12), service.admit(10**12):
        assert service.pending == 2


@pytest.mark.anyio
async def test_process_counts_the_pdf_bytes_against_the_limit(controlled_thread):
    gate, _ = controlled_thread
    service = byte_limited_service(len(PDF_BYTES))

    accepted = asyncio.create_task(service.process(PDF_BYTES))
    await wait_until_pending(service, 1)

    assert service.pending_bytes == len(PDF_BYTES)
    with pytest.raises(QueueFullError):
        await service.process(PDF_BYTES)

    gate.set()
    await accepted
    assert service.pending_bytes == 0


@pytest.fixture
def byte_limited_pdf_service() -> Iterator[DocumentService]:
    service = DocumentService(
        PdfiumPDFExtractor(),
        config=ConcurrencyConfig(worker_pool_size=1, max_queue_size=10, max_queue_bytes=10_000),
    )
    app.dependency_overrides[get_document_service] = lambda: service
    app.dependency_overrides[get_upload_config] = lambda: UploadConfig(max_upload_bytes=4_000)
    try:
        yield service
    finally:
        app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_extract_returns_503_without_reading_body_when_declared_size_does_not_fit(
    byte_limited_pdf_service,
):
    service = byte_limited_pdf_service
    payload = multipart_body(HELLO_PDF)
    body_was_read = False

    async def body() -> AsyncIterator[bytes]:
        nonlocal body_was_read
        body_was_read = True
        yield payload

    with service.admit(10_000 - len(payload) + 1):
        async with asgi_client() as client:
            response = await client.post(
                "/extract",
                content=body(),
                headers={**MULTIPART_HEADERS, "Content-Length": str(len(payload))},
            )

    assert response.status_code == 503
    assert response.headers["retry-after"] == "1"
    assert not body_was_read


@pytest.mark.anyio
async def test_extract_reserves_the_declared_size_while_reading_the_body(
    byte_limited_pdf_service,
):
    service = byte_limited_pdf_service
    payload = multipart_body(HELLO_PDF)
    bytes_when_body_is_read: list[int] = []

    async def body() -> AsyncIterator[bytes]:
        bytes_when_body_is_read.append(service.pending_bytes)
        yield payload

    async with asgi_client() as client:
        response = await client.post(
            "/extract",
            content=body(),
            headers={**MULTIPART_HEADERS, "Content-Length": str(len(payload))},
        )

    assert response.status_code == 200
    assert bytes_when_body_is_read == [len(payload)]
    assert service.pending_bytes == 0


@pytest.mark.anyio
async def test_extract_assumes_the_upload_limit_when_the_size_is_not_declared(
    byte_limited_pdf_service,
):
    service = byte_limited_pdf_service
    bytes_when_body_is_read: list[int] = []

    async def body() -> AsyncIterator[bytes]:
        bytes_when_body_is_read.append(service.pending_bytes)
        yield multipart_body(HELLO_PDF)

    async with asgi_client() as client:
        response = await client.post("/extract", content=body(), headers=MULTIPART_HEADERS)

    assert response.status_code == 200
    assert bytes_when_body_is_read == [4_000]
