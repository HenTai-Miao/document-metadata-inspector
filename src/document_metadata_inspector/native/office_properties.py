"""Convert native Office property structures into provenance-rich evidence."""

from __future__ import annotations

import codecs
from base64 import b64encode
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from math import isfinite
from re import fullmatch
from typing import TYPE_CHECKING, Final, Protocol, cast

from document_metadata_inspector.models import EvidenceObservation, JsonValue
from document_metadata_inspector.normalization import (
    normalize_evidence_value,
    normalize_identity_text,
)

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element

_CORE_NS: Final = (
    "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
)
_EXT_NS: Final = (
    "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
)
_CUSTOM_NS: Final = (
    "http://schemas.openxmlformats.org/officeDocument/2006/custom-properties"
)
_DC_NS: Final = "http://purl.org/dc/elements/1.1/"
_DCTERMS_NS: Final = "http://purl.org/dc/terms/"

_CORE_ROOT: Final = f"{{{_CORE_NS}}}coreProperties"
_APP_ROOT: Final = f"{{{_EXT_NS}}}Properties"
_CUSTOM_ROOT: Final = f"{{{_CUSTOM_NS}}}Properties"

_CORE_FIELDS: Final = {
    f"{{{_DC_NS}}}creator": "author",
    f"{{{_CORE_NS}}}lastModifiedBy": "last_modified_by",
    f"{{{_DC_NS}}}title": "title",
    f"{{{_DC_NS}}}subject": "subject",
    f"{{{_DC_NS}}}description": "description",
    f"{{{_CORE_NS}}}keywords": "keywords",
    f"{{{_CORE_NS}}}category": "category",
    f"{{{_CORE_NS}}}contentStatus": "content_status",
    f"{{{_DC_NS}}}identifier": "identifier",
    f"{{{_DC_NS}}}language": "language",
    f"{{{_CORE_NS}}}revision": "revision",
    f"{{{_CORE_NS}}}version": "version",
    f"{{{_DCTERMS_NS}}}created": "created_at",
    f"{{{_DCTERMS_NS}}}modified": "modified_at",
    f"{{{_CORE_NS}}}lastPrinted": "last_printed_at",
}
_APP_FIELDS: Final = {
    "Application": "application",
    "AppVersion": "application_version",
    "Company": "company",
    "Manager": "manager",
    "Template": "template",
    "TotalTime": "total_editing_minutes",
    "Pages": "page_count",
    "Words": "word_count",
    "Characters": "character_count",
    "CharactersWithSpaces": "character_count_with_spaces",
    "Lines": "line_count",
    "Paragraphs": "paragraph_count",
    "Slides": "slide_count",
    "Notes": "note_count",
    "HiddenSlides": "hidden_slide_count",
}
_INTEGER_APP_FIELDS: Final = frozenset(
    {
        "total_editing_minutes",
        "page_count",
        "word_count",
        "character_count",
        "character_count_with_spaces",
        "line_count",
        "paragraph_count",
        "slide_count",
        "note_count",
        "hidden_slide_count",
    }
)
_BYTE_EVIDENCE_BASE64_LIMIT: Final = 4096

_SUMMARY_FIELDS: Final = {
    2: "title",
    3: "subject",
    4: "author",
    5: "keywords",
    6: "description",
    7: "template",
    8: "last_modified_by",
    9: "revision",
    10: "total_editing_time_100ns",
    11: "last_printed_at",
    12: "created_at",
    13: "modified_at",
    14: "page_count",
    15: "word_count",
    16: "character_count",
    18: "application",
    19: "security_flags",
}
_DOCUMENT_SUMMARY_FIELDS: Final = {
    2: "category",
    3: "presentation_target",
    4: "byte_count",
    5: "line_count",
    6: "paragraph_count",
    7: "slide_count",
    8: "note_count",
    9: "hidden_slide_count",
    10: "multimedia_clip_count",
    11: "scale_crop",
    12: "heading_pairs",
    13: "titles_of_parts",
    14: "manager",
    15: "company",
    16: "links_dirty",
    17: "character_count_with_spaces",
    19: "shared_document",
    22: "hyperlinks_changed",
    23: "application_version",
    26: "content_type",
    27: "content_status",
    28: "language",
    29: "document_version",
}


class OpcPropertyReader(Protocol):
    """Provide bounded optional XML reads from an OPC package."""

    def has_part(self, name: str) -> bool:
        """Report whether the immutable package inventory contains a part."""
        ...

    def read_xml(self, name: str) -> Element:
        """Read and safely parse one budgeted XML part."""
        ...


@dataclass(frozen=True, slots=True)
class EvidenceSource:
    """Identify one native evidence carrier without repeating loose arguments."""

    kind: str
    location: str
    parser_name: str = "native-office"
    parser_version: str = "1"


def _local_name(tag: str) -> str:
    return tag.rpartition("}")[2] if "}" in tag else tag


