"""Genuine-XLSX identity and critical-XML tests for package access."""

from pathlib import Path
from zipfile import ZipFile

import pytest

from tests.factories import make_workbook, rewrite_package
from xlsx_metadata_forensics.errors import ErrorCode, ExtractionError
from xlsx_metadata_forensics.models import ExtractionLimits
from xlsx_metadata_forensics.ooxml.package import open_package

CONTENT_TYPES_PART = "[Content_Types].xml"
ROOT_RELS_PART = "_rels/.rels"
WORKBOOK_PART = "xl/workbook.xml"
XLSX_MAIN_TYPE = (
    b"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
)


def _part_bytes(path: Path, name: str) -> bytes:
    with ZipFile(path, "r") as archive:
        return archive.read(name)


def _replace_main_content_type(path: Path, replacement: str) -> None:
    original = _part_bytes(path, CONTENT_TYPES_PART)
    changed = original.replace(XLSX_MAIN_TYPE, replacement.encode())
    assert changed != original
    rewrite_package(path, {CONTENT_TYPES_PART: changed}, {})


@pytest.mark.parametrize(
    "missing_part",
    [CONTENT_TYPES_PART, ROOT_RELS_PART, WORKBOOK_PART],
    ids=("content-types", "root-relationships", "workbook-target"),
)
def test_rejects_each_missing_critical_ooxml_part(
    tmp_path: Path,
    missing_part: str,
) -> None:
    # Given: an otherwise genuine workbook missing one critical OOXML part.
    workbook = make_workbook(tmp_path / "missing-critical.xlsx")
    rewrite_package(workbook, {missing_part: None}, {})

    # When / Then: the package cannot be trusted as XLSX.
    with (
        pytest.raises(ExtractionError) as caught,
        open_package(workbook, ExtractionLimits()),
    ):
        pass
    assert caught.value.code is ErrorCode.INVALID_XLSX


@pytest.mark.parametrize(
    "part_name",
    [CONTENT_TYPES_PART, ROOT_RELS_PART, WORKBOOK_PART],
    ids=("content-types", "root-relationships", "workbook"),
)
def test_rejects_each_malformed_critical_xml_part(
    tmp_path: Path,
    part_name: str,
) -> None:
    # Given: an otherwise genuine workbook with one malformed critical XML part.
    workbook = make_workbook(tmp_path / "malformed-critical.xlsx")
    rewrite_package(workbook, {part_name: b"<broken>"}, {})

    # When / Then: malformed critical XML is a typed invalid-XLSX failure.
    with (
        pytest.raises(ExtractionError) as caught,
        open_package(workbook, ExtractionLimits()),
    ):
        pass
    assert caught.value.code is ErrorCode.INVALID_XLSX


@pytest.mark.parametrize(
    ("part_name", "wrong_root"),
    [
        (CONTENT_TYPES_PART, b"<Types />"),
        (ROOT_RELS_PART, b"<Relationships />"),
        (WORKBOOK_PART, b"<notWorkbook />"),
    ],
    ids=("content-types", "root-relationships", "workbook"),
)
def test_rejects_each_wrong_critical_xml_root(
    tmp_path: Path,
    part_name: str,
    wrong_root: bytes,
) -> None:
    # Given: well-formed critical XML carrying an untrusted root element.
    workbook = make_workbook(tmp_path / "wrong-root.xlsx")
    rewrite_package(workbook, {part_name: wrong_root}, {})

    # When / Then: a lookalike critical part is not accepted as genuine XLSX.
    with (
        pytest.raises(ExtractionError) as caught,
        open_package(workbook, ExtractionLimits()),
    ):
        pass
    assert caught.value.code is ErrorCode.INVALID_XLSX


