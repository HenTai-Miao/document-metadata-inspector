"""Typed extraction errors and error response contracts."""

from dataclasses import FrozenInstanceError, dataclass
from enum import StrEnum
from typing import Final, Literal, override

from xlsx_metadata_forensics.models import FrozenModel


class ErrorCode(StrEnum):
    """Stable machine-consumed extraction failure codes."""

    UNSUPPORTED_FORMAT = "unsupported_format"
    INVALID_EXCEL = "invalid_excel"
    INVALID_XLSX = "invalid_excel"
    ENCRYPTED_EXCEL = "encrypted_excel"
    ENCRYPTED_XLSX = "encrypted_excel"
    CORRUPT_PACKAGE = "corrupt_package"
    FILE_TOO_LARGE = "file_too_large"
    UNSAFE_PACKAGE = "unsafe_package"
    EXTRACTION_FAILED = "extraction_failed"


_EXTRACTION_ERROR_FIELDS: Final = frozenset(("code", "message", "source"))


@dataclass(slots=True)
class ExtractionError(Exception):
    """Carry a stable error code and sanitized boundary message."""

    code: ErrorCode
    message: str
    source: str | None = None

    @override
    def __setattr__(self, name: str, value: object) -> None:
        """Keep evidence fields stable while permitting exception runtime state."""
        if name in _EXTRACTION_ERROR_FIELDS and hasattr(self, name):
            detail = f"cannot assign to field {name!r}"
            raise FrozenInstanceError(detail)
        BaseException.__setattr__(self, name, value)

    @override
    def __delattr__(self, name: str) -> None:
        """Reject evidence-field deletion without freezing runtime state."""
        if name in _EXTRACTION_ERROR_FIELDS:
            detail = f"cannot delete field {name!r}"
            raise FrozenInstanceError(detail)
        BaseException.__delattr__(self, name)

    @override
    def __str__(self) -> str:
        """Return the sanitized message for logs and command errors."""
        return self.message


class ErrorResponse(FrozenModel):
    """Return the stable failed-extraction JSON contract."""

    success: Literal[False] = False
    error: ExtractionError
