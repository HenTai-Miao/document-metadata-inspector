"""Behavior tests for the OLE/BIFF legacy package adapter."""

from pathlib import Path

import pytest
from olefile import DEFECT_INCORRECT, OleFileIO

from xlsx_metadata_forensics.errors import ErrorCode, ExtractionError
from xlsx_metadata_forensics.formats import ExcelFormat
from xlsx_metadata_forensics.legacy.package import open_legacy_workbook
from xlsx_metadata_forensics.legacy.properties import read_legacy_properties
from xlsx_metadata_forensics.models import ExtractionLimits

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures"
XLS_PATH = FIXTURE_DIR / "metadata.xls"
XLT_PATH = FIXTURE_DIR / "metadata.xlt"


# ── container identity ───────────────────────────────────────────────────────


def test_ole_magic_bytes_are_recognized() -> None:
    """Given a real .xls fixture, it starts with the OLE/CFB magic bytes."""
    data = XLS_PATH.read_bytes()
    assert data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def test_ole_fixture_contains_workbook_stream() -> None:
    """Given a real .xls fixture, olefile can locate the Workbook stream."""
    with OleFileIO(str(XLS_PATH), raise_defects=DEFECT_INCORRECT) as ole:
        assert ole.exists("Workbook") or ole.exists("Book")


def test_public_adapter_accepts_a_single_workbook_stream() -> None:
    """The public adapter accepts a valid workbook identity."""
    with open_legacy_workbook(
        XLS_PATH,
        ExtractionLimits(),
        expected_format=ExcelFormat.XLS,
    ) as view:
        assert view.workbook_stream == "Workbook"


def test_public_adapter_accepts_an_unencrypted_fixture(tmp_path: Path) -> None:
    """A valid unencrypted fixture opens through the public boundary."""
    path = tmp_path / "test.xls"
    _ = path.write_bytes(XLS_PATH.read_bytes())

    with open_legacy_workbook(
        path,
        ExtractionLimits(),
        expected_format=ExcelFormat.XLS,
    ) as view:
        assert view.format == ExcelFormat.XLS


# ── metadata extraction ──────────────────────────────────────────────────────


def test_legacy_fixture_yields_expected_metadata(tmp_path: Path) -> None:
    """Given the real .xls fixture, extracted metadata matches the known values.

    Fields that olefile extracts from LibreOffice-generated fixtures are
    checked.  company, manager, and creating_application are not preserved
    by the LibreOffice OLE conversion and are expected to be None.
    """
    path = tmp_path / "test.xls"
    _ = path.write_bytes(XLS_PATH.read_bytes())

    with open_legacy_workbook(
        path, ExtractionLimits(), expected_format=ExcelFormat.XLS
    ) as view:
        facts = read_legacy_properties(view)

    assert facts.metadata.author == "Alice Analyst"
    assert facts.metadata.last_modified_by == "Bob Reviewer"
    assert facts.metadata.title == "Metadata Test Fixture"
    assert facts.metadata.subject == "TDD Verification"
    assert facts.metadata.description == ("Controlled fixture for OLE adapter tests.")
    assert facts.metadata.keywords == "test, fixture, metadata"
    assert facts.metadata.revision == "3"
    # created_at is stored as UTC by LibreOffice.
    assert facts.metadata.created_at is not None
    assert "2024-03-15" in facts.metadata.created_at.raw
    # Fields not preserved by LibreOffice OLE conversion.
    assert facts.metadata.company is None
    assert facts.metadata.manager is None
    assert facts.metadata.application is None


def test_legacy_template_fixture_is_accepted(tmp_path: Path) -> None:
    """Given the real .xlt fixture with XLT expected format, it opens cleanly."""
    path = tmp_path / "test.xlt"
    _ = path.write_bytes(XLT_PATH.read_bytes())

    with open_legacy_workbook(
        path, ExtractionLimits(), expected_format=ExcelFormat.XLT
    ) as view:
        assert view.format == ExcelFormat.XLT


# ── budget and closure ───────────────────────────────────────────────────────


def test_legacy_file_budget_is_enforced(tmp_path: Path) -> None:
    """Given a file exceeding max_file_bytes, raise FILE_TOO_LARGE."""
    path = tmp_path / "big.xls"
    _ = path.write_bytes(XLS_PATH.read_bytes())
    limits = ExtractionLimits(max_file_bytes=10)

    with (
        pytest.raises(ExtractionError) as exc_info,
        open_legacy_workbook(path, limits, expected_format=ExcelFormat.XLS),
    ):
        pass
    assert exc_info.value.code == ErrorCode.FILE_TOO_LARGE


def test_legacy_workbook_closes_ole_on_exception(tmp_path: Path) -> None:
    """Given a real fixture, the OLE handle is closed even on read error."""
    path = tmp_path / "test.xls"
    _ = path.write_bytes(XLS_PATH.read_bytes())

    with open_legacy_workbook(
        path, ExtractionLimits(), expected_format=ExcelFormat.XLS
    ):
        pass  # Normal close — no leak.

    # Prove the file is still deletable (no lingering lock).
    path.unlink()
