"""Stable error codes shared by document metadata parser boundaries."""

from dataclasses import dataclass
from enum import StrEnum
from typing import override


class ErrorCode(StrEnum):
    """Identify failures without exposing parser internals or sensitive paths."""

    UNSUPPORTED_FORMAT = "unsupported_format"
    FORMAT_MISMATCH = "format_mismatch"
    INVALID_DOCUMENT = "invalid_document"
    ENCRYPTED_DOCUMENT = "encrypted_document"
    PASSWORD_REQUIRED = "password_required"  # noqa: S105
    WRONG_PASSWORD = "wrong_password"  # noqa: S105
    UNSUPPORTED_ENCRYPTION = "unsupported_encryption"
    CORRUPT_CONTAINER = "corrupt_container"
    UNSAFE_DOCUMENT = "unsafe_document"
    RESOURCE_LIMIT_EXCEEDED = "resource_limit_exceeded"
    PARSER_TIMEOUT = "parser_timeout"
    PARSER_CRASHED = "parser_crashed"
    PARSER_UNAVAILABLE = "parser_unavailable"
    PARSER_OUTPUT_INVALID = "parser_output_invalid"
    SOURCE_CHANGED = "source_changed"
    EXPORT_FAILED = "export_failed"
    INTERNAL_ERROR = "internal_error"


@dataclass(slots=True)
class InspectionError(Exception):
    """Carry a stable code and sanitized message across parser boundaries."""

    code: ErrorCode
    message: str
    source: str | None = None
    stage: str | None = None

    @override
    def __str__(self) -> str:
        """Return only the sanitized boundary message."""
        return self.message
