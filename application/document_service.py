import asyncio
import multiprocessing
from collections.abc import Iterator
from concurrent.futures import Executor, ProcessPoolExecutor
from contextlib import contextmanager

from application.config import PROCESS_EXECUTOR, ConcurrencyConfig
from application.pdf_extractor import ExtractionResult, PDFExtractor


class QueueFullError(Exception):
    pass


@contextmanager
def extraction_executor(config: ConcurrencyConfig) -> Iterator[Executor | None]:
    if config.executor != PROCESS_EXECUTOR:
        yield None
        return

    with ProcessPoolExecutor(
        max_workers=config.worker_pool_size,
        mp_context=multiprocessing.get_context("spawn"),
    ) as pool:
        yield pool


class DocumentService:
    def __init__(
        self,
        extractor: PDFExtractor,
        config: ConcurrencyConfig | None = None,
        executor: Executor | None = None,
    ) -> None:
        self._extractor = extractor
        self._config = config or ConcurrencyConfig.from_env()
        self._executor = executor
        self._workers = asyncio.Semaphore(self._config.worker_pool_size)
        self._pending = 0

    @property
    def pending(self) -> int:
        return self._pending

    @property
    def capacity(self) -> int:
        return self._config.capacity

    @contextmanager
    def admit(self) -> Iterator[None]:
        if self._pending >= self.capacity:
            raise QueueFullError("extraction queue is full")

        self._pending += 1
        try:
            yield
        finally:
            self._pending -= 1

    async def process_admitted(self, pdf_bytes: bytes) -> ExtractionResult:
        async with self._workers:
            if self._executor is None:
                return await asyncio.to_thread(self._extractor.extract, pdf_bytes)

            return await asyncio.get_running_loop().run_in_executor(
                self._executor,
                self._extractor.extract,
                pdf_bytes,
            )

    async def process(self, pdf_bytes: bytes) -> ExtractionResult:
        with self.admit():
            return await self.process_admitted(pdf_bytes)
