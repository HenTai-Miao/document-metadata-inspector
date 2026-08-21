"""Core behavior tests for bounded OOXML package access."""

from pathlib import Path
from zipfile import ZipFile

import pytest

from tests.factories import make_workbook, rewrite_package
from xlsx_metadata_forensics.errors import ErrorCode, ExtractionError
from xlsx_metadata_forensics.models import ExtractionLimits
from xlsx_metadata_forensics.ooxml.package import open_package

WORKBOOK_PART = "xl/workbook.xml"
WORKBOOK_TAG = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}workbook"


def test_valid_xlsx_opens_with_stable_immutable_inventory(tmp_path: Path) -> None:
    # Given: a genuine workbook package.
    workbook = make_workbook(tmp_path / "valid.xlsx")

    # When: its validated inventory is observed before and after a part read.
    with open_package(workbook, ExtractionLimits()) as package:
        first_names = package.names
        first_count = package.entry_count
        _ = package.read_bytes("[Content_Types].xml")
        second_names = package.names
        second_count = package.entry_count

    # Then: inventory values are immutable tuples and remain stable after closure.
    assert type(first_names) is tuple
    assert first_names == tuple(sorted(first_names))
    assert first_names is second_names
    assert first_count == second_count == len(first_names)
    assert package.names is first_names
    assert not hasattr(package, "__dict__")
    names_attribute = "names"
    count_attribute = "entry_count"
    with pytest.raises(AttributeError):
        setattr(package, names_attribute, ("changed.xml",))
    with pytest.raises(AttributeError):
        setattr(package, count_attribute, 0)


def test_valid_xlsx_exposes_part_lookup_and_required_xml(tmp_path: Path) -> None:
    # Given: a genuine workbook package.
    workbook = make_workbook(tmp_path / "valid.xlsx")

    # When: the workbook part is looked up and parsed as required XML.
    with open_package(workbook, ExtractionLimits()) as package:
        present = package.has_part(WORKBOOK_PART)
        root = package.read_xml(WORKBOOK_PART, required=True)

    # Then: the genuine workbook XML root is returned.
    assert present is True
    assert root.tag == WORKBOOK_TAG


def test_optional_absent_xml_returns_none(tmp_path: Path) -> None:
    # Given: a genuine workbook without an optional custom part.
    workbook = make_workbook(tmp_path / "valid.xlsx")

    # When: the absent part is requested as optional XML.
    with open_package(workbook, ExtractionLimits()) as package:
        result = package.read_xml("docProps/absent.xml")

    # Then: absence is represented only by None.
    assert result is None


def test_required_absent_xml_raises_typed_extraction_error(tmp_path: Path) -> None:
    # Given: a genuine workbook without the requested required part.
    workbook = make_workbook(tmp_path / "valid.xlsx")

    # When / Then: required absence is a stable extraction failure.
    with (
        open_package(workbook, ExtractionLimits()) as package,
        pytest.raises(ExtractionError) as caught,
    ):
        _ = package.read_xml("docProps/absent.xml", required=True)
    assert caught.value.code is ErrorCode.EXTRACTION_FAILED
    assert caught.value.source == "docProps/absent.xml"


def test_present_malformed_optional_xml_raises_instead_of_returning_none(
    tmp_path: Path,
) -> None:
    # Given: a genuine workbook containing malformed optional XML.
    workbook = make_workbook(tmp_path / "malformed-part.xlsx")
    rewrite_package(
        workbook,
        replacements={},
        additions={"docProps/broken.xml": b"<broken>"},
    )

    # When / Then: malformed presence is a typed extraction failure.
    with (
        open_package(workbook, ExtractionLimits()) as package,
        pytest.raises(ExtractionError) as caught,
    ):
        _ = package.read_xml("docProps/broken.xml")
    assert caught.value.code is ErrorCode.EXTRACTION_FAILED
    assert caught.value.source == "docProps/broken.xml"


def test_context_exit_closes_package_reads(tmp_path: Path) -> None:
    # Given: a package view whose context has exited.
    workbook = make_workbook(tmp_path / "valid.xlsx")
    with open_package(workbook, ExtractionLimits()) as package:
        assert package.has_part(WORKBOOK_PART)

    # When / Then: resource-backed reads cannot outlive the owning context.
    with pytest.raises(ExtractionError) as caught:
        _ = package.read_bytes(WORKBOOK_PART)
    assert caught.value.code is ErrorCode.EXTRACTION_FAILED


