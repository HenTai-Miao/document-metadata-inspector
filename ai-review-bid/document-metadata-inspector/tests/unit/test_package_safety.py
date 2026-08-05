"""Archive inventory and fixture-safety tests for OOXML package access."""

from pathlib import Path
from zipfile import ZipFile

import pytest

from tests.factories import make_workbook, rewrite_package
from xlsx_metadata_forensics.errors import ErrorCode, ExtractionError
from xlsx_metadata_forensics.models import ExtractionLimits
from xlsx_metadata_forensics.ooxml.package import open_package

WORKBOOK_PART = "xl/workbook.xml"


def test_rewrite_factory_closes_sibling_zip_before_atomic_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a workbook and an observer at the atomic replacement boundary.
    workbook = make_workbook(tmp_path / "rewrite.xlsx")
    real_replace = Path.replace
    observed_parts: list[tuple[bool, bool]] = []

    def checked_replace(source: Path, destination: Path) -> Path:
        with ZipFile(source, "r") as completed:
            temporary_complete = completed.testzip() is None
        with ZipFile(destination, "r") as original:
            destination_unchanged = "custom/new.xml" not in original.namelist()
        observed_parts.append((temporary_complete, destination_unchanged))
        return real_replace(source, destination)

    monkeypatch.setattr(Path, "replace", checked_replace)

    # When: the package is rewritten with one addition.
    rewrite_package(workbook, {}, {"custom/new.xml": b"<new />"})

    # Then: only a complete closed sibling ZIP replaces the untouched fixture.
    assert observed_parts == [(True, True)]
    with ZipFile(workbook, "r") as rewritten:
        assert rewritten.read("custom/new.xml") == b"<new />"


def test_rejects_too_many_central_directory_entries(tmp_path: Path) -> None:
    # Given: a genuine workbook whose entry limit permits no ZIP members.
    workbook = make_workbook(tmp_path / "entries.xlsx")
    limits = ExtractionLimits(max_entries=0)

    # When / Then: central-directory count is rejected as unsafe.
    with pytest.raises(ExtractionError) as caught, open_package(workbook, limits):
        pass
    assert caught.value.code is ErrorCode.UNSAFE_PACKAGE


@pytest.mark.parametrize(
    "unsafe_name",
    [
        "/absolute.xml",
        "C:/drive.xml",
        "xl\\backslash.xml",
        "xl/../traversal.xml",
        "xl/%2e%2e/encoded-traversal.xml",
        "xl/%252e%252e/double-encoded-traversal.xml",
        "xl//empty-segment.xml",
        "xl/./dot-segment.xml",
    ],
    ids=(
        "absolute",
        "drive",
        "backslash",
        "dot-dot",
        "encoded-dot-dot",
        "double-encoded-dot-dot",
        "empty",
        "dot",
    ),
)
def test_rejects_each_unsafe_package_name(
    tmp_path: Path,
    unsafe_name: str,
) -> None:
    # Given: a genuine workbook with one independently unsafe member name.
    workbook = make_workbook(tmp_path / "unsafe-name.xlsx")
    rewrite_package(workbook, {}, {unsafe_name: b"unsafe"})

    # When / Then: the ambiguous member name rejects the whole package.
    with (
        pytest.raises(ExtractionError) as caught,
        open_package(workbook, ExtractionLimits()),
    ):
        pass
    assert caught.value.code is ErrorCode.UNSAFE_PACKAGE


def test_rejects_duplicate_central_directory_names(tmp_path: Path) -> None:
    # Given: a second central-directory record with an existing workbook name.
    workbook = make_workbook(tmp_path / "duplicate.xlsx")
    rewrite_package(workbook, {}, {WORKBOOK_PART: b"duplicate"})

    # When / Then: exact duplicate names are rejected before part lookup.
    with (
        pytest.raises(ExtractionError) as caught,
        open_package(workbook, ExtractionLimits()),
    ):
        pass
    assert caught.value.code is ErrorCode.UNSAFE_PACKAGE


def test_rejects_casefold_ambiguous_package_names(tmp_path: Path) -> None:
    # Given: a name that aliases the workbook on case-insensitive filesystems.
    workbook = make_workbook(tmp_path / "ambiguous.xlsx")
    rewrite_package(workbook, {}, {"XL/WORKBOOK.XML": b"ambiguous"})

    # When / Then: canonical-name ambiguity is rejected as unsafe.
    with (
        pytest.raises(ExtractionError) as caught,
        open_package(workbook, ExtractionLimits()),
    ):
        pass
    assert caught.value.code is ErrorCode.UNSAFE_PACKAGE


def test_validation_never_invokes_zipfile_extraction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a genuine workbook whose extraction APIs are forbidden.
    workbook = make_workbook(tmp_path / "no-extraction.xlsx")
    monkeypatch.setattr(ZipFile, "extract", pytest.fail)
    monkeypatch.setattr(ZipFile, "extractall", pytest.fail)

    # When: package validation runs with extraction methods disabled.
    with open_package(workbook, ExtractionLimits()) as package:
        workbook_present = package.has_part(WORKBOOK_PART)

    # Then: validation succeeded solely through in-package reads.
    assert workbook_present is True
