import asyncio
import os
from dataclasses import dataclass

from application.pdf_extractor import ExtractionResult, PDFExtractor

DEFAULT_WORKER_POOL_SIZE = 4
DEFAULT_MAX_QUEUE_SIZE = 100


class QueueFullError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ConcurrencyConfig:
    worker_pool_size: int = DEFAULT_WORKER_POOL_SIZE
    max_queue_size: int = DEFAULT_MAX_QUEUE_SIZE

    @property
    def capacity(self) -> int:
        return self.worker_pool_size + self.max_queue_size

    @classmethod
    def from_env(cls) -> "ConcurrencyConfig":
        return cls(
            worker_pool_size=_positive_int_from_env("WORKER_POOL_SIZE", DEFAULT_WORKER_POOL_SIZE),
            max_queue_size=_positive_int_from_env("MAX_QUEUE_SIZE", DEFAULT_MAX_QUEUE_SIZE),
        )


def _positive_int_from_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc

    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")

    return value


class DocumentService:
    def __init__(
        self,
        extractor: PDFExtractor,
        config: ConcurrencyConfig | None = None,
    ) -> None:
        self._extractor = extractor
        self._config = config or ConcurrencyConfig.from_env()
        self._workers = asyncio.Semaphore(self._config.worker_pool_size)
        self._pending = 0

    @property
    def pending(self) -> int:
        return self._pending

    @property
    def capacity(self) -> int:
        return self._config.capacity

    async def process(self, pdf_bytes: bytes) -> ExtractionResult:
        if self._pending >= self.capacity:
            raise QueueFullError("extraction queue is full")

        self._pending += 1
        try:
            async with self._workers:
                return await asyncio.to_thread(self._extractor.extract, pdf_bytes)
        finally:
            self._pending -= 1
