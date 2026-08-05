"""Bounded native inspection of Word and Excel OPC packages."""

from __future__ import annotations

import zlib
from dataclasses import dataclass
from hashlib import sha256
from lzma import LZMAError
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, final
from unicodedata import category
from urllib.parse import unquote, urlsplit
from xml.etree.ElementTree import Element, ParseError
from zipfile import BadZipFile, ZipFile, ZipInfo

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring

from document_metadata_inspector.errors import ErrorCode, InspectionError
from document_metadata_inspector.formats import (
    DocumentFamily,
    DocumentFormat,
)
from document_metadata_inspector.native.office_properties import (
    EvidenceSource,
    make_observation,
    read_opc_properties,
)
from document_metadata_inspector.native.opc_forensics import read_opc_forensics

if TYPE_CHECKING:
    from collections.abc import Mapping

    from document_metadata_inspector.formats import FormatIdentity
    from document_metadata_inspector.models import EvidenceObservation, InspectionLimits
    from document_metadata_inspector.source import SourceSnapshot

_CHUNK_BYTES: Final = 64 * 1024
_CONTENT_TYPES_PART: Final = "[Content_Types].xml"
_ROOT_RELS_PART: Final = "_rels/.rels"
_CONTENT_TYPES_NS: Final = (
    "http://schemas.openxmlformats.org/package/2006/content-types"
)
_REL_NS: Final = "http://schemas.openxmlformats.org/package/2006/relationships"
_STRICT_REL_NS: Final = "http://purl.oclc.org/ooxml/package/relationships"
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
_BRT_BEGIN_BOOK_PREFIX: Final = b"\x83\x01\x00"

_MAIN_CONTENT_TYPES: Final[dict[DocumentFormat, str]] = {
    DocumentFormat.DOCX: (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
    ),
    DocumentFormat.DOCM: "application/vnd.ms-word.document.macroEnabled.main+xml",
    DocumentFormat.DOTX: (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml"
    ),
    DocumentFormat.DOTM: (
        "application/vnd.ms-word.template.macroEnabledTemplate.main+xml"
    ),
    DocumentFormat.XLSX: (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
    ),
    DocumentFormat.XLSM: "application/vnd.ms-excel.sheet.macroEnabled.main+xml",
    DocumentFormat.XLSB: "application/vnd.ms-excel.sheet.binary.macroEnabled.main",
    DocumentFormat.XLTX: (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.template.main+xml"
    ),
    DocumentFormat.XLTM: "application/vnd.ms-excel.template.macroEnabled.main+xml",
}


def _error(code: ErrorCode, message: str, source: str | None = None) -> InspectionError:
    return InspectionError(
        code=code,
        message=message,
        source=source,
        stage="native_opc",
    )


def _bounded_unquote(value: str) -> str | None:
    decoded = value
    for _ in range(2):
        candidate = unquote(decoded)
        if candidate == decoded:
            return decoded
        decoded = candidate
    return decoded if unquote(decoded) == decoded else None


def _canonical_member(name: str) -> str | None:
    decoded = _bounded_unquote(name)
    if decoded is None:
        return None
    candidate = decoded.removesuffix("/")
    segments = candidate.split("/")
    has_drive = bool(segments and len(segments[0]) > 1 and segments[0][1] == ":")
    if (
        not candidate
        or decoded.startswith("/")
        or "\\" in decoded
        or has_drive
        or any(category(character) == "Cc" for character in decoded)
        or any(segment in {"", ".", ".."} for segment in segments)
    ):
        return None
    return candidate.casefold()


def _inventory(
    archive: ZipFile,
    limits: InspectionLimits,
) -> tuple[Mapping[str, ZipInfo], tuple[str, ...]]:
    infos = archive.infolist()
    if len(infos) > limits.max_entries:
        raise _error(
            ErrorCode.RESOURCE_LIMIT_EXCEEDED,
            "The OPC package contains too many entries.",
        )
    names = tuple(info.filename for info in infos)
    canonical = tuple(_canonical_member(name) for name in names)
    if (
        any(info.orig_filename != info.filename for info in infos)
        or any(name is None for name in canonical)
        or len(set(names)) != len(names)
        or len(set(canonical)) != len(canonical)
    ):
        raise _error(
            ErrorCode.UNSAFE_DOCUMENT,
            "The OPC package contains unsafe or ambiguous member names.",
        )
    if any(info.flag_bits & 1 for info in infos):
        raise _error(
            ErrorCode.ENCRYPTED_DOCUMENT,
            "The OPC package contains encrypted entries.",
        )
    return MappingProxyType({info.filename: info for info in infos}), tuple(
        sorted(names)
    )


