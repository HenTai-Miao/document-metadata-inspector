"""Integration tests for the extract_metadata dispatcher across all 7 formats."""

from hashlib import sha256
from pathlib import Path

import pytest

from tests.opc_factories import make_opc_workbook
from xlsx_metadata_forensics.extractor import extract_metadata
from xlsx_metadata_forensics.formats import ExcelFormat
from xlsx_metadata_forensics.models import ExtractionReport, ExtractionRequest

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures"


# ── helpers ──────────────────────────────────────────────────────────────────


def _extract(path: Path, display_name: str) -> ExtractionReport:
    request = ExtractionRequest(path=path, display_name=display_name)
    return extract_metadata(request)


def _assert_sha_stable(path: Path) -> str:
    before = sha256(path.read_bytes()).hexdigest()
    _ = _extract(path, path.name)
    after = sha256(path.read_bytes()).hexdigest()
    assert before == after, "Source file was modified during extraction"
    return before


# ── OPC formats ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "expected_format",
    [
        pytest.param(ExcelFormat.XLSX, id="xlsx"),
        pytest.param(ExcelFormat.XLSM, id="xlsm"),
        pytest.param(ExcelFormat.XLSB, id="xlsb"),
        pytest.param(ExcelFormat.XLTX, id="xltx"),
        pytest.param(ExcelFormat.XLTM, id="xltm"),
    ],
)
def test_extract_opc_format_succeeds_and_preserves_identity(
    tmp_path: Path,
    expected_format: ExcelFormat,
) -> None:
    """Each OPC format yields a valid report with correct format identity."""
    path = tmp_path / f"sample.{expected_format.value}"
    _ = make_opc_workbook(path, expected_format)

    sha = _assert_sha_stable(path)
    report = _extract(path, path.name)

    assert report.success is True
    assert report.file.format == expected_format
    assert report.file.sha256 == sha
    assert report.file.size_bytes > 0
    assert report.file.package_entry_count > 0


# ── OLE formats ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("fixture_name", "expected_format"),
    [
        pytest.param("metadata.xls", ExcelFormat.XLS, id="xls"),
        pytest.param("metadata.xlt", ExcelFormat.XLT, id="xlt"),
    ],
)
def test_extract_ole_format_succeeds_and_preserves_identity(
    tmp_path: Path,
    fixture_name: str,
    expected_format: ExcelFormat,
) -> None:
    """Each OLE fixture yields a valid report with correct format identity."""
    fixture = FIXTURE_DIR / fixture_name
    path = tmp_path / fixture_name
    _ = path.write_bytes(fixture.read_bytes())

    sha = _assert_sha_stable(path)
    report = _extract(path, path.name)

    assert report.success is True
    assert report.file.format == expected_format
    assert report.file.sha256 == sha
    assert report.file.size_bytes > 0


# ── source integrity ─────────────────────────────────────────────────────────


def test_extract_all_seven_formats_preserves_source_integrity(
    tmp_path: Path,
) -> None:
    """Every supported format leaves its source file unchanged."""
    cases: list[tuple[Path, ExcelFormat]] = []

    for fmt in (ExcelFormat.XLSX, ExcelFormat.XLSM, ExcelFormat.XLTX):
        p = tmp_path / f"opc_{fmt.value}.{fmt.value}"
        _ = make_opc_workbook(p, fmt)
        cases.append((p, fmt))

    # XLSB needs separate handling - uses workbook.bin
    p = tmp_path / "opc_xlsb.xlsb"
    _ = make_opc_workbook(p, ExcelFormat.XLSB)
    cases.append((p, ExcelFormat.XLSB))

    for name in ("metadata.xls", "metadata.xlt"):
        p = tmp_path / name
        _ = p.write_bytes((FIXTURE_DIR / name).read_bytes())
        cases.append((p, ExcelFormat(name.split(".")[-1])))

    for path, _fmt in cases:
        before = sha256(path.read_bytes()).hexdigest()
        _ = _extract(path, path.name)
        after = sha256(path.read_bytes()).hexdigest()
        assert before == after, f"Modified: {path.name}"