def _decode_bytes(value: bytes, encoding: str | None = None) -> str:
    encodings: list[str] = []
    if value.startswith((b"\xff\xfe", b"\xfe\xff")):
        encodings.append("utf-16")
    if encoding is not None:
        encodings.append(encoding)
    encodings.extend(("utf-8", "gb18030"))
    for candidate in dict.fromkeys(encodings):
        try:
            return value.decode(candidate).rstrip("\x00")
        except UnicodeDecodeError:
            continue
    return value.decode("utf-8", errors="replace").rstrip("\x00")


def _uncertain_byte_evidence(
    value: bytes,
    decoded_text: str,
    encoding: str,
) -> dict[str, JsonValue]:
    encoded = value[:_BYTE_EVIDENCE_BASE64_LIMIT]
    return {
        "decoded_text": decoded_text,
        "encoding": encoding,
        "decoding_status": "uncertain",
        "byte_length": len(value),
        "sha256": sha256(value).hexdigest(),
        "bytes_base64": b64encode(encoded).decode("ascii"),
        "base64_complete": len(encoded) == len(value),
    }


def _decode_ole_bytes(
    value: bytes,
    encoding: str | None,
) -> tuple[JsonValue, tuple[str, ...]]:
    if value.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return value.decode("utf-16").rstrip("\x00"), ()
        except UnicodeDecodeError:
            pass
    if encoding is not None:
        try:
            return value.decode(encoding).rstrip("\x00"), ()
        except UnicodeDecodeError:
            pass
    for candidate in ("utf-8", "gb18030"):
        try:
            decoded = value.decode(candidate).rstrip("\x00")
        except UnicodeDecodeError:
            continue
        return (
            _uncertain_byte_evidence(value, decoded, candidate),
            ("ole_string_decode_uncertain",),
        )
    decoded = value.decode("utf-8", errors="replace").rstrip("\x00")
    return (
        _uncertain_byte_evidence(value, decoded, "utf-8-replacement"),
        ("ole_string_decode_uncertain",),
    )


def json_value(value: object, *, byte_encoding: str | None = None) -> JsonValue:
    """Convert parser-native scalars and sequences to stable JSON values."""
    if value is None or isinstance(value, (str, bool, int)):
        result: JsonValue = value
    elif isinstance(value, float):
        result = value if isfinite(value) else str(value)
    elif isinstance(value, bytes):
        result = _decode_bytes(value, byte_encoding)
    elif isinstance(value, datetime):
        result = value.isoformat()
    elif isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        result = {
            str(key): json_value(item, byte_encoding=byte_encoding)
            for key, item in mapping.items()
        }
    elif isinstance(value, (list, tuple)):
        sequence = cast("list[object] | tuple[object, ...]", value)
        result = tuple(
            json_value(item, byte_encoding=byte_encoding) for item in sequence
        )
    else:
        result = str(value)
    return result


def make_observation(  # noqa: PLR0913
    canonical_name: str,
    raw_name: str,
    raw_value: object,
    *,
    value_type: str,
    source: EvidenceSource,
    warnings: tuple[str, ...] = (),
) -> EvidenceObservation:
    """Build one native-parser observation with conservative normalization."""
    raw = json_value(raw_value)
    return EvidenceObservation(
        canonical_name=canonical_name,
        raw_name=raw_name,
        raw_value=raw,
        normalized_value=normalize_evidence_value(canonical_name, raw),
        value_type=value_type,
        source_kind=source.kind,
        location=source.location,
        parser_name=source.parser_name,
        parser_version=source.parser_version,
        warnings=warnings,
    )


def _xml_value(element: Element) -> str | tuple[str, ...]:
    if len(element) == 0:
        return element.text or ""
    return tuple(text for text in element.itertext() if text.strip())


def _parse_integer(raw: str) -> int | str:
    stripped = raw.strip()
    if fullmatch(r"[+-]?[0-9]+", stripped) is None:
        return raw
    try:
        return int(stripped)
    except ValueError:
        return raw


def _parse_custom_scalar(value_type: str, raw: str) -> object:
    if value_type in {
        "i1",
        "i2",
        "i4",
        "i8",
        "int",
        "ui1",
        "ui2",
        "ui4",
        "ui8",
        "uint",
    }:
        return _parse_integer(raw)
    if value_type == "bool":
        return {"true": True, "1": True, "false": False, "0": False}.get(
            raw.strip().casefold(),
            raw,
        )
    if value_type in {"r4", "r8"}:
        try:
            number = float(raw.strip())
        except ValueError:
            return raw
        return number if isfinite(number) else raw
    if value_type == "empty" and not raw.strip():
        return None
    return raw


