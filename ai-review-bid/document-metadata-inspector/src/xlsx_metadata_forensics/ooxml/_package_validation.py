"""Central-directory and OOXML identity validation for Excel OPC packages."""

from typing import Final, Protocol
from urllib.parse import urlsplit
from xml.etree.ElementTree import Element

from xlsx_metadata_forensics.errors import ErrorCode, ExtractionError
from xlsx_metadata_forensics.formats import ExcelFormat
from xlsx_metadata_forensics.ooxml._opc_formats import (
    BRT_BEGIN_BOOK_PREFIX,
    OpcWorkbookIdentity,
    spec_for_content_type,
    spec_for_format,
)
from xlsx_metadata_forensics.ooxml._zip_inventory import bounded_unquote

_CONTENT_TYPES_PART: Final = "[Content_Types].xml"
_ROOT_RELS_PART: Final = "_rels/.rels"
_CONTENT_TYPES_NS: Final = (
    "http://schemas.openxmlformats.org/package/2006/content-types"
)
_REL_NS: Final = "http://schemas.openxmlformats.org/package/2006/relationships"
_STRICT_REL_NS: Final = "http://purl.oclc.org/ooxml/package/relationships"
_WORKBOOK_NS: Final = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_STRICT_WORKBOOK_NS: Final = "http://purl.oclc.org/ooxml/spreadsheetml/main"
_OFFICE_REL_TYPES: Final = frozenset(
    {
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument",
        "http://purl.oclc.org/ooxml/officeDocument/relationships/officeDocument",
    }
)
_REL_ROOTS: Final = frozenset(
    {f"{{{_REL_NS}}}Relationships", f"{{{_STRICT_REL_NS}}}Relationships"}
)
_REL_ITEMS: Final = frozenset(
    {f"{{{_REL_NS}}}Relationship", f"{{{_STRICT_REL_NS}}}Relationship"}
)
_WORKBOOK_ROOTS: Final = frozenset(
    {f"{{{_WORKBOOK_NS}}}workbook", f"{{{_STRICT_WORKBOOK_NS}}}workbook"}
)


class XmlReader(Protocol):
    """Provide budgeted required-XML reads to identity validation."""

    def has_part(self, name: str) -> bool: ...

    def read_prefix(self, name: str, length: int) -> bytes: ...

    def read_xml(self, name: str, failure_code: ErrorCode) -> Element: ...


def _failure(
    code: ErrorCode,
    message: str,
    source: str | None = None,
) -> ExtractionError:
    return ExtractionError(code, message, source)


def _internal_target(raw_target: str) -> str | None:
    try:
        split = urlsplit(raw_target)
    except ValueError:
        return None
    if split.scheme or split.netloc or split.query or split.fragment:
        return None
    decoded = bounded_unquote(split.path)
    if decoded is None:
        return None
    candidate = decoded.removeprefix("/")
    segments = candidate.split("/")
    if (
        not candidate
        or "\\" in decoded
        or any(segment in {"", ".", ".."} for segment in segments)
    ):
        return None
    return "/".join(segments)


def _workbook_target(relationships: Element) -> str:
    office_documents = tuple(
        item
        for item in relationships
        if item.tag in _REL_ITEMS and item.get("Type") in _OFFICE_REL_TYPES
    )
    if len(office_documents) != 1:
        raise _failure(
            ErrorCode.INVALID_XLSX,
            "Root relationships do not identify exactly one workbook.",
            _ROOT_RELS_PART,
        )
    relationship = office_documents[0]
    raw_target = relationship.get("Target")
    target_mode = relationship.get("TargetMode")
    target = None if raw_target is None else _internal_target(raw_target)
    if target is None or target_mode not in {None, "Internal"}:
        raise _failure(
            ErrorCode.INVALID_XLSX,
            "The workbook relationship target is not internal and safe.",
            _ROOT_RELS_PART,
        )
    return target


