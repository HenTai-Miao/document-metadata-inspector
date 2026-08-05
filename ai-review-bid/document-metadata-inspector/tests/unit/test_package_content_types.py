"""Workbook content-type resolution through OPC defaults."""

from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring
from zipfile import ZipFile

import pytest
from defusedxml.ElementTree import fromstring

from tests.factories import make_workbook, rewrite_package
from xlsx_metadata_forensics.errors import ErrorCode, ExtractionError
from xlsx_metadata_forensics.models import ExtractionLimits
from xlsx_metadata_forensics.ooxml.package import open_package

CONTENT_TYPES_PART = "[Content_Types].xml"
ROOT_RELS_PART = "_rels/.rels"
WORKBOOK_PART = "xl/workbook.xml"
CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
XLSX_MAIN_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
)
XLSM_MAIN_TYPE = "application/vnd.ms-excel.sheet.macroEnabled.main+xml"


def _part_bytes(path: Path, name: str) -> bytes:
    with ZipFile(path, "r") as archive:
        return archive.read(name)


def _content_types(path: Path) -> Element:
    return fromstring(
        _part_bytes(path, CONTENT_TYPES_PART),
        forbid_dtd=True,
        forbid_entities=True,
        forbid_external=True,
    )


def _write_content_types(path: Path, content_types: Element) -> None:
    rewrite_package(
        path,
        {
            CONTENT_TYPES_PART: tostring(
                content_types,
                encoding="utf-8",
                xml_declaration=True,
            )
        },
        {},
    )


def _use_xml_default_for_workbook(path: Path) -> None:
    content_types = _content_types(path)
    defaults = tuple(
        item
        for item in content_types
        if item.tag == f"{{{CONTENT_TYPES_NS}}}Default"
        and item.get("Extension") == "xml"
    )
    overrides = tuple(
        item
        for item in content_types
        if item.tag == f"{{{CONTENT_TYPES_NS}}}Override"
        and item.get("PartName") == f"/{WORKBOOK_PART}"
    )
    assert len(defaults) == len(overrides) == 1
    defaults[0].set("ContentType", XLSX_MAIN_TYPE)
    content_types.remove(overrides[0])
    relationships = _part_bytes(path, ROOT_RELS_PART)
    changed_relationships = relationships.replace(
        b'Target="xl/workbook.xml"', b'Target="/xl/workbook.xml"'
    )
    assert changed_relationships != relationships
    _write_content_types(path, content_types)
    rewrite_package(path, {ROOT_RELS_PART: changed_relationships}, {})


def _set_xml_default(path: Path, content_type: str) -> None:
    content_types = _content_types(path)
    defaults = tuple(
        item
        for item in content_types
        if item.tag == f"{{{CONTENT_TYPES_NS}}}Default"
        and item.get("Extension") == "xml"
    )
    assert len(defaults) == 1
    defaults[0].set("ContentType", content_type)
    _write_content_types(path, content_types)


def _set_workbook_override(path: Path, content_type: str) -> None:
    content_types = _content_types(path)
    overrides = tuple(
        item
        for item in content_types
        if item.tag == f"{{{CONTENT_TYPES_NS}}}Override"
        and item.get("PartName") == f"/{WORKBOOK_PART}"
    )
    assert len(overrides) == 1
    overrides[0].set("ContentType", content_type)
    _write_content_types(path, content_types)


def _remove_workbook_override(path: Path) -> None:
    content_types = _content_types(path)
    overrides = tuple(
        item
        for item in content_types
        if item.tag == f"{{{CONTENT_TYPES_NS}}}Override"
        and item.get("PartName") == f"/{WORKBOOK_PART}"
    )
    assert len(overrides) == 1
    content_types.remove(overrides[0])
    _write_content_types(path, content_types)


def test_accepts_workbook_type_from_unique_extension_default(tmp_path: Path) -> None:
    # Given: a genuine XLSX whose workbook alone inherits the XML Default type.
    workbook = make_workbook(tmp_path / "default-content-type.xlsx")
    _use_xml_default_for_workbook(workbook)

    # When: package identity resolves the declared workbook's effective type.
    with open_package(workbook, ExtractionLimits()) as package:
        workbook_present = package.has_part(WORKBOOK_PART)

    # Then: a valid extension-default declaration is accepted without rewriting it.
    assert workbook_present is True


def test_exact_override_takes_precedence_over_matching_default(tmp_path: Path) -> None:
    # Given: the extension Default says XLSX while the target Override says XLSM.
    workbook = make_workbook(tmp_path / "override-precedence.xlsx")
    _set_xml_default(workbook, XLSX_MAIN_TYPE)
    _set_workbook_override(workbook, XLSM_MAIN_TYPE)

    # When / Then: the target-specific declaration wins and remains unsupported.
    with (
        pytest.raises(ExtractionError) as caught,
        open_package(workbook, ExtractionLimits()),
    ):
        pass
    assert caught.value.code is ErrorCode.UNSUPPORTED_FORMAT


def test_rejects_ambiguous_matching_extension_defaults(tmp_path: Path) -> None:
    # Given: a default-declared workbook with a second case-equivalent XML Default.
    workbook = make_workbook(tmp_path / "ambiguous-defaults.xlsx")
    _use_xml_default_for_workbook(workbook)
    content_types = _content_types(workbook)
    _ = SubElement(
        content_types,
        f"{{{CONTENT_TYPES_NS}}}Default",
        Extension="XML",
        ContentType=XLSX_MAIN_TYPE,
    )
    _write_content_types(workbook, content_types)

    # When / Then: ambiguous extension declarations cannot establish identity.
    with (
        pytest.raises(ExtractionError) as caught,
        open_package(workbook, ExtractionLimits()),
    ):
        pass
    assert caught.value.code is ErrorCode.INVALID_XLSX


def test_maps_unsupported_extension_default_to_unsupported_format(
    tmp_path: Path,
) -> None:
    # Given: a workbook whose effective extension Default declares XLSM.
    workbook = make_workbook(tmp_path / "unsupported-default.xlsx")
    _use_xml_default_for_workbook(workbook)
    _set_xml_default(workbook, XLSM_MAIN_TYPE)

    # When / Then: fallback resolves the type before exact XLSX enforcement.
    with (
        pytest.raises(ExtractionError) as caught,
        open_package(workbook, ExtractionLimits()),
    ):
        pass
    assert caught.value.code is ErrorCode.UNSUPPORTED_FORMAT


def test_rejects_target_without_override_or_matching_default(tmp_path: Path) -> None:
    # Given: a workbook target with no Override or Default for its XML extension.
    workbook = make_workbook(tmp_path / "missing-content-type.xlsx")
    _remove_workbook_override(workbook)
    content_types = _content_types(workbook)
    defaults = tuple(
        item
        for item in content_types
        if item.tag == f"{{{CONTENT_TYPES_NS}}}Default"
        and item.get("Extension") == "xml"
    )
    assert len(defaults) == 1
    defaults[0].set("Extension", "not-xml")
    _write_content_types(workbook, content_types)

    # When / Then: no effective workbook type remains an invalid XLSX identity.
    with (
        pytest.raises(ExtractionError) as caught,
        open_package(workbook, ExtractionLimits()),
    ):
        pass
    assert caught.value.code is ErrorCode.INVALID_XLSX
