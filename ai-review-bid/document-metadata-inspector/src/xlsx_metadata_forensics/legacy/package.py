"""Read-only access to OLE/CFBF Excel workbooks (.xls, .xlt)."""

from __future__ import annotations

from contextlib import contextmanager
from os import fstat
from typing import TYPE_CHECKING, final

from olefile import DEFECT_INCORRECT, OleFileIO
from olefile.olefile import OleFileError

from xlsx_metadata_forensics.errors import ErrorCode, ExtractionError
from xlsx_metadata_forensics.legacy._biff_validation import (
    select_workbook_stream,
    validate_biff_globals,
)
from xlsx_metadata_forensics.legacy._read_budget import LegacyReadBudget

if TYPE_CHECKING:
    from collections.abc import Generator
    from contextlib import AbstractContextManager
    from pathlib import Path
    from typing import BinaryIO

    from xlsx_metadata_forensics.formats import ExcelFormat
    from xlsx_metadata_forensics.models import ExtractionLimits

_ENCRYPTION_STREAMS = frozenset({"EncryptedPackage", "EncryptionInfo"})


def _failure(
    code: ErrorCode, message: str, source: str | None = None
) -> ExtractionError:
    return ExtractionError(code, message, source)


def _inventory(
    ole: OleFileIO[str],
    limits: ExtractionLimits,
    source: str,
) -> tuple[tuple[str, ...], ...]:
    entries = tuple(tuple(path) for path in ole.listdir(streams=True, storages=True))
    if len(entries) > limits.max_entries:
        raise _failure(
            ErrorCode.UNSAFE_PACKAGE,
            "The OLE container contains too many directory entries.",
            source,
        )
    return entries


def _check_encryption(
    entries: tuple[tuple[str, ...], ...],
    source: str,
) -> None:
    """Reject explicit root-level OLE encryption streams."""
    root_names = frozenset(entry[0] for entry in entries if len(entry) == 1)
    if root_names.intersection(_ENCRYPTION_STREAMS):
        raise _failure(
            ErrorCode.ENCRYPTED_EXCEL,
            "Encrypted OLE containers are not supported.",
            source,
        )


@contextmanager
def _legacy_stream_context(
    source: BinaryIO,
    source_name: str,
    file_size: int,
    limits: ExtractionLimits,
    expected_format: ExcelFormat,
) -> Generator[LegacyWorkbookView]:
    if file_size > limits.max_file_bytes:
        raise _failure(
            ErrorCode.FILE_TOO_LARGE,
            "The input file exceeds the configured size limit.",
            source_name,
        )

    ole: OleFileIO[str] | None = None
    try:
        ole = OleFileIO(source, raise_defects=DEFECT_INCORRECT)
        entries = _inventory(ole, limits, source_name)
        _check_encryption(entries, source_name)
        workbook_stream = select_workbook_stream(entries, source_name)
        budget = LegacyReadBudget(limits)
        validate_biff_globals(ole, workbook_stream, budget)
        yield LegacyWorkbookView(
            ole=ole,
            fmt=expected_format,
            entry_count=len(entries),
            workbook_stream=workbook_stream,
        )
    except ExtractionError:
        raise
    except OleFileError as error:
        raise _failure(
            ErrorCode.CORRUPT_PACKAGE,
            "The OLE container is structurally invalid.",
            source_name,
        ) from error
    except OSError as error:
        raise _failure(
            ErrorCode.EXTRACTION_FAILED,
            "The OLE container could not be read.",
            source_name,
        ) from error
    finally:
        if ole is not None:
            ole.close()


@contextmanager
def _legacy_path_context(
    path: Path,
    limits: ExtractionLimits,
    expected_format: ExcelFormat,
) -> Generator[LegacyWorkbookView]:
    try:
        source = path.open("rb")
    except OSError as error:
        raise _failure(
            ErrorCode.EXTRACTION_FAILED,
            "The input file could not be opened.",
            path.name,
        ) from error
    with source:
        try:
            file_size = fstat(source.fileno()).st_size
        except OSError as error:
            raise _failure(
                ErrorCode.EXTRACTION_FAILED,
                "The input file could not be inspected.",
                path.name,
            ) from error
        with _legacy_stream_context(
            source,
            path.name,
            file_size,
            limits,
            expected_format,
        ) as view:
            yield view


def open_legacy_workbook_stream(
    source: BinaryIO,
    source_name: str,
    file_size: int,
    limits: ExtractionLimits,
    *,
    expected_format: ExcelFormat,
) -> AbstractContextManager[LegacyWorkbookView]:
    """Inspect OLE data through a caller-owned, already-open read-only stream."""
    return _legacy_stream_context(
        source,
        source_name,
        file_size,
        limits,
        expected_format,
    )


def open_legacy_workbook(
    path: Path,
    limits: ExtractionLimits,
    *,
    expected_format: ExcelFormat,
) -> AbstractContextManager[LegacyWorkbookView]:
    """Open one legacy Excel workbook under a bounded read-only context."""
    return _legacy_path_context(path, limits, expected_format)


@final
class LegacyWorkbookView:
    """Read-only, resource-owned snapshot of one legacy Excel workbook."""

    def __init__(
        self,
        ole: OleFileIO[str],
        fmt: ExcelFormat,
        entry_count: int,
        workbook_stream: str,
    ) -> None:
        """Retain the validated OLE handle and immutable workbook facts."""
        self._ole = ole
        self.format = fmt
        self.entry_count = entry_count
        self.workbook_stream = workbook_stream

    @property
    def ole(self) -> OleFileIO[str]:
        """Return the underlying olefile handle for metadata extraction."""
        return self._ole
