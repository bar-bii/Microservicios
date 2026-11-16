import multiprocessing
import os
from pathlib import Path

import pytest

from application.config import ConcurrencyConfig
from application.document_service import DocumentService, extraction_executor
from application.pdf_extractor import ExtractionResult, InvalidPDFError, PypdfPDFExtractor

HELLO_PDF = (Path(__file__).parent / "fixtures" / "hello.pdf").read_bytes()
THREAD_CONFIG = ConcurrencyConfig(worker_pool_size=1, max_queue_size=1)
PROCESS_CONFIG = ConcurrencyConfig(worker_pool_size=1, max_queue_size=1, executor="process")


class ProcessIdExtractor:
    def extract(self, pdf_bytes: bytes) -> ExtractionResult:
        return ExtractionResult(content=str(os.getpid()), page_count=1)


def test_concurrency_config_uses_thread_executor_by_default(monkeypatch):
    monkeypatch.delenv("EXTRACTION_EXECUTOR", raising=False)

    assert ConcurrencyConfig.from_env().executor == "thread"


def test_concurrency_config_reads_executor_from_environment(monkeypatch):
    monkeypatch.setenv("EXTRACTION_EXECUTOR", "process")

    assert ConcurrencyConfig.from_env().executor == "process"


def test_concurrency_config_rejects_unknown_executor(monkeypatch):
    monkeypatch.setenv("EXTRACTION_EXECUTOR", "fiber")

    with pytest.raises(ValueError, match="EXTRACTION_EXECUTOR"):
        ConcurrencyConfig.from_env()


@pytest.mark.anyio
async def test_thread_executor_extracts_in_the_server_process():
    with extraction_executor(THREAD_CONFIG) as executor:
        service = DocumentService(ProcessIdExtractor(), THREAD_CONFIG, executor)

        result = await service.process(HELLO_PDF)

    assert result.content == str(os.getpid())


@pytest.mark.anyio
async def test_process_executor_extracts_in_a_worker_process():
    with extraction_executor(PROCESS_CONFIG) as executor:
        service = DocumentService(ProcessIdExtractor(), PROCESS_CONFIG, executor)

        result = await service.process(HELLO_PDF)

    assert result.content != str(os.getpid())


@pytest.mark.anyio
async def test_process_executor_returns_the_extracted_text():
    with extraction_executor(PROCESS_CONFIG) as executor:
        service = DocumentService(PypdfPDFExtractor(), PROCESS_CONFIG, executor)

        result = await service.process(HELLO_PDF)

    assert result == ExtractionResult(content="Hello PDF", page_count=1)


@pytest.mark.anyio
async def test_process_executor_reports_invalid_pdfs():
    with extraction_executor(PROCESS_CONFIG) as executor:
        service = DocumentService(PypdfPDFExtractor(), PROCESS_CONFIG, executor)

        with pytest.raises(InvalidPDFError):
            await service.process(b"not a pdf")

    assert service.pending == 0


def test_process_executor_stops_its_workers_on_exit():
    with extraction_executor(PROCESS_CONFIG) as executor:
        executor.submit(os.getpid).result()

        assert multiprocessing.active_children()

    assert not multiprocessing.active_children()
