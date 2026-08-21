"""Excel-family OPC format identity tests."""

from pathlib import Path

import pytest

from tests.factories import rewrite_package
from tests.opc_factories import (
    BINARY_WORKBOOK_PART,
    CONTENT_TYPES_PART,
    ROOT_RELS_PART,
    XML_WORKBOOK_PART,
    make_opc_workbook,
    read_part,
)
from xlsx_metadata_forensics.errors import ErrorCode, ExtractionError
from xlsx_metadata_forensics.formats import ExcelFormat
from xlsx_metadata_forensics.models import ExtractionLimits
from xlsx_metadata_forensics.ooxml.package import open_package

OPC_FORMATS = [
    ExcelFormat.XLSX,
    ExcelFormat.XLSM,
    ExcelFormat.XLSB,
    ExcelFormat.XLTX,
    ExcelFormat.XLTM,
]


@pytest.mark.parametrize("excel_format", OPC_FORMATS)
def test_accepts_each_exact_opc_format_when_explicitly_expected(
    tmp_path: Path,
    excel_format: ExcelFormat,
) -> None:
    # Given: one package carrying the exact main MIME and shape for its suffix.
    workbook = make_opc_workbook(
        tmp_path / f"fixture.{excel_format.value}",
        excel_format,
    )

    # When: its caller explicitly selects that format adapter.
    with open_package(
        workbook,
        ExtractionLimits(),
        expected_format=excel_format,
    ) as package:
        actual_format = package.format

    # Then: the validated internal identity, not just the suffix, is returned.
    assert actual_format is excel_format


def test_two_argument_open_remains_xlsx_compatible(tmp_path: Path) -> None:
    # Given: one genuine ordinary XLSX.
    workbook = make_opc_workbook(tmp_path / "default.xlsx", ExcelFormat.XLSX)

    # When: the existing two-argument public API is used.
    with open_package(workbook, ExtractionLimits()) as package:
        actual_format = package.format

    # Then: it remains strict XLSX mode and exposes that validated identity.
    assert actual_format is ExcelFormat.XLSX


@pytest.mark.parametrize(
    ("actual_format", "expected_format"),
    [
        (ExcelFormat.XLSX, ExcelFormat.XLSM),
        (ExcelFormat.XLSM, ExcelFormat.XLSX),
        (ExcelFormat.XLTX, ExcelFormat.XLTM),
        (ExcelFormat.XLSB, ExcelFormat.XLSM),
    ],
)
def test_rejects_internal_mime_that_does_not_match_selected_adapter(
    tmp_path: Path,
    actual_format: ExcelFormat,
    expected_format: ExcelFormat,
) -> None:
    # Given: an internally coherent package for a different Excel format.
    workbook = make_opc_workbook(
        tmp_path / f"mismatch.{expected_format.value}",
        actual_format,
    )

    # When / Then: the filename cannot override the exact internal MIME.
    with (
        pytest.raises(ExtractionError) as caught,
        open_package(
            workbook,
            ExtractionLimits(),
            expected_format=expected_format,
        ),
    ):
        pass
    assert caught.value.code is ErrorCode.UNSUPPORTED_FORMAT


def test_rejects_xlsb_main_part_without_brt_begin_book(tmp_path: Path) -> None:
    # Given: an XLSB-declared package whose binary main part is arbitrary bytes.
    workbook = make_opc_workbook(tmp_path / "wrong-header.xlsb", ExcelFormat.XLSB)
    rewrite_package(
        workbook,
        {BINARY_WORKBOOK_PART: b"not-a-biff12-workbook"},
        {},
    )

    # When / Then: MIME alone cannot establish an XLSB workbook identity.
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
    assert caught.value.source == BINARY_WORKBOOK_PART


def test_rejects_xlsb_mime_attached_to_xml_named_main_part(tmp_path: Path) -> None:
    # Given: XLSB MIME and bytes are attached to an XML-shaped target name.
    workbook = make_opc_workbook(tmp_path / "binary-as-xml.xlsb", ExcelFormat.XLSB)
    content_types = read_part(workbook, CONTENT_TYPES_PART).replace(
        b"/xl/workbook.bin", b"/xl/workbook.xml"
    )
    relationships = read_part(workbook, ROOT_RELS_PART).replace(
        b'Target="xl/workbook.bin"', b'Target="xl/workbook.xml"'
    )
    binary_payload = read_part(workbook, BINARY_WORKBOOK_PART)
    rewrite_package(
        workbook,
        {
            CONTENT_TYPES_PART: content_types,
            ROOT_RELS_PART: relationships,
            BINARY_WORKBOOK_PART: None,
        },
        {XML_WORKBOOK_PART: binary_payload},
    )

    # When / Then: the binary adapter requires a binary main-part shape.
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


def test_rejects_xml_mime_attached_to_binary_named_main_part(tmp_path: Path) -> None:
    # Given: an XLSM XML workbook root is moved under a binary-shaped name.
    workbook = make_opc_workbook(tmp_path / "xml-as-binary.xlsm", ExcelFormat.XLSM)
    content_types = read_part(workbook, CONTENT_TYPES_PART).replace(
        b"/xl/workbook.xml", b"/xl/workbook.bin"
    )
    relationships = read_part(workbook, ROOT_RELS_PART).replace(
        b'Target="xl/workbook.xml"', b'Target="xl/workbook.bin"'
    )
    xml_payload = read_part(workbook, XML_WORKBOOK_PART)
    rewrite_package(
        workbook,
        {
            CONTENT_TYPES_PART: content_types,
            ROOT_RELS_PART: relationships,
            XML_WORKBOOK_PART: None,
        },
        {BINARY_WORKBOOK_PART: xml_payload},
    )

    # When / Then: an XML adapter requires an XML main-part shape and root.
    with (
        pytest.raises(ExtractionError) as caught,
        open_package(
            workbook,
            ExtractionLimits(),
            expected_format=ExcelFormat.XLSM,
        ),
    ):
        pass
    assert caught.value.code is ErrorCode.INVALID_EXCEL
