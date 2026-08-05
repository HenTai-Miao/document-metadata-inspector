"""Controlled OPC Excel-family fixture construction for tests."""

from pathlib import Path
from zipfile import ZipFile

from tests.factories import make_workbook, rewrite_package
from xlsx_metadata_forensics.formats import ExcelFormat

CONTENT_TYPES_PART = "[Content_Types].xml"
ROOT_RELS_PART = "_rels/.rels"
XML_WORKBOOK_PART = "xl/workbook.xml"
BINARY_WORKBOOK_PART = "xl/workbook.bin"
BRT_BEGIN_BOOK = b"\x83\x01\x00"

XLSX_MAIN_TYPE = (
    b"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
)
OPC_MAIN_TYPES: dict[ExcelFormat, bytes] = {
    ExcelFormat.XLSX: XLSX_MAIN_TYPE,
    ExcelFormat.XLSM: b"application/vnd.ms-excel.sheet.macroEnabled.main+xml",
    ExcelFormat.XLSB: b"application/vnd.ms-excel.sheet.binary.macroEnabled.main",
    ExcelFormat.XLTX: (
        b"application/vnd.openxmlformats-officedocument.spreadsheetml.template.main+xml"
    ),
    ExcelFormat.XLTM: b"application/vnd.ms-excel.template.macroEnabled.main+xml",
}


def read_part(path: Path, name: str) -> bytes:
    """Read one fixture part outside production access-boundary assertions."""
    with ZipFile(path, "r") as archive:
        return archive.read(name)


def make_opc_workbook(path: Path, excel_format: ExcelFormat) -> Path:
    """Create one structurally controlled OPC workbook identity fixture."""
    if excel_format not in OPC_MAIN_TYPES:
        message = "The fixture factory supports OPC Excel formats only."
        raise ValueError(message)

    workbook = make_workbook(path)
    content_types = read_part(workbook, CONTENT_TYPES_PART)
    relationships = read_part(workbook, ROOT_RELS_PART)
    requested_type = OPC_MAIN_TYPES[excel_format]
    changed_content_types = content_types.replace(XLSX_MAIN_TYPE, requested_type)
    assert changed_content_types != content_types or excel_format is ExcelFormat.XLSX

    if excel_format is not ExcelFormat.XLSB:
        rewrite_package(workbook, {CONTENT_TYPES_PART: changed_content_types}, {})
        return workbook

    binary_content_types = changed_content_types.replace(
        b"/xl/workbook.xml", b"/xl/workbook.bin"
    )
    binary_relationships = relationships.replace(
        b'Target="xl/workbook.xml"', b'Target="xl/workbook.bin"'
    )
    assert binary_content_types != changed_content_types
    assert binary_relationships != relationships
    rewrite_package(
        workbook,
        {
            CONTENT_TYPES_PART: binary_content_types,
            ROOT_RELS_PART: binary_relationships,
            XML_WORKBOOK_PART: None,
        },
        {BINARY_WORKBOOK_PART: BRT_BEGIN_BOOK},
    )
    return workbook
