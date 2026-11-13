import os
from dataclasses import dataclass

DEFAULT_MAX_UPLOAD_BYTES = 15 * 1024 * 1024


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
