"""OPC content-type resolution across all supported Excel package formats."""

from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring

import pytest
from defusedxml.ElementTree import fromstring

from tests.factories import rewrite_package
from tests.opc_factories import (
    CONTENT_TYPES_PART,
    OPC_MAIN_TYPES,
    XML_WORKBOOK_PART,
    make_opc_workbook,
    read_part,
)
from xlsx_metadata_forensics.errors import ErrorCode, ExtractionError
from xlsx_metadata_forensics.formats import ExcelFormat
from xlsx_metadata_forensics.models import ExtractionLimits
from xlsx_metadata_forensics.ooxml.package import open_package

CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
OPC_FORMATS = [
    ExcelFormat.XLSX,
    ExcelFormat.XLSM,
    ExcelFormat.XLSB,
    ExcelFormat.XLTX,
    ExcelFormat.XLTM,
]


def _content_types(path: Path) -> Element:
    return fromstring(
        read_part(path, CONTENT_TYPES_PART),
        forbid_dtd=True,
        forbid_entities=True,
        forbid_external=True,
    )


def _write_content_types(path: Path, root: Element) -> None:
    rewrite_package(
        path,
        {
            CONTENT_TYPES_PART: tostring(
                root,
                encoding="utf-8",
                xml_declaration=True,
            )
        },
        {},
    )


def _main_part(excel_format: ExcelFormat) -> str:
    return "xl/workbook.bin" if excel_format is ExcelFormat.XLSB else XML_WORKBOOK_PART


def _replace_main_override_with_default(path: Path, excel_format: ExcelFormat) -> None:
    root = _content_types(path)
    part_name = f"/{_main_part(excel_format)}"
    overrides = [
        item
        for item in root
        if item.tag == f"{{{CONTENT_TYPES_NS}}}Override"
        and item.get("PartName") == part_name
    ]
    assert len(overrides) == 1
    root.remove(overrides[0])

    extension = "bin" if excel_format is ExcelFormat.XLSB else "xml"
    defaults = [
        item
        for item in root
        if item.tag == f"{{{CONTENT_TYPES_NS}}}Default"
        and (item.get("Extension") or "").casefold() == extension
    ]
    if defaults:
        assert len(defaults) == 1
        defaults[0].set("ContentType", OPC_MAIN_TYPES[excel_format].decode())
    else:
        _ = SubElement(
            root,
            f"{{{CONTENT_TYPES_NS}}}Default",
            Extension=extension,
            ContentType=OPC_MAIN_TYPES[excel_format].decode(),
        )
    _write_content_types(path, root)


@pytest.mark.parametrize("excel_format", OPC_FORMATS)
def test_unique_extension_default_resolves_each_selected_opc_format(
    tmp_path: Path,
    excel_format: ExcelFormat,
) -> None:
    # Given: one exact workbook MIME inherited from a unique extension Default.
    workbook = make_opc_workbook(
        tmp_path / f"default.{excel_format.value}",
        excel_format,
    )
    _replace_main_override_with_default(workbook, excel_format)

    # When: the matching adapter resolves the target's effective MIME.
    with open_package(
        workbook,
        ExtractionLimits(),
        expected_format=excel_format,
    ) as package:
        actual_format = package.format

    # Then: valid OPC Default serialization is accepted without rewriting source.
    assert actual_format is excel_format


def test_exact_xlsm_override_takes_precedence_over_xlsx_xml_default(
    tmp_path: Path,
) -> None:
    # Given: an XLSM Override and a different extension-wide XLSX Default.
    workbook = make_opc_workbook(tmp_path / "override.xlsm", ExcelFormat.XLSM)
    root = _content_types(workbook)
    defaults = [
        item
        for item in root
        if item.tag == f"{{{CONTENT_TYPES_NS}}}Default"
        and item.get("Extension") == "xml"
    ]
    assert len(defaults) == 1
    defaults[0].set("ContentType", OPC_MAIN_TYPES[ExcelFormat.XLSX].decode())
    _write_content_types(workbook, root)

    # When: exact target declaration is resolved first.
    with open_package(
        workbook,
        ExtractionLimits(),
        expected_format=ExcelFormat.XLSM,
    ) as package:
        actual_format = package.format

    # Then: the selected macro-enabled identity is retained.
    assert actual_format is ExcelFormat.XLSM


def test_rejects_case_equivalent_duplicate_xlsb_defaults(tmp_path: Path) -> None:
    # Given: an XLSB target with two case-equivalent binary Defaults.
    workbook = make_opc_workbook(tmp_path / "ambiguous.xlsb", ExcelFormat.XLSB)
    _replace_main_override_with_default(workbook, ExcelFormat.XLSB)
    root = _content_types(workbook)
    _ = SubElement(
        root,
        f"{{{CONTENT_TYPES_NS}}}Default",
        Extension="BIN",
        ContentType=OPC_MAIN_TYPES[ExcelFormat.XLSB].decode(),
    )
    _write_content_types(workbook, root)

    # When / Then: case aliases cannot establish one effective type.
    with (
        pytest.raises(ExtractionError) as caught,
        open_package(
            workbook,
            ExtractionLimits(),
            expected_format=ExcelFormat.XLSB,
        ),
    ):
        pass
    assert caught.value.code is ErrorCode.INVALID_EXCEL


def test_rejects_xlsm_when_xml_default_resolves_xlsx(tmp_path: Path) -> None:
    # Given: an XLSM-selected target inheriting an XLSX Default.
    workbook = make_opc_workbook(tmp_path / "wrong-default.xlsm", ExcelFormat.XLSM)
    _replace_main_override_with_default(workbook, ExcelFormat.XLSM)
    root = _content_types(workbook)
    defaults = [
        item
        for item in root
        if item.tag == f"{{{CONTENT_TYPES_NS}}}Default"
        and item.get("Extension") == "xml"
    ]
    assert len(defaults) == 1
    defaults[0].set("ContentType", OPC_MAIN_TYPES[ExcelFormat.XLSX].decode())
    _write_content_types(workbook, root)

    # When / Then: a recognized but mismatched effective type remains unsupported.
    with (
        pytest.raises(ExtractionError) as caught,
        open_package(
            workbook,
            ExtractionLimits(),
            expected_format=ExcelFormat.XLSM,
        ),
    ):
        pass
    assert caught.value.code is ErrorCode.UNSUPPORTED_FORMAT
