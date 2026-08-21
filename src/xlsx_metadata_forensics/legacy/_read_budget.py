"""Shared cumulative and per-stream budgets for legacy OLE reads."""

from __future__ import annotations

from typing import TYPE_CHECKING, final

from xlsx_metadata_forensics.errors import ErrorCode, ExtractionError

if TYPE_CHECKING:
    from xlsx_metadata_forensics.models import ExtractionLimits


@final
class LegacyReadBudget:
    """Charge every logical legacy stream read against immutable limits."""

    def __init__(self, limits: ExtractionLimits) -> None:
        self._limits = limits
        self._remaining = limits.max_total_read_bytes

    def claim(
        self,
        length: int,
        source: str,
        *,
        enforce_stream_limit: bool = False,
    ) -> None:
        """Reserve bytes before a dependency is allowed to materialize them."""
        if length < 0:
            raise ExtractionError(
                ErrorCode.CORRUPT_PACKAGE,
                "An OLE stream reports an invalid size.",
                source,
            )
        if enforce_stream_limit and length > self._limits.max_xml_part_bytes:
            raise ExtractionError(
                ErrorCode.FILE_TOO_LARGE,
                "An OLE property stream exceeds the configured size limit.",
                source,
            )
        if length > self._remaining:
            raise ExtractionError(
                ErrorCode.FILE_TOO_LARGE,
                "The package read budget has been exhausted.",
                source,
            )
        self._remaining -= length
