"""Behavior tests for the unified extract_metadata dispatcher."""

from hashlib import sha256
from pathlib import Path
from typing import BinaryIO, Literal

import pytest

from tests.opc_factories import make_opc_workbook
from tests.property_support import (
    APP,
    CORE,
    CORE_XML,
    CUSTOM,
    make_property_workbook,
)
from xlsx_metadata_forensics.errors import ErrorCode, ExtractionError
from xlsx_metadata_forensics.extractor import extract_metadata
from xlsx_metadata_forensics.formats import ExcelFormat
from xlsx_metadata_forensics.models import (
    ExtractionLimits,
    ExtractionReport,
    ExtractionRequest,
)
from xlsx_metadata_forensics.ooxml.package import PackageView
from xlsx_metadata_forensics.ooxml.properties import PropertyFacts
from xlsx_metadata_forensics.ooxml.properties import (
    read_properties as read_opc_properties,
)


def _make_sample_xlsx(directory: Path) -> Path:
    return make_property_workbook(
        directory,
        {CORE: None, APP: None, CUSTOM: None},
    )


# ── success paths ────────────────────────────────────────────────────────────


def test_extract_xlsx_produces_valid_report(tmp_path: Path) -> None:
    """Given a genuine XLSX, the report carries file info, metadata, and SHA-256."""
    workbook = _make_sample_xlsx(tmp_path)
    before = sha256(workbook.read_bytes()).hexdigest()
    request = ExtractionRequest(path=workbook, display_name="test.xlsx")

    report = extract_metadata(request)

    assert isinstance(report, ExtractionReport)
    assert report.success is True
    assert report.file.name == "test.xlsx"
    assert report.file.size_bytes == workbook.stat().st_size
    assert report.file.sha256 == before
    assert report.file.format == ExcelFormat.XLSX
    assert report.file.package_entry_count > 0
    # The source file must not have been modified.
    assert sha256(workbook.read_bytes()).hexdigest() == before


@pytest.mark.parametrize(
    "expected_format",
    [
        pytest.param(ExcelFormat.XLSM, id="xlsm"),
        pytest.param(ExcelFormat.XLSB, id="xlsb"),
        pytest.param(ExcelFormat.XLTX, id="xltx"),
        pytest.param(ExcelFormat.XLTM, id="xltm"),
    ],
)
def test_extract_opc_format_preserves_correct_identity(
    tmp_path: Path,
    expected_format: ExcelFormat,
) -> None:
    """Given a genuine OPC package with a non-XLSX format, the report records it."""
    path = tmp_path / f"sample.{expected_format.value}"
    _ = make_opc_workbook(path, expected_format)
    request = ExtractionRequest(path=path, display_name=path.name)

    report = extract_metadata(request)

    assert report.success is True
    assert report.file.format == expected_format


# ── OLE adapter ──────────────────────────────────────────────────────────────


def test_extract_xls_produces_valid_report(
    tmp_path: Path,
) -> None:
    """Given a real .xls fixture via the dispatcher, a valid report is returned."""
    fixture_dir = Path(__file__).resolve().parent.parent / "fixtures"
    fixture = fixture_dir / "metadata.xls"
    path = tmp_path / "test.xls"
    _ = path.write_bytes(fixture.read_bytes())
    request = ExtractionRequest(path=path, display_name=path.name)

    report = extract_metadata(request)

    assert isinstance(report, ExtractionReport)
    assert report.success is True
    assert report.file.format == ExcelFormat.XLS
    assert report.metadata.author == "Alice Analyst"
    assert report.file.sha256 is not None


# ── error paths ──────────────────────────────────────────────────────────────


def test_extract_unsupported_suffix_raises_typed_error(tmp_path: Path) -> None:
    """Given an unsupported suffix, expose the stable public error contract."""
    path = tmp_path / "sample.csv"
    _ = path.write_text("a,b,c", encoding="utf-8")
    request = ExtractionRequest(path=path, display_name=path.name)

    with pytest.raises(ExtractionError) as exc_info:
        _ = extract_metadata(request)

    assert exc_info.value.code == ErrorCode.UNSUPPORTED_FORMAT