@final
class _OpcReader:
    __slots__ = ("_archive", "_limits", "_parts", "_remaining", "names")

    def __init__(
        self,
        archive: ZipFile,
        parts: Mapping[str, ZipInfo],
        names: tuple[str, ...],
        limits: InspectionLimits,
    ) -> None:
        self._archive = archive
        self._parts = parts
        self.names = names
        self._limits = limits
        self._remaining = limits.max_total_read_bytes

    def has_part(self, name: str) -> bool:
        return name in self._parts

    def _info(self, name: str) -> ZipInfo:
        try:
            return self._parts[name]
        except KeyError as error:
            raise _error(
                ErrorCode.INVALID_DOCUMENT,
                "A required OPC package part is missing.",
                name,
            ) from error

    def read_bytes(self, name: str, *, max_bytes: int | None = None) -> bytes:
        info = self._info(name)
        required = (
            info.file_size if max_bytes is None else min(info.file_size, max_bytes)
        )
        if required > self._limits.max_part_bytes or required > self._remaining:
            raise _error(
                ErrorCode.RESOURCE_LIMIT_EXCEEDED,
                "An OPC package read exceeds the configured budget.",
                name,
            )
        payload = bytearray()
        try:
            with self._archive.open(info, "r") as stream:
                while len(payload) < required:
                    chunk = stream.read(min(_CHUNK_BYTES, required - len(payload)))
                    if not chunk:
                        break
                    self._remaining -= len(chunk)
                    payload.extend(chunk)
        except (BadZipFile, LZMAError, UnicodeDecodeError, zlib.error) as error:
            raise _error(
                ErrorCode.CORRUPT_CONTAINER,
                "An OPC package part is corrupt.",
                name,
            ) from error
        except (NotImplementedError, RuntimeError) as error:
            raise _error(
                ErrorCode.CORRUPT_CONTAINER,
                "An OPC package part cannot be decoded.",
                name,
            ) from error
        except OSError as error:
            raise _error(
                ErrorCode.INVALID_DOCUMENT,
                "An OPC package part could not be read.",
                name,
            ) from error
        if len(payload) != required:
            raise _error(
                ErrorCode.CORRUPT_CONTAINER,
                "An OPC package part ended unexpectedly.",
                name,
            )
        return bytes(payload)

    def read_xml(self, name: str) -> Element:
        payload = self.read_bytes(name)
        try:
            return fromstring(
                payload,
                forbid_dtd=True,
                forbid_entities=True,
                forbid_external=True,
            )
        except (ParseError, DefusedXmlException) as error:
            raise _error(
                ErrorCode.CORRUPT_CONTAINER,
                "An OPC XML part is malformed.",
                name,
            ) from error

    def part_size(self, name: str) -> int:
        return self._info(name).file_size

    def hash_part(self, name: str) -> str:
        info = self._info(name)
        required = info.file_size
        if required > self._limits.max_part_bytes or required > self._remaining:
            raise _error(
                ErrorCode.RESOURCE_LIMIT_EXCEEDED,
                "An OPC package hash exceeds the configured budget.",
                name,
            )
        digest = sha256()
        consumed = 0
        try:
            with self._archive.open(info, "r") as stream:
                while chunk := stream.read(_CHUNK_BYTES):
                    consumed += len(chunk)
                    self._remaining -= len(chunk)
                    digest.update(chunk)
        except (BadZipFile, LZMAError, zlib.error) as error:
            raise _error(
                ErrorCode.CORRUPT_CONTAINER,
                "An OPC package part is corrupt.",
                name,
            ) from error
        except (NotImplementedError, RuntimeError) as error:
            raise _error(
                ErrorCode.CORRUPT_CONTAINER,
                "An OPC package part cannot be decoded.",
                name,
            ) from error
        except OSError as error:
            raise _error(
                ErrorCode.INVALID_DOCUMENT,
                "An OPC package part could not be read.",
                name,
            ) from error
        if consumed != required:
            raise _error(
                ErrorCode.CORRUPT_CONTAINER,
                "An OPC package part ended unexpectedly.",
                name,
            )
        return digest.hexdigest()


