import asyncio

import pytest

from application.config import FIFO_ORDER, HRRN_ORDER, ConcurrencyConfig
from application.document_service import DocumentService
from application.pdf_extractor import ExtractionResult

BLOCKER = b"%PDF-blocker"
LARGE = b"%PDF-" + b"x" * 1_000_000
SMALL = b"%PDF-small"


class RecordingExtractor:
    def __init__(self) -> None:
        self.extracted: list[bytes] = []

    def extract(self, pdf_bytes: bytes) -> ExtractionResult:
        self.extracted.append(pdf_bytes)
        return ExtractionResult(content="", page_count=0)


async def wait_until_pending(service: DocumentService, expected: int) -> None:
    async with asyncio.timeout(2):
        while service.pending < expected:
            await asyncio.sleep(0)


async def extraction_order(monkeypatch, order: str | None) -> list[bytes]:
    """Encola un PDF grande y después uno chico detrás de una extracción en curso."""
    release_blocker = asyncio.Event()

    async def fake_to_thread(func, pdf_bytes):
        if pdf_bytes == BLOCKER:
            await release_blocker.wait()
        return func(pdf_bytes)

    monkeypatch.setattr("application.document_service.asyncio.to_thread", fake_to_thread)
    config = (
        ConcurrencyConfig(worker_pool_size=1)
        if order is None
        else ConcurrencyConfig(worker_pool_size=1, queue_order=order)
    )
    extractor = RecordingExtractor()
    service = DocumentService(extractor, config=config)

    tasks = []
    for expected_pending, payload in enumerate((BLOCKER, LARGE, SMALL), start=1):
        tasks.append(asyncio.create_task(service.process(payload)))
        await wait_until_pending(service, expected_pending)
    await asyncio.sleep(0.02)

    release_blocker.set()
    await asyncio.gather(*tasks)
    return extractor.extracted


@pytest.mark.anyio
@pytest.mark.parametrize("order", [None, FIFO_ORDER])
async def test_service_extracts_in_arrival_order_by_default(monkeypatch, order):
    assert await extraction_order(monkeypatch, order) == [BLOCKER, LARGE, SMALL]


@pytest.mark.anyio
async def test_service_extracts_the_small_pdf_first_with_hrrn(monkeypatch):
    assert await extraction_order(monkeypatch, HRRN_ORDER) == [BLOCKER, SMALL, LARGE]


def test_concurrency_config_uses_fifo_order_by_default(monkeypatch):
    monkeypatch.delenv("QUEUE_ORDER", raising=False)

    assert ConcurrencyConfig.from_env().queue_order == FIFO_ORDER


def test_concurrency_config_reads_the_queue_order(monkeypatch):
    monkeypatch.setenv("QUEUE_ORDER", "hrrn")

    assert ConcurrencyConfig.from_env().queue_order == HRRN_ORDER


def test_concurrency_config_rejects_an_unknown_queue_order(monkeypatch):
    monkeypatch.setenv("QUEUE_ORDER", "lifo")

    with pytest.raises(ValueError, match="QUEUE_ORDER"):
        ConcurrencyConfig.from_env()
