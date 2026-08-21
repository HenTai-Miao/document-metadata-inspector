"""Exact OPC main-part identities for supported Excel formats."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal

from xlsx_metadata_forensics.formats import ExcelFormat

type MainPartKind = Literal["xml", "binary"]

BRT_BEGIN_BOOK_PREFIX: Final = b"\x83\x01\x00"


@dataclass(frozen=True, slots=True)
class OpcFormatSpec:
    """Describe one exact supported OPC workbook main part."""

    format: ExcelFormat
    content_type: str
    target_extension: Literal["xml", "bin"]
    kind: MainPartKind


@dataclass(frozen=True, slots=True)
class OpcWorkbookIdentity:
    """Bind one validated package target to its actual Excel format."""

    format: ExcelFormat
    target: str
    content_type: str
    kind: MainPartKind


_SPECS: Final[tuple[OpcFormatSpec, ...]] = (
    OpcFormatSpec(
        ExcelFormat.XLSX,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
        "xml",
        "xml",
    ),
    OpcFormatSpec(
        ExcelFormat.XLSM,
        "application/vnd.ms-excel.sheet.macroEnabled.main+xml",
        "xml",
        "xml",
    ),
    OpcFormatSpec(
        ExcelFormat.XLSB,
        "application/vnd.ms-excel.sheet.binary.macroEnabled.main",
        "bin",
        "binary",
    ),
    OpcFormatSpec(
        ExcelFormat.XLTX,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.template.main+xml",
        "xml",
        "xml",
    ),
    OpcFormatSpec(
        ExcelFormat.XLTM,
        "application/vnd.ms-excel.template.macroEnabled.main+xml",
        "xml",
        "xml",
    ),
)
_SPECS_BY_FORMAT: Final[Mapping[ExcelFormat, OpcFormatSpec]] = MappingProxyType(
    {spec.format: spec for spec in _SPECS}
)
_SPECS_BY_CONTENT_TYPE: Final[Mapping[str, OpcFormatSpec]] = MappingProxyType(
    {spec.content_type: spec for spec in _SPECS}
)


def spec_for_format(excel_format: ExcelFormat) -> OpcFormatSpec | None:
    """Return the OPC spec for a format, or None for legacy OLE formats."""
    return _SPECS_BY_FORMAT.get(excel_format)


def spec_for_content_type(content_type: str) -> OpcFormatSpec | None:
    """Resolve one exact supported main MIME without fuzzy matching."""
    return _SPECS_BY_CONTENT_TYPE.get(content_type)
