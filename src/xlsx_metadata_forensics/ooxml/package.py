"""Bounded, resource-owned access to genuine Excel OPC packages."""

from collections.abc import Generator
from contextlib import AbstractContextManager, contextmanager
from os import fstat
from pathlib import Path
from typing import BinaryIO, Final
from zipfile import BadZipFile, ZipFile

from xlsx_metadata_forensics.errors import ErrorCode, ExtractionError
from xlsx_metadata_forensics.formats import ExcelFormat
from xlsx_metadata_forensics.models import ExtractionLimits
from xlsx_metadata_forensics.ooxml._package_reader import PackageReader, PackageView
from xlsx_metadata_forensics.ooxml._package_validation import validate_excel_package
from xlsx_metadata_forensics.ooxml._zip_inventory import build_inventory

_CFB_HEADER: Final = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

__all__ = ("PackageView", "open_package")


def _failure(
    code: ErrorCode,
    message: str,
    source: str | None = None,
) -> ExtractionError:
    return ExtractionError(code, message, source)


@contextmanager
def _package_stream_context(
    source: BinaryIO,
    source_name: str,
    file_size: int,
    limits: ExtractionLimits,
    expected_format: ExcelFormat,
) -> Generator[PackageView]:
    if file_size > limits.max_file_bytes:
        raise _failure(
            ErrorCode.FILE_TOO_LARGE,
            "The input file exceeds the configured size limit.",
            source_name,
        )
    try:
        _ = source.seek(0)
        header = source.read(len(_CFB_HEADER))
        _ = source.seek(0)
    except OSError as error:
        raise _failure(
            ErrorCode.EXTRACTION_FAILED,
            "The input file could not be inspected.",
            source_name,
        ) from error
    if header == _CFB_HEADER:
        raise _failure(
            ErrorCode.ENCRYPTED_EXCEL,
            "The file uses an OLE/CFB container, not a ZIP-based OPC package.",
            source_name,
        )
    try:
        archive = ZipFile(source, "r")
    except (BadZipFile, UnicodeDecodeError, NotImplementedError) as error:
        raise _failure(
            ErrorCode.CORRUPT_PACKAGE,
            "The input is not a readable ZIP package.",
            source_name,
        ) from error
    except OSError as error:
        raise _failure(
            ErrorCode.EXTRACTION_FAILED,
            "The ZIP package could not be opened.",
            source_name,
        ) from error
    with archive:
        parts, names = build_inventory(archive, limits)
        reader = PackageReader(archive, parts, limits)
        try:
            identity = validate_excel_package(reader, expected_format)
            package = PackageView(reader, len(names), names, identity.format)
            try:
                yield package
            except ExtractionError as error:
                raise _failure(error.code, error.message, error.source) from error
        finally:
            reader.close()


@contextmanager
def _path_package_context(
    path: Path,
    limits: ExtractionLimits,
    expected_format: ExcelFormat,
) -> Generator[PackageView]:
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
        with _package_stream_context(
            source,
            path.name,
            file_size,
            limits,
            expected_format,
        ) as package:
            yield package


def open_package_stream(
    source: BinaryIO,
    source_name: str,
    file_size: int,
    limits: ExtractionLimits,
    *,
    expected_format: ExcelFormat = ExcelFormat.XLSX,
) -> AbstractContextManager[PackageView]:
    """Inspect OPC data through a caller-owned, already-open read-only stream."""
    return _package_stream_context(
        source,
        source_name,
        file_size,
        limits,
        expected_format,
    )


def open_package(
    path: Path,
    limits: ExtractionLimits,
    *,
    expected_format: ExcelFormat = ExcelFormat.XLSX,
) -> AbstractContextManager[PackageView]:
    """Open one exact Excel OPC format with bounded reads and deterministic closure."""
    return _path_package_context(path, limits, expected_format)
