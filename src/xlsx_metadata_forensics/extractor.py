"""Unified metadata extraction entry-point for the Excel file family."""

from typing import assert_never

from xlsx_metadata_forensics._source import SourceSnapshot, open_source_snapshot
from xlsx_metadata_forensics.errors import ErrorCode, ExtractionError
from xlsx_metadata_forensics.formats import (
    ContainerKind,
    ExcelFormat,
    UnsupportedExcelFormatError,
    identify_declared_format,
)
from xlsx_metadata_forensics.legacy.package import open_legacy_workbook_stream
from xlsx_metadata_forensics.legacy.properties import read_legacy_properties
from xlsx_metadata_forensics.models import (
    ExtractionReport,
    ExtractionRequest,
    FileInfo,
    ForensicInfo,
)
from xlsx_metadata_forensics.ooxml.package import open_package_stream
from xlsx_metadata_forensics.ooxml.properties import read_properties


def _failure(
    code: ErrorCode, message: str, source: str | None = None
) -> ExtractionError:
    return ExtractionError(code, message, source)


def _extract_opc(
    request: ExtractionRequest,
    expected_format: ExcelFormat,
    source: SourceSnapshot,
) -> ExtractionReport:
    with open_package_stream(
        source.stream,
        source.name,
        source.size_bytes,
        request.limits,
        expected_format=expected_format,
    ) as package:
        facts = read_properties(package)
        return ExtractionReport(
            file=FileInfo(
                name=request.display_name,
                size_bytes=source.size_bytes,
                sha256=source.sha256,
                format=package.format,
                package_entry_count=package.entry_count,
            ),
            metadata=facts.metadata,
            forensics=ForensicInfo(custom_properties=facts.custom_properties),
            warnings=facts.warnings,
        )


def _extract_ole(
    request: ExtractionRequest,
    expected_format: ExcelFormat,
    source: SourceSnapshot,
) -> ExtractionReport:
    with open_legacy_workbook_stream(
        source.stream,
        source.name,
        source.size_bytes,
        request.limits,
        expected_format=expected_format,
    ) as view:
        facts = read_legacy_properties(view)
        return ExtractionReport(
            file=FileInfo(
                name=request.display_name,
                size_bytes=source.size_bytes,
                sha256=source.sha256,
                format=view.format,
                package_entry_count=view.entry_count,
            ),
            metadata=facts.metadata,
            forensics=ForensicInfo(custom_properties=facts.custom_properties),
            warnings=facts.warnings,
        )


def extract_metadata(request: ExtractionRequest) -> ExtractionReport:
    """Extract read-only metadata from one supported Excel-family file.

    Raises:
        ExtractionError: on unsupported format, missing files, or extraction failure.
    """
    try:
        identity = identify_declared_format(request.path)
    except UnsupportedExcelFormatError as error:
        raise _failure(
            ErrorCode.UNSUPPORTED_FORMAT,
            "The filename does not declare a supported Excel format.",
            request.path.name,
        ) from error

    try:
        with open_source_snapshot(request) as source:
            match identity.container:
                case ContainerKind.OPC:
                    return _extract_opc(request, identity.format, source)
                case ContainerKind.OLE:
                    return _extract_ole(request, identity.format, source)
                case _:  # pragma: no cover
                    assert_never(identity.container)
    except ExtractionError:
        raise
    except OSError:
        raise _failure(
            ErrorCode.EXTRACTION_FAILED,
            "The input file could not be read.",
            request.path.name,
        ) from None