def _safe_internal_target(raw_target: str) -> str | None:
    try:
        split = urlsplit(raw_target)
    except ValueError:
        return None
    if split.scheme or split.netloc or split.query or split.fragment:
        return None
    decoded = _bounded_unquote(split.path)
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


def _main_target(reader: _OpcReader) -> str:
    relationships = reader.read_xml(_ROOT_RELS_PART)
    if relationships.tag not in _REL_ROOTS:
        raise _error(
            ErrorCode.INVALID_DOCUMENT,
            "The root relationships part has an invalid root.",
            _ROOT_RELS_PART,
        )
    candidates = tuple(
        element
        for element in relationships
        if element.tag in _REL_ITEMS and element.get("Type") in _OFFICE_REL_TYPES
    )
    if len(candidates) != 1:
        raise _error(
            ErrorCode.INVALID_DOCUMENT,
            "The package must identify exactly one main Office document.",
            _ROOT_RELS_PART,
        )
    relationship = candidates[0]
    raw_target = relationship.get("Target")
    if raw_target is None or relationship.get("TargetMode") not in {None, "Internal"}:
        raise _error(
            ErrorCode.UNSAFE_DOCUMENT,
            "The main Office document target is not internal.",
            _ROOT_RELS_PART,
        )
    target = _safe_internal_target(raw_target)
    if target is None or not reader.has_part(target):
        raise _error(
            ErrorCode.INVALID_DOCUMENT,
            "The main Office document target is invalid or missing.",
            _ROOT_RELS_PART,
        )
    return target


@dataclass(frozen=True, slots=True)
class _ContentTypes:
    overrides: Mapping[str, str]
    defaults: Mapping[str, str]

    def for_part(self, name: str) -> str | None:
        override = self.overrides.get(f"/{name}")
        if override is not None:
            return override
        extension = name.rpartition(".")[2].casefold()
        return self.defaults.get(extension)


def _read_content_types(reader: _OpcReader) -> _ContentTypes:
    content_types = reader.read_xml(_CONTENT_TYPES_PART)
    expected_root = f"{{{_CONTENT_TYPES_NS}}}Types"
    if content_types.tag != expected_root:
        raise _error(
            ErrorCode.INVALID_DOCUMENT,
            "The content-types part has an invalid root.",
            _CONTENT_TYPES_PART,
        )
    overrides: dict[str, str] = {}
    defaults: dict[str, str] = {}
    override_tag = f"{{{_CONTENT_TYPES_NS}}}Override"
    default_tag = f"{{{_CONTENT_TYPES_NS}}}Default"
    for item in content_types:
        if item.tag == override_tag:
            key = item.get("PartName")
            value = item.get("ContentType")
            destination = overrides
        elif item.tag == default_tag:
            key = (item.get("Extension") or "").casefold()
            value = item.get("ContentType")
            destination = defaults
        else:
            continue
        if not key or not value or key in destination:
            raise _error(
                ErrorCode.INVALID_DOCUMENT,
                "The content-types part contains an invalid declaration.",
                _CONTENT_TYPES_PART,
            )
        destination[key] = value
    return _ContentTypes(
        overrides=MappingProxyType(overrides),
        defaults=MappingProxyType(defaults),
    )


def _validate_main_part(
    reader: _OpcReader,
    identity: FormatIdentity,
    content_types: _ContentTypes,
) -> None:
    expected_content_type = _MAIN_CONTENT_TYPES.get(identity.declared_format)
    if expected_content_type is None:
        raise _error(
            ErrorCode.FORMAT_MISMATCH,
            "The declared format does not use an OPC Office package.",
        )
    target = _main_target(reader)
    actual_content_type = content_types.for_part(target)
    if actual_content_type != expected_content_type:
        raise _error(
            ErrorCode.FORMAT_MISMATCH,
            "The OPC main content type does not match the declared format.",
            target,
        )
    if identity.declared_format is DocumentFormat.XLSB:
        if reader.read_bytes(target, max_bytes=len(_BRT_BEGIN_BOOK_PREFIX)) != (
            _BRT_BEGIN_BOOK_PREFIX
        ):
            raise _error(
                ErrorCode.INVALID_DOCUMENT,
                "The binary workbook main part has an invalid prefix.",
                target,
            )
        return

    main = reader.read_xml(target)
    local_root = main.tag.rpartition("}")[2]
    expected_root = "document" if identity.family is DocumentFamily.WORD else "workbook"
    if local_root != expected_root:
        raise _error(
            ErrorCode.FORMAT_MISMATCH,
            "The OPC main part has the wrong Office family root.",
            target,
        )