def _main_content_type(content_types: Element, target: str) -> str:
    overrides = tuple(
        item.get("ContentType")
        for item in content_types
        if item.tag == f"{{{_CONTENT_TYPES_NS}}}Override"
        and item.get("PartName") == f"/{target}"
    )
    if overrides:
        if len(overrides) != 1 or overrides[0] is None:
            raise _failure(
                ErrorCode.INVALID_XLSX,
                "The workbook target lacks one exact content-type declaration.",
                _CONTENT_TYPES_PART,
            )
        return overrides[0]

    filename = target.rpartition("/")[2]
    _, separator, extension = filename.rpartition(".")
    defaults = tuple(
        item.get("ContentType")
        for item in content_types
        if separator
        and item.tag == f"{{{_CONTENT_TYPES_NS}}}Default"
        and (item.get("Extension") or "").casefold() == extension.casefold()
    )
    if len(defaults) != 1 or defaults[0] is None:
        raise _failure(
            ErrorCode.INVALID_XLSX,
            "The workbook target lacks one exact content-type declaration.",
            _CONTENT_TYPES_PART,
        )
    return defaults[0]


def validate_excel_package(
    reader: XmlReader,
    expected_format: ExcelFormat,
) -> OpcWorkbookIdentity:
    """Validate one exact internal workbook for the selected OPC adapter."""
    expected_spec = spec_for_format(expected_format)
    if expected_spec is None:
        raise _failure(
            ErrorCode.UNSUPPORTED_FORMAT,
            "The selected Excel format does not use an OPC package.",
        )

    content_types = reader.read_xml(_CONTENT_TYPES_PART, ErrorCode.INVALID_EXCEL)
    if content_types.tag != f"{{{_CONTENT_TYPES_NS}}}Types":
        raise _failure(
            ErrorCode.INVALID_EXCEL,
            "The content-types part has an invalid root.",
            _CONTENT_TYPES_PART,
        )
    relationships = reader.read_xml(_ROOT_RELS_PART, ErrorCode.INVALID_EXCEL)
    if relationships.tag not in _REL_ROOTS:
        raise _failure(
            ErrorCode.INVALID_EXCEL,
            "The root-relationships part has an invalid root.",
            _ROOT_RELS_PART,
        )
    target = _workbook_target(relationships)
    if not reader.has_part(target):
        raise _failure(
            ErrorCode.INVALID_EXCEL,
            "A required package part is missing.",
            target,
        )
    content_type = _main_content_type(content_types, target)
    actual_spec = spec_for_content_type(content_type)
    if actual_spec is None or actual_spec.format is not expected_spec.format:
        raise _failure(
            ErrorCode.UNSUPPORTED_FORMAT,
            "The package main part does not match the selected Excel format.",
            target,
        )

    target_extension = target.rpartition(".")[2].casefold()
    if target_extension != actual_spec.target_extension:
        raise _failure(
            ErrorCode.INVALID_EXCEL,
            "The declared main part has an invalid format shape.",
            target,
        )

    if actual_spec.kind == "binary":
        if (
            reader.read_prefix(target, len(BRT_BEGIN_BOOK_PREFIX))
            != BRT_BEGIN_BOOK_PREFIX
        ):
            raise _failure(
                ErrorCode.INVALID_EXCEL,
                "The declared binary main part is not a genuine workbook root.",
                target,
            )
    else:
        workbook = reader.read_xml(target, ErrorCode.INVALID_EXCEL)
        if workbook.tag not in _WORKBOOK_ROOTS:
            raise _failure(
                ErrorCode.INVALID_EXCEL,
                "The declared main part is not a genuine workbook root.",
                target,
            )

    return OpcWorkbookIdentity(
        format=actual_spec.format,
        target=target,
        content_type=content_type,
        kind=actual_spec.kind,
    )


def validate_xlsx(reader: XmlReader) -> None:
    """Preserve the existing strict XLSX-only validation entry point."""
    _ = validate_excel_package(reader, ExcelFormat.XLSX)
