"""Exceptional context-exit closure regressions for retained package views."""

from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from zipfile import ZipFile

import pytest

from tests.factories import make_workbook, rewrite_package
from xlsx_metadata_forensics.errors import ErrorCode, ExtractionError
from xlsx_metadata_forensics.models import ExtractionLimits
from xlsx_metadata_forensics.ooxml.package import PackageView, open_package

WORKBOOK_PART = "xl/workbook.xml"
BROKEN_PART = "custom/broken.xml"
CONTENT_TYPES_PART = "[Content_Types].xml"


@contextmanager
def _generator_boundary() -> Generator[None, None, None]:
    yield


def _retain_then_abort(package: PackageView, retained: list[PackageView]) -> None:
    retained.append(package)
    message = "caller aborted"
    raise LookupError(message)


def _retain_then_read_broken(package: PackageView, retained: list[PackageView]) -> None:
    retained.append(package)
    _ = package.read_xml(BROKEN_PART)


def _track_zip_closure(monkeypatch: pytest.MonkeyPatch) -> list[ZipFile]:
    original_close = ZipFile.close
    closed_archives: list[ZipFile] = []

    def tracked_close(archive: ZipFile) -> None:
        original_close(archive)
        closed_archives.append(archive)

    monkeypatch.setattr(ZipFile, "close", tracked_close)
    return closed_archives


def _run_with_owned_package(
    path: Path,
    retained: list[PackageView],
    operation: Callable[[PackageView, list[PackageView]], None],
) -> None:
    with open_package(path, ExtractionLimits()) as package:
        operation(package, retained)


def test_arbitrary_caller_exception_closes_retained_package_view(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a genuine workbook and storage retaining its yielded public view.
    workbook = make_workbook(tmp_path / "caller-exception.xlsx")
    retained: list[PackageView] = []
    closed_archives = _track_zip_closure(monkeypatch)

    # When: arbitrary caller code aborts the owning context after retaining the view.
    with pytest.raises(LookupError, match="caller aborted"):
        _run_with_owned_package(workbook, retained, _retain_then_abort)

    # Then: later resource-backed use fails through the stable closed-view contract.
    with pytest.raises(ExtractionError) as caught:
        _ = retained[0].read_bytes(WORKBOOK_PART)
    assert caught.value.code is ErrorCode.EXTRACTION_FAILED
    assert caught.value.source is None
    assert len(closed_archives) == 1
    assert closed_archives[0].fp is None


def test_public_read_exception_closes_retained_package_view(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a retained view whose public XML read will raise from malformed content.
    workbook = make_workbook(tmp_path / "read-exception.xlsx")
    rewrite_package(workbook, {}, {BROKEN_PART: b"<broken>"})
    retained: list[PackageView] = []
    closed_archives = _track_zip_closure(monkeypatch)

    # When: an uncaught public read error unwinds the owning package context.
    with pytest.raises(ExtractionError) as read_failure:
        _run_with_owned_package(workbook, retained, _retain_then_read_broken)
    assert read_failure.value.code is ErrorCode.EXTRACTION_FAILED
    assert read_failure.value.source == BROKEN_PART

    # Then: the retained view reports deterministic closure on a later read.
    with pytest.raises(ExtractionError) as closed_failure:
        _ = retained[0].read_bytes(WORKBOOK_PART)
    assert closed_failure.value.code is ErrorCode.EXTRACTION_FAILED
    assert closed_failure.value.source is None
    assert len(closed_archives) == 1
    assert closed_archives[0].fp is None


def test_pre_yield_failure_remains_typed_through_generator_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: malformed identity XML and an outer generator-based caller boundary.
    workbook = make_workbook(tmp_path / "pre-yield-failure.xlsx")
    rewrite_package(workbook, {CONTENT_TYPES_PART: b"<broken>"}, {})
    closed_archives = _track_zip_closure(monkeypatch)

    # When: package validation fails before open_package can yield its public view.
    with (
        pytest.raises(ExtractionError) as caught,
        _generator_boundary(),
        open_package(workbook, ExtractionLimits()),
    ):
        pass

    # Then: context propagation preserves the typed failure and closes the archive.
    assert caught.value.code is ErrorCode.INVALID_XLSX
    assert caught.value.source == CONTENT_TYPES_PART
    assert len(closed_archives) == 1
    assert closed_archives[0].fp is None