def _relationship_observations(
    reader: _OpcReader,
) -> tuple[tuple[EvidenceObservation, ...], tuple[str, ...]]:
    observations: list[EvidenceObservation] = []
    warnings: list[str] = []
    for name in reader.names:
        if not name.casefold().endswith(".rels"):
            continue
        try:
            root = reader.read_xml(name)
        except InspectionError:
            warnings.append("opc_relationship_part_unreadable")
            continue
        if root.tag not in _REL_ROOTS:
            warnings.append("opc_relationship_part_invalid")
            continue
        for relationship in root:
            if (
                relationship.tag not in _REL_ITEMS
                or relationship.get("TargetMode") != "External"
            ):
                continue
            target = relationship.get("Target") or ""
            observations.append(
                make_observation(
                    "external_relationship",
                    relationship.get("Type") or "relationship",
                    target,
                    value_type="uri",
                    source=EvidenceSource("opc_relationship", name),
                )
            )
    return tuple(observations), tuple(sorted(set(warnings)))


def _inventory_observations(
    reader: _OpcReader,
    content_types: _ContentTypes,
) -> tuple[EvidenceObservation, ...]:
    observations: list[EvidenceObservation] = []
    for name in reader.names:
        folded = name.casefold()
        canonical: str | None = None
        source_kind: str | None = None
        raw_value: object = name
        value_type = "part_name"
        if folded.endswith("vbaproject.bin") or "/activex/" in f"/{folded}":
            canonical = "active_content"
            source_kind = "opc_active_content"
        elif "/embeddings/" in f"/{folded}":
            canonical = "embedded_object"
            source_kind = "opc_embedding"
            raw_value = {
                "path": name,
                "content_type": content_types.for_part(name)
                or "application/octet-stream",
                "size_bytes": reader.part_size(name),
                "sha256": reader.hash_part(name),
            }
            value_type = "embedded_resource_descriptor"
        elif folded.startswith("_xmlsignatures/"):
            canonical = "digital_signature_part"
            source_kind = "opc_signature"
        if canonical is not None and source_kind is not None:
            observations.append(
                make_observation(
                    canonical,
                    "part_name",
                    raw_value,
                    value_type=value_type,
                    source=EvidenceSource(source_kind, name),
                )
            )
    return tuple(observations)


def extract_opc(
    snapshot: SourceSnapshot,
    identity: FormatIdentity,
) -> tuple[tuple[EvidenceObservation, ...], tuple[str, ...]]:
    """Validate and enumerate native evidence from one OPC Office package."""
    try:
        _ = snapshot.stream.seek(0)
        archive = ZipFile(snapshot.stream, "r")
    except (BadZipFile, UnicodeDecodeError, NotImplementedError) as error:
        raise _error(
            ErrorCode.CORRUPT_CONTAINER,
            "The input is not a readable OPC ZIP package.",
            snapshot.name,
        ) from error
    except OSError as error:
        raise _error(
            ErrorCode.INVALID_DOCUMENT,
            "The OPC package could not be opened.",
            snapshot.name,
        ) from error

    with archive:
        parts, names = _inventory(archive, snapshot.limits)
        reader = _OpcReader(archive, parts, names, snapshot.limits)
        content_types = _read_content_types(reader)
        _validate_main_part(reader, identity, content_types)
        property_observations, property_warnings = read_opc_properties(reader)
        relationship_observations, relationship_warnings = _relationship_observations(
            reader
        )
        forensic_observations, forensic_warnings = read_opc_forensics(
            reader,
            identity.family,
        )
        observations = (
            *property_observations,
            *relationship_observations,
            *forensic_observations,
            *_inventory_observations(reader, content_types),
        )
        warnings = tuple(
            sorted(set(property_warnings + relationship_warnings + forensic_warnings))
        )
        return observations, warnings
