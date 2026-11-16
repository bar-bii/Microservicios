import os
from dataclasses import dataclass

DEFAULT_WORKER_POOL_SIZE = 4
DEFAULT_MAX_QUEUE_SIZE = 100
DEFAULT_MAX_UPLOAD_BYTES = 15 * 1024 * 1024
THREAD_EXECUTOR = "thread"
PROCESS_EXECUTOR = "process"
EXECUTORS = (THREAD_EXECUTOR, PROCESS_EXECUTOR)
FIFO_ORDER = "fifo"
HRRN_ORDER = "hrrn"
QUEUE_ORDERS = (FIFO_ORDER, HRRN_ORDER)


def positive_int_from_env(name: str, default: int) -> int:
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


def optional_positive_int_from_env(name: str) -> int | None:
    if not os.getenv(name):
        return None

    return positive_int_from_env(name, 0)


def choice_from_env(name: str, default: str, choices: tuple[str, ...]) -> str:
    value = os.getenv(name, default)
    if value not in choices:
        raise ValueError(f"{name} must be one of: {', '.join(choices)}")

    return value


@dataclass(frozen=True, slots=True)
class ConcurrencyConfig:
    worker_pool_size: int = DEFAULT_WORKER_POOL_SIZE
    max_queue_size: int = DEFAULT_MAX_QUEUE_SIZE
    executor: str = THREAD_EXECUTOR
    max_queue_bytes: int | None = None
    queue_order: str = FIFO_ORDER

    @property
    def capacity(self) -> int:
        return self.worker_pool_size + self.max_queue_size

    @classmethod
    def from_env(cls) -> "ConcurrencyConfig":
        return cls(
            worker_pool_size=positive_int_from_env(
                "WORKER_POOL_SIZE",
                DEFAULT_WORKER_POOL_SIZE,
            ),
            max_queue_size=positive_int_from_env(
                "MAX_QUEUE_SIZE",
                DEFAULT_MAX_QUEUE_SIZE,
            ),
            executor=choice_from_env("EXTRACTION_EXECUTOR", THREAD_EXECUTOR, EXECUTORS),
            max_queue_bytes=optional_positive_int_from_env("MAX_QUEUE_BYTES"),
            queue_order=choice_from_env("QUEUE_ORDER", FIFO_ORDER, QUEUE_ORDERS),
        )


@dataclass(frozen=True, slots=True)
class UploadConfig:
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES

    @classmethod
    def from_env(cls) -> "UploadConfig":
        return cls(
            max_upload_bytes=positive_int_from_env(
                "MAX_UPLOAD_BYTES",
                DEFAULT_MAX_UPLOAD_BYTES,
            )
        )