def test_context_exit_closes_package_xml_parsing(tmp_path: Path) -> None:
    # Given: a package view whose owning context has exited.
    workbook = make_workbook(tmp_path / "valid.xlsx")
    with open_package(workbook, ExtractionLimits()) as package:
        assert package.has_part(WORKBOOK_PART)

    # When / Then: XML parsing cannot outlive the owning context.
    with pytest.raises(ExtractionError) as caught:
        _ = package.read_xml(WORKBOOK_PART, required=True)
    assert caught.value.code is ErrorCode.EXTRACTION_FAILED


def test_context_exit_closes_package_hashing(tmp_path: Path) -> None:
    # Given: a package view whose owning context has exited.
    workbook = make_workbook(tmp_path / "valid.xlsx")
    with open_package(workbook, ExtractionLimits()) as package:
        assert package.has_part(WORKBOOK_PART)

    # When / Then: hashing cannot outlive the owning context.
    with pytest.raises(ExtractionError) as caught:
        _ = package.sha256_part(WORKBOOK_PART)
    assert caught.value.code is ErrorCode.EXTRACTION_FAILED


def test_rejects_plain_zip_when_required_xlsx_parts_are_missing(
    tmp_path: Path,
) -> None:
    # Given: a valid ZIP that is not an XLSX.
    fake = tmp_path / "fake.xlsx"
    with ZipFile(fake, "w") as archive:
        archive.writestr("note.txt", "not a workbook")

    # When / Then: package validation rejects it with the stable code.
    with (
        pytest.raises(ExtractionError) as caught,
        open_package(fake, ExtractionLimits()),
    ):
        pass
    assert caught.value.code is ErrorCode.INVALID_XLSX


def test_cfb_ole_header_maps_to_encrypted_xlsx(tmp_path: Path) -> None:
    # Given: a file carrying the Compound File Binary header.
    disguised = tmp_path / "encrypted.xlsx"
    _ = disguised.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"container")

    # When / Then: it is rejected before ZIP parsing as encrypted XLSX.
    with (
        pytest.raises(ExtractionError) as caught,
        open_package(disguised, ExtractionLimits()),
    ):
        pass
    assert caught.value.code is ErrorCode.ENCRYPTED_XLSX


def test_malformed_zip_maps_to_corrupt_package(tmp_path: Path) -> None:
    # Given: bytes that are neither CFB nor a valid ZIP.
    malformed = tmp_path / "corrupt.xlsx"
    _ = malformed.write_bytes(b"PK\x03\x04truncated")

    # When / Then: malformed ZIP structure has its independent code.
    with (
        pytest.raises(ExtractionError) as caught,
        open_package(malformed, ExtractionLimits()),
    ):
        pass
    assert caught.value.code is ErrorCode.CORRUPT_PACKAGE


def test_file_size_limit_precedes_zip_parsing(tmp_path: Path) -> None:
    # Given: malformed bytes larger than the configured input limit.
    oversized = tmp_path / "oversized.xlsx"
    _ = oversized.write_bytes(b"not-a-zip")
    limits = ExtractionLimits(max_file_bytes=8)

    # When / Then: physical size is rejected before malformed ZIP parsing.
    with pytest.raises(ExtractionError) as caught, open_package(oversized, limits):
        pass
    assert caught.value.code is ErrorCode.FILE_TOO_LARGE


def test_unreadable_missing_path_maps_to_extraction_failed(tmp_path: Path) -> None:
    # Given: a path that does not exist.
    missing = tmp_path / "missing.xlsx"

    # When / Then: local I/O failure uses the independent extraction code.
    with (
        pytest.raises(ExtractionError) as caught,
        open_package(missing, ExtractionLimits()),
    ):
        pass
    assert caught.value.code is ErrorCode.EXTRACTION_FAILED


def test_unreadable_directory_path_maps_to_extraction_failed(tmp_path: Path) -> None:
    # Given: an existing path that cannot be opened as an input file.
    directory = tmp_path / "directory.xlsx"
    directory.mkdir()

    # When / Then: the concrete local I/O failure is converted at the boundary.
    with (
        pytest.raises(ExtractionError) as caught,
        open_package(directory, ExtractionLimits()),
    ):
        pass
    assert caught.value.code is ErrorCode.EXTRACTION_FAILED