def _read_core_properties(
    reader: OpcPropertyReader,
) -> tuple[list[EvidenceObservation], list[str]]:
    observations: list[EvidenceObservation] = []
    warnings: list[str] = []
    core_name = "docProps/core.xml"
    if not reader.has_part(core_name):
        return observations, warnings
    core = reader.read_xml(core_name)
    if core.tag != _CORE_ROOT:
        warnings.append("opc_core_properties_invalid")
        return observations, warnings
    source = EvidenceSource("opc_core_properties", core_name)
    for child in core:
        local = _local_name(child.tag)
        canonical = _CORE_FIELDS.get(
            child.tag,
            f"core_property.{local.casefold()}",
        )
        observations.append(
            make_observation(
                canonical,
                local,
                _xml_value(child),
                value_type="xml_text",
                source=source,
            )
        )
    return observations, warnings


def _read_extended_properties(
    reader: OpcPropertyReader,
) -> tuple[list[EvidenceObservation], list[str]]:
    observations: list[EvidenceObservation] = []
    warnings: list[str] = []
    app_name = "docProps/app.xml"
    if not reader.has_part(app_name):
        return observations, warnings
    app = reader.read_xml(app_name)
    if app.tag != _APP_ROOT:
        warnings.append("opc_extended_properties_invalid")
        return observations, warnings
    source = EvidenceSource("opc_extended_properties", app_name)
    for child in app:
        local = _local_name(child.tag)
        canonical = _APP_FIELDS.get(
            local,
            f"extended_property.{local.casefold()}",
        )
        raw_value = _xml_value(child)
        if canonical in _INTEGER_APP_FIELDS and isinstance(raw_value, str):
            raw_value = _parse_integer(raw_value)
        observations.append(
            make_observation(
                canonical,
                local,
                raw_value,
                value_type="xml_value",
                source=source,
            )
        )
    return observations, warnings


def _read_custom_properties(
    reader: OpcPropertyReader,
) -> tuple[list[EvidenceObservation], list[str]]:
    observations: list[EvidenceObservation] = []
    warnings: list[str] = []
    custom_name = "docProps/custom.xml"
    if not reader.has_part(custom_name):
        return observations, warnings
    custom = reader.read_xml(custom_name)
    if custom.tag != _CUSTOM_ROOT:
        warnings.append("opc_custom_properties_invalid")
        return observations, warnings
    source = EvidenceSource("opc_custom_properties", custom_name)
    for prop in custom:
        name = prop.get("name")
        if _local_name(prop.tag) != "property" or not name or len(prop) != 1:
            warnings.append("opc_custom_property_malformed")
            continue
        value_element = prop[0]
        value_type = _local_name(value_element.tag)
        raw_text = "".join(value_element.itertext())
        observations.append(
            make_observation(
                f"custom_property.{normalize_identity_text(name)}",
                name,
                _parse_custom_scalar(value_type, raw_text),
                value_type=value_type,
                source=source,
            )
        )
    return observations, warnings


def read_opc_properties(
    reader: OpcPropertyReader,
) -> tuple[tuple[EvidenceObservation, ...], tuple[str, ...]]:
    """Enumerate standard, extended and custom OPC properties when present."""
    observations: list[EvidenceObservation] = []
    warnings: list[str] = []
    for parser in (
        _read_core_properties,
        _read_extended_properties,
        _read_custom_properties,
    ):
        parsed, parser_warnings = parser(reader)
        observations.extend(parsed)
        warnings.extend(parser_warnings)
    return tuple(observations), tuple(sorted(set(warnings)))


def read_ole_property_set(
    properties: Mapping[int, object],
    *,
    location: str,
    document_summary: bool,
) -> tuple[EvidenceObservation, ...]:
    """Preserve every value returned from one OLE property-set section."""
    fields = _DOCUMENT_SUMMARY_FIELDS if document_summary else _SUMMARY_FIELDS
    observations: list[EvidenceObservation] = []
    source = EvidenceSource("ole_property_set", location)
    byte_encoding = _ole_codepage_encoding(properties.get(1))
    for property_id, value in sorted(properties.items()):
        if value is None:
            continue
        canonical = fields.get(property_id, f"ole_property.{property_id}")
        if isinstance(value, bytes):
            decoded_value, decode_warnings = _decode_ole_bytes(value, byte_encoding)
        else:
            decoded_value = json_value(value, byte_encoding=byte_encoding)
            decode_warnings = ()
        observations.append(
            make_observation(
                canonical,
                f"property:{property_id}",
                decoded_value,
                value_type=type(value).__name__,
                source=source,
                warnings=decode_warnings,
            )
        )
    return tuple(observations)


def _ole_codepage_encoding(value: object) -> str | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    codepage = value & 0xFFFF
    aliases = {
        1200: "utf-16-le",
        1201: "utf-16-be",
        10000: "mac-roman",
        10008: "gb18030",
        54936: "gb18030",
        65000: "utf-7",
        65001: "utf-8",
    }
    candidate = aliases.get(codepage, f"cp{codepage}")
    try:
        return codecs.lookup(candidate).name
    except LookupError:
        return None
