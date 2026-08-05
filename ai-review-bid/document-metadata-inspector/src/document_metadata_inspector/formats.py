"""Declared and observed identities for supported document formats."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

SUPPORTED_SUFFIXES: Final = (
    ".pdf",
    ".doc",
    ".docx",
    ".docm",
    ".dot",
    ".dotx",
    ".dotm",
    ".xls",
    ".xlsx",
    ".xlsm",
    ".xlsb",
    ".xlt",
    ".xltx",
    ".xltm",
)

_OLE_MAGIC: Final = bytes.fromhex("D0CF11E0A1B11AE1")
_ZIP_MAGICS: Final = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
_UNSUPPORTED_SUFFIX_MESSAGE: Final = "Unsupported document filename suffix."


class UnsupportedDocumentFormatError(ValueError):
    """Reject a filename outside the explicitly supported format contract."""

    def __init__(self) -> None:
        """Build a fixed error that does not disclose a local path."""
        super().__init__(_UNSUPPORTED_SUFFIX_MESSAGE)


class DocumentFamily(StrEnum):
    """Group formats that expose the same high-level evidence concepts."""

    PDF = "pdf"
    WORD = "word"
    EXCEL = "excel"


class ContainerKind(StrEnum):
    """Identify the native container parser required by a file."""

    PDF = "pdf"
    OLE = "ole"
    OPC = "opc"


class DocumentFormat(StrEnum):
    """Identify one supported document, workbook or template format."""

    PDF = "pdf"
    DOC = "doc"
    DOCX = "docx"
    DOCM = "docm"
    DOT = "dot"
    DOTX = "dotx"
    DOTM = "dotm"
    XLS = "xls"
    XLSX = "xlsx"
    XLSM = "xlsm"
    XLSB = "xlsb"
    XLT = "xlt"
    XLTX = "xltx"
    XLTM = "xltm"


class FormatIdentityStatus(StrEnum):
    """Describe whether container evidence agrees with the filename."""

    UNVERIFIED = "unverified"
    CONFIRMED = "confirmed"
    MISMATCH = "mismatch"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class FormatIdentity:
    """Preserve declared identity separately from observed container evidence."""

    declared_format: DocumentFormat
    family: DocumentFamily
    expected_container: ContainerKind
    observed_container: ContainerKind | None = None
    status: FormatIdentityStatus = FormatIdentityStatus.UNVERIFIED


_FORMAT_FACTS: Final[dict[DocumentFormat, tuple[DocumentFamily, ContainerKind]]] = {
    DocumentFormat.PDF: (DocumentFamily.PDF, ContainerKind.PDF),
    DocumentFormat.DOC: (DocumentFamily.WORD, ContainerKind.OLE),
    DocumentFormat.DOCX: (DocumentFamily.WORD, ContainerKind.OPC),
    DocumentFormat.DOCM: (DocumentFamily.WORD, ContainerKind.OPC),
    DocumentFormat.DOT: (DocumentFamily.WORD, ContainerKind.OLE),
    DocumentFormat.DOTX: (DocumentFamily.WORD, ContainerKind.OPC),
    DocumentFormat.DOTM: (DocumentFamily.WORD, ContainerKind.OPC),
    DocumentFormat.XLS: (DocumentFamily.EXCEL, ContainerKind.OLE),
    DocumentFormat.XLSX: (DocumentFamily.EXCEL, ContainerKind.OPC),
    DocumentFormat.XLSM: (DocumentFamily.EXCEL, ContainerKind.OPC),
    DocumentFormat.XLSB: (DocumentFamily.EXCEL, ContainerKind.OPC),
    DocumentFormat.XLT: (DocumentFamily.EXCEL, ContainerKind.OLE),
    DocumentFormat.XLTX: (DocumentFamily.EXCEL, ContainerKind.OPC),
    DocumentFormat.XLTM: (DocumentFamily.EXCEL, ContainerKind.OPC),
}


def identify_declared_format(path: str | Path) -> FormatIdentity:
    """Resolve an approved suffix without claiming the container is genuine."""
    suffix = Path(path).suffix.casefold()
    try:
        document_format = DocumentFormat(suffix.removeprefix("."))
    except ValueError:
        raise UnsupportedDocumentFormatError from None

    family, container = _FORMAT_FACTS[document_format]
    return FormatIdentity(
        declared_format=document_format,
        family=family,
        expected_container=container,
    )


def identify_observed_container(header: bytes) -> ContainerKind | None:
    """Recognize a PDF, OLE or ZIP/OPC container from a bounded prefix."""
    if b"%PDF-" in header[:1024]:
        return ContainerKind.PDF
    if header.startswith(_OLE_MAGIC):
        return ContainerKind.OLE
    if header.startswith(_ZIP_MAGICS):
        return ContainerKind.OPC
    return None


def identify_format(path: str | Path, header: bytes) -> FormatIdentity:
    """Combine filename and magic evidence without allowing either to overwrite."""
    declared = identify_declared_format(path)
    observed = identify_observed_container(header)
    if observed is None:
        status = FormatIdentityStatus.UNKNOWN
    elif observed is declared.expected_container:
        status = FormatIdentityStatus.CONFIRMED
    else:
        status = FormatIdentityStatus.MISMATCH
    return FormatIdentity(
        declared_format=declared.declared_format,
        family=declared.family,
        expected_container=declared.expected_container,
        observed_container=observed,
        status=status,
    )