def test_accepts_internal_relationship_targeting_genuine_moved_workbook(
    tmp_path: Path,
) -> None:
    # Given: the genuine workbook root is consistently moved to another part.
    workbook = make_workbook(tmp_path / "moved-workbook.xlsx")
    content_types = _part_bytes(workbook, CONTENT_TYPES_PART).replace(
        b'/xl/workbook.xml"', b'/custom/main.xml"'
    )
    relationships = _part_bytes(workbook, ROOT_RELS_PART).replace(
        b'Target="xl/workbook.xml"', b'Target="custom/main.xml"'
    )
    workbook_xml = _part_bytes(workbook, WORKBOOK_PART)
    rewrite_package(
        workbook,
        {
            CONTENT_TYPES_PART: content_types,
            ROOT_RELS_PART: relationships,
            WORKBOOK_PART: None,
        },
        {"custom/main.xml": workbook_xml},
    )

    # When: the declared internal target is validated rather than hard-coded.
    with open_package(workbook, ExtractionLimits()) as package:
        moved_part_present = package.has_part("custom/main.xml")

    # Then: the consistent genuine workbook target is accepted.
    assert moved_part_present is True


def test_rejects_root_relationship_to_missing_workbook_target(tmp_path: Path) -> None:
    # Given: root relationships naming a workbook part that does not exist.
    workbook = make_workbook(tmp_path / "missing-target.xlsx")
    relationships = _part_bytes(workbook, ROOT_RELS_PART)
    changed = relationships.replace(b'xl/workbook.xml"', b'xl/missing.xml"')
    assert changed != relationships
    rewrite_package(workbook, {ROOT_RELS_PART: changed}, {})

    # When / Then: relationship presence cannot impersonate a workbook target.
    with (
        pytest.raises(ExtractionError) as caught,
        open_package(workbook, ExtractionLimits()),
    ):
        pass
    assert caught.value.code is ErrorCode.INVALID_XLSX


@pytest.mark.parametrize(
    "target_replacement",
    [
        b'https://example.invalid/book.xlsx" TargetMode="External',
        b"../xl/workbook.xml",
    ],
    ids=("external", "root-escape"),
)
def test_rejects_non_internal_office_document_target(
    tmp_path: Path,
    target_replacement: bytes,
) -> None:
    # Given: the root relationship attempts a non-internal workbook target.
    workbook = make_workbook(tmp_path / "unsafe-target.xlsx")
    relationships = _part_bytes(workbook, ROOT_RELS_PART)
    changed = relationships.replace(b"xl/workbook.xml", target_replacement)
    assert changed != relationships
    rewrite_package(workbook, {ROOT_RELS_PART: changed}, {})

    # When / Then: validation rejects the target without dereferencing it.
    with (
        pytest.raises(ExtractionError) as caught,
        open_package(workbook, ExtractionLimits()),
    ):
        pass
    assert caught.value.code is ErrorCode.INVALID_XLSX


@pytest.mark.parametrize(
    "unsupported_type",
    [
        "application/vnd.ms-excel.sheet.macroEnabled.main+xml",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.template.main+xml",
        "application/xml",
    ],
    ids=("macro-enabled", "template", "other"),
)
def test_rejects_non_xlsx_workbook_main_content_types(
    tmp_path: Path,
    unsupported_type: str,
) -> None:
    # Given: a genuine package declaring a non-XLSX workbook main type.
    workbook = make_workbook(tmp_path / "unsupported.xlsx")
    _replace_main_content_type(workbook, unsupported_type)

    # When / Then: every non-exact main type is unsupported, not accepted.
    with (
        pytest.raises(ExtractionError) as caught,
        open_package(workbook, ExtractionLimits()),
    ):
        pass
    assert caught.value.code is ErrorCode.UNSUPPORTED_FORMAT


def test_defused_parser_rejects_external_entity_in_critical_xml(tmp_path: Path) -> None:
    # Given: a critical part attempting an external XML entity.
    workbook = make_workbook(tmp_path / "external-entity.xlsx")
    malicious = b"""<!DOCTYPE Types [<!ENTITY xxe SYSTEM 'file:///etc/passwd'>]>
<Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'>&xxe;</Types>"""
    rewrite_package(workbook, {CONTENT_TYPES_PART: malicious}, {})

    # When / Then: parsing fails safely as invalid XLSX without dereferencing it.
    with (
        pytest.raises(ExtractionError) as caught,
        open_package(workbook, ExtractionLimits()),
    ):
        pass
    assert caught.value.code is ErrorCode.INVALID_XLSX
