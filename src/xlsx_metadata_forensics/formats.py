"""Typed identities for the supported Excel file family."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import assert_never

_UNSUPPORTED_SUFFIX_MESSAGE = "Unsupported Excel filename suffix."


class UnsupportedExcelFormatError(ValueError):
    """Reject a filename outside the approved Excel format contract."""

    def __init__(self) -> None:
        """Build the fixed, non-reflective format error."""
        super().__init__(_UNSUPPORTED_SUFFIX_MESSAGE)


class ContainerKind(StrEnum):
    """Identify the container parser required for an Excel format."""

    OLE = "ole"
    OPC = "opc"


class ExcelFormat(StrEnum):
    """Identify one supported Excel workbook or template format."""

    XLS = "xls"
    XLSX = "xlsx"
    XLSM = "xlsm"
    XLSB = "xlsb"
    XLT = "xlt"
    XLTX = "xltx"
    XLTM = "xltm"


@dataclass(frozen=True, slots=True)
class FormatIdentity:
    """Bind one declared Excel format to its required container family."""

    format: ExcelFormat
    container: ContainerKind


def identify_declared_format(path: Path) -> FormatIdentity:
    """Resolve one approved filename suffix without trusting its container."""
    suffix = path.suffix.removeprefix(".").casefold()
    try:
        excel_format = ExcelFormat(suffix)
    except ValueError:
        raise UnsupportedExcelFormatError from None

    return FormatIdentity(
        format=excel_format,
        container=_container_for_format(excel_format),
    )


def _container_for_format(excel_format: ExcelFormat) -> ContainerKind:
    match excel_format:
        case ExcelFormat.XLS | ExcelFormat.XLT:
            return ContainerKind.OLE
        case (
            ExcelFormat.XLSX
            | ExcelFormat.XLSM
            | ExcelFormat.XLSB
            | ExcelFormat.XLTX
            | ExcelFormat.XLTM
        ):
            return ContainerKind.OPC
        case _:
            assert_never(excel_format)