def test_extract_no_extension_raises_typed_error(tmp_path: Path) -> None:
    """Given no extension, expose the same stable public error contract."""
    path = tmp_path / "no_extension"
    _ = path.write_text("hello", encoding="utf-8")
    request = ExtractionRequest(path=path, display_name=path.name)

    with pytest.raises(ExtractionError) as exc_info:
        _ = extract_metadata(request)

    assert exc_info.value.code == ErrorCode.UNSUPPORTED_FORMAT


def test_extract_missing_file_raises_typed_error(
    tmp_path: Path,
) -> None:
    """Raise ExtractionError with EXTRACTION_FAILED for missing files."""

    path = tmp_path / "does_not_exist.xlsx"
    request = ExtractionRequest(path=path, display_name=path.name)

    with pytest.raises(ExtractionError) as exc_info:
        _ = extract_metadata(request)

    assert exc_info.value.code == ErrorCode.EXTRACTION_FAILED


def test_file_size_limit_precedes_any_whole_file_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A rejected file is never loaded wholesale before its size is checked."""
    path = tmp_path / "oversized.xlsx"
    _ = path.write_bytes(b"too large")
    original_read_bytes = Path.read_bytes
    guard_message = "whole-file read ran before the size guard"

    def guarded_read_bytes(candidate: Path) -> bytes:
        if candidate == path:
            raise RuntimeError(guard_message)
        return original_read_bytes(candidate)

    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)
    request = ExtractionRequest(
        path=path,
        display_name=path.name,
        limits=ExtractionLimits(max_file_bytes=1),
    )

    with pytest.raises(ExtractionError) as exc_info:
        _ = extract_metadata(request)

    assert exc_info.value.code == ErrorCode.FILE_TOO_LARGE


def test_extraction_uses_the_single_opened_file_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Path replacement cannot combine one file's hash with another's metadata."""
    first = make_property_workbook(
        tmp_path / "first",
        {CORE: CORE_XML.replace("Alice", "Snapshot A"), APP: None, CUSTOM: None},
    )
    second = make_property_workbook(
        tmp_path / "second",
        {CORE: CORE_XML.replace("Alice", "Snapshot B"), APP: None, CUSTOM: None},
    )
    path = tmp_path / "target.xlsx"
    replacement = tmp_path / "replacement.xlsx"
    _ = path.write_bytes(first.read_bytes())
    _ = replacement.write_bytes(second.read_bytes())
    first_sha = sha256(path.read_bytes()).hexdigest()

    original_open = Path.open
    replaced = False

    def replace_after_open(
        candidate: Path,
        mode: Literal["rb"] = "rb",
    ) -> BinaryIO:
        nonlocal replaced
        handle = original_open(candidate, mode)
        if candidate == path and not replaced:
            replaced = True
            _ = replacement.replace(path)
        return handle

    monkeypatch.setattr(Path, "open", replace_after_open)

    report = extract_metadata(ExtractionRequest(path=path, display_name=path.name))

    assert replaced is True
    assert report.file.sha256 == first_sha
    assert report.metadata.author == "Snapshot A"


def test_extraction_rejects_in_place_change_before_returning_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful parse cannot return evidence after its open inode changed."""
    path = _make_sample_xlsx(tmp_path)

    def mutate_after_read(package: PackageView) -> PropertyFacts:
        facts = read_opc_properties(package)
        with path.open("r+b") as mutable:
            first_byte = mutable.read(1)
            _ = mutable.seek(0)
            _ = mutable.write(bytes((first_byte[0] ^ 0xFF,)))
        return facts

    monkeypatch.setattr(
        "xlsx_metadata_forensics.extractor.read_properties",
        mutate_after_read,
    )

    with pytest.raises(ExtractionError) as exc_info:
        _ = extract_metadata(ExtractionRequest(path=path, display_name=path.name))

    assert exc_info.value.code == ErrorCode.EXTRACTION_FAILED
    assert exc_info.value.message == "The input file changed during extraction."
