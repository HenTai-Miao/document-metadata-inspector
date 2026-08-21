"""Read-only, non-executing PDF metadata and forensic structure adapter."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from hashlib import sha256
from json import dumps
from typing import TYPE_CHECKING, Final, Protocol, cast
from xml.etree.ElementTree import ParseError

import pypdf
from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring
from pypdf import PasswordType, PdfReader
from pypdf.errors import (
    FileNotDecryptedError,
    LimitReachedError,
    PdfReadError,
    PyPdfError,
    WrongPasswordError,
    XmpDocumentError,
)
from pypdf.generic import (
    ArrayObject,
    ByteStringObject,
    IndirectObject,
    StreamObject,
)

from document_metadata_inspector.errors import ErrorCode, InspectionError
from document_metadata_inspector.formats import (
    ContainerKind,
    FormatIdentityStatus,
)
from document_metadata_inspector.models import (
    ParserRun,
    ParserStatus,
)
from document_metadata_inspector.native.office_properties import (
    EvidenceSource,
    json_value,
)
from document_metadata_inspector.native.office_properties import (
    make_observation as _make_observation,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from document_metadata_inspector.formats import FormatIdentity
    from document_metadata_inspector.models import EvidenceObservation
    from document_metadata_inspector.source import SourceSnapshot

type PasswordProvider = Callable[[str], str | None]

_PARSER_NAME: Final = "native-pdf"
_INFO_FIELDS: Final = {
    "/Title": "title",
    "/Author": "author",
    "/Subject": "subject",
    "/Keywords": "keywords",
    "/Creator": "creator_application",
    "/Producer": "producer_application",
    "/CreationDate": "created_at",
    "/ModDate": "modified_at",
    "/Trapped": "trapped",
}
_XMP_FIELDS: Final = {
    "creator": "author",
    "title": "title",
    "description": "description",
    "subject": "keywords",
    "creatortool": "creator_application",
    "producer": "producer_application",
    "createdate": "created_at",
    "modifydate": "modified_at",
    "metadatadate": "metadata_modified_at",
    "nickname": "xmp_nickname",
    "label": "xmp_label",
    "rating": "xmp_rating",
}
_RDF_ABOUT: Final = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about"
_STRUCTURAL_XMP_TAGS: Final = frozenset(
    {"xmpmeta", "RDF", "Description", "Seq", "Bag", "Alt", "li"}
)
_SCAN_CHUNK_BYTES: Final = 1024 * 1024
_SIGNATURE_BYTE_RANGE_LENGTH: Final = 4


def make_observation(
    canonical_name: str,
    raw_name: str,
    raw_value: object,
    *,
    value_type: str,
    source: EvidenceSource,
) -> EvidenceObservation:
    """Create PDF evidence with the actual native-PDF parser provenance."""
    pdf_source = EvidenceSource(
        kind=source.kind,
        location=source.location,
        parser_name=_PARSER_NAME,
        parser_version=pypdf.__version__,
    )
    return _make_observation(
        canonical_name,
        raw_name,
        raw_value,
        value_type=value_type,
        source=pdf_source,
    )


def _error(code: ErrorCode, message: str, source: str | None = None) -> InspectionError:
    return InspectionError(
        code=code,
        message=message,
        source=source,
        stage="native_pdf",
    )


def _failure(error: InspectionError) -> ParserRun:
    return ParserRun(
        parser_name=_PARSER_NAME,
        parser_version=pypdf.__version__,
        status=ParserStatus.FAILED,
        error_code=error.code.value,
        warnings=(error.message,),
    )


def _resolve(value: object) -> object:
    resolved = value
    for _ in range(8):
        if not isinstance(resolved, IndirectObject):
            break
        dynamic = cast("object", resolved.get_object())
        resolved = dynamic
    return resolved


def _mapping(value: object) -> Mapping[object, object] | None:
    resolved = _resolve(value)
    if isinstance(resolved, Mapping):
        return cast("Mapping[object, object]", resolved)
    return None


def _sequence(value: object) -> Sequence[object] | None:
    resolved = _resolve(value)
    if isinstance(resolved, (ArrayObject, list, tuple)):
        return cast("Sequence[object]", resolved)
    return None


def _get(mapping: Mapping[object, object], key: str) -> object | None:
    value = mapping.get(key)
    return None if value is None else _resolve(value)


def _text(value: object | None) -> str | None:
    resolved = _resolve(value) if value is not None else None
    if resolved is None:
        return None
    if isinstance(resolved, bytes):
        return resolved.decode("utf-8", errors="replace")
    return str(resolved)


def _content_digest(value: object) -> tuple[str, int]:
    converted = json_value(_resolve(value))
    serialized = dumps(
        converted,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return sha256(serialized).hexdigest(), len(serialized)


def _read_info(reader: PdfReader) -> tuple[EvidenceObservation, ...]:
    dynamic = cast("object", reader.metadata)
    metadata = _mapping(dynamic)
    if metadata is None:
        return ()
    source = EvidenceSource("pdf_info", "trailer/Info")
    observations: list[EvidenceObservation] = []
    ordered = sorted(metadata.items(), key=lambda item: str(item[0]))
    for raw_key, raw_value in ordered:
        key = str(raw_key)
        canonical = _INFO_FIELDS.get(
            key,
            f"pdf_info.{key.removeprefix('/').casefold()}",
        )
        observations.append(
            make_observation(
                canonical,
                key,
                _resolve(raw_value),
                value_type=type(_resolve(raw_value)).__name__,
                source=source,
            )
        )
    return tuple(observations)


def _stream_data_unfiltered(
    value: object,
    snapshot: SourceSnapshot,
) -> bytes | None:
    resolved = _resolve(value)
    if not isinstance(resolved, StreamObject) or resolved.get("/Filter") is not None:
        return None
    payload = resolved.get_data()
    return payload if len(payload) <= snapshot.limits.max_part_bytes else None


def _local_name(tag: str) -> str:
    return tag.rpartition("}")[2] if "}" in tag else tag


def _xmp_value(element: object) -> str | tuple[str, ...] | None:
    dynamic = element
    if not hasattr(dynamic, "itertext"):
        return None
    typed = cast("_XmlElement", dynamic)
    values = tuple(text for text in typed.itertext() if text.strip())
    if not values:
        return None
    return values[0] if len(values) == 1 else values


class _XmlElement(Protocol):
    """Local structural type boundary for defused ElementTree elements."""

    @property
    def tag(self) -> str:
        """Return the expanded XML element name."""
        ...

    @property
    def attrib(self) -> Mapping[str, str]:
        """Return the XML attribute mapping."""
        ...

    def iter(self) -> Iterator[_XmlElement]:
        """Iterate over this element and all descendants."""
        ...

    def itertext(self) -> Iterator[str]:
        """Iterate over text nodes below this element."""
        ...


def _read_xmp(
    reader: PdfReader,
    snapshot: SourceSnapshot,
) -> tuple[tuple[EvidenceObservation, ...], tuple[str, ...]]:
    root_mapping = _mapping(cast("object", reader.root_object))
    if root_mapping is None:
        return (), ()
    metadata = _get(root_mapping, "/Metadata")
    if metadata is None:
        return (), ()
    payload = _stream_data_unfiltered(metadata, snapshot)
    if payload is None:
        return (), ("pdf_xmp_compressed_or_oversized",)
    try:
        parsed = fromstring(
            payload,
            forbid_dtd=True,
            forbid_entities=True,
            forbid_external=True,
        )
    except (ParseError, DefusedXmlException) as error:
        raise _error(
            ErrorCode.CORRUPT_CONTAINER,
            "The PDF XMP metadata stream is malformed.",
            "Catalog/Metadata",
        ) from error

    source = EvidenceSource("pdf_xmp", "Catalog/Metadata")
    observations: list[EvidenceObservation] = []
    dynamic_root = cast("object", parsed)
    root = cast("_XmlElement", dynamic_root)
    for element in root.iter():
        for raw_name, raw_value in element.attrib.items():
            if raw_name == _RDF_ABOUT:
                continue
            local = _local_name(raw_name)
            canonical = _XMP_FIELDS.get(local.casefold(), f"xmp.{local.casefold()}")
            observations.append(
                make_observation(
                    canonical,
                    raw_name,
                    raw_value,
                    value_type="xmp_attribute",
                    source=source,
                )
            )
        local = _local_name(element.tag)
        folded = local.casefold()
        canonical = _XMP_FIELDS.get(folded)
        if canonical is None and local not in _STRUCTURAL_XMP_TAGS:
            canonical = f"xmp.{folded}"
        value = _xmp_value(element)
        if canonical is not None and value is not None:
            observations.append(
                make_observation(
                    canonical,
                    element.tag,
                    value,
                    value_type="xmp_element",
                    source=source,
                )
            )
    return tuple(observations), ()


def _read_trailer_and_catalog(reader: PdfReader) -> tuple[EvidenceObservation, ...]:
    observations: list[EvidenceObservation] = []
    trailer = _mapping(cast("object", reader.trailer))
    if trailer is not None:
        identifiers = _sequence(_get(trailer, "/ID"))
        if identifiers is not None:
            values = tuple(
                bytes(item).hex()
                if isinstance(item, (bytes, ByteStringObject))
                else str(item)
                for item in identifiers
            )
            observations.append(
                make_observation(
                    "pdf_trailer_id",
                    "/ID",
                    values,
                    value_type="byte_string_array",
                    source=EvidenceSource("pdf_trailer", "trailer"),
                )
            )

    catalog = _mapping(cast("object", reader.root_object))
    if catalog is None:
        return tuple(observations)
    source = EvidenceSource("pdf_catalog", "Catalog")
    for key, canonical in (
        ("/Lang", "language"),
        ("/PageLayout", "pdf_page_layout"),
        ("/PageMode", "pdf_page_mode"),
        ("/Version", "pdf_catalog_version"),
    ):
        value = _get(catalog, key)
        if value is not None:
            observations.append(
                make_observation(
                    canonical,
                    key,
                    value,
                    value_type=type(value).__name__,
                    source=source,
                )
            )
    for key, canonical in (
        ("/OpenAction", "pdf_open_action_present"),
        ("/AA", "pdf_additional_actions_present"),
    ):
        if _get(catalog, key) is not None:
            observations.append(
                make_observation(
                    canonical,
                    key,
                    raw_value=True,
                    value_type="boolean",
                    source=source,
                )
            )
    return tuple(observations)


def _read_encryption(reader: PdfReader) -> tuple[EvidenceObservation, ...]:
    source = EvidenceSource("pdf_encryption", "trailer/Encrypt")
    observations = [
        make_observation(
            "pdf_encrypted",
            "/Encrypt",
            raw_value=reader.is_encrypted,
            value_type="boolean",
            source=source,
        )
    ]
    if not reader.is_encrypted:
        return tuple(observations)
    trailer = _mapping(cast("object", reader.trailer))
    encryption = None if trailer is None else _mapping(_get(trailer, "/Encrypt"))
    if encryption is not None:
        for key, canonical in (
            ("/Filter", "pdf_encryption_filter"),
            ("/SubFilter", "pdf_encryption_subfilter"),
            ("/V", "pdf_encryption_algorithm_version"),
            ("/Length", "pdf_encryption_key_length"),
            ("/R", "pdf_encryption_revision"),
            ("/EncryptMetadata", "pdf_encrypts_metadata"),
        ):
            value = _get(encryption, key)
            if value is not None:
                observations.append(
                    make_observation(
                        canonical,
                        key,
                        value,
                        value_type=type(value).__name__,
                        source=source,
                    )
                )
    permissions = reader.user_access_permissions
    if permissions is not None:
        observations.append(
            make_observation(
                "pdf_permissions",
                "/P",
                int(permissions),
                value_type="integer_bitmask",
                source=source,
            )
        )
    integrity = reader.are_permissions_valid
    if integrity is not None:
        observations.append(
            make_observation(
                "pdf_permissions_integrity_valid",
                "/Perms",
                raw_value=integrity,
                value_type="boolean",
                source=source,
            )
        )
    return tuple(observations)


def _annotation_evidence(
    annotation: Mapping[object, object],
    source: EvidenceSource,
) -> tuple[EvidenceObservation, ...]:
    observations: list[EvidenceObservation] = []
    subtype = _text(_get(annotation, "/Subtype"))
    if subtype is not None:
        observations.append(
            make_observation(
                "annotation_subtype",
                "/Subtype",
                subtype,
                value_type="name",
                source=source,
            )
        )
    author = _text(_get(annotation, "/T"))
    if author is not None and subtype != "/Widget":
        observations.append(
            make_observation(
                "annotation_author",
                "/T",
                author,
                value_type="string",
                source=source,
            )
        )
    for key, canonical in (
        ("/M", "annotation_modified_at"),
        ("/CreationDate", "annotation_created_at"),
        ("/NM", "annotation_identifier"),
    ):
        value = _get(annotation, key)
        if value is not None:
            observations.append(
                make_observation(
                    canonical,
                    key,
                    value,
                    value_type=type(value).__name__,
                    source=source,
                )
            )
    contents = _get(annotation, "/Contents")
    if contents is not None:
        digest, length = _content_digest(contents)
        observations.extend(
            (
                make_observation(
                    "annotation_body_sha256",
                    "/Contents",
                    digest,
                    value_type="sha256",
                    source=source,
                ),
                make_observation(
                    "annotation_body_length",
                    "/Contents",
                    length,
                    value_type="integer",
                    source=source,
                ),
            )
        )
    return tuple(observations)


def _read_annotations(
    reader: PdfReader,
    snapshot: SourceSnapshot,
) -> tuple[EvidenceObservation, ...]:
    if len(reader.pages) > snapshot.limits.max_entries:
        raise _error(
            ErrorCode.RESOURCE_LIMIT_EXCEEDED,
            "The PDF contains too many pages.",
        )
    observations: list[EvidenceObservation] = []
    annotation_count = 0
    for page_index, page in enumerate(reader.pages, start=1):
        page_mapping = _mapping(cast("object", page))
        if page_mapping is None:
            continue
        annotations = _sequence(_get(page_mapping, "/Annots")) or ()
        for item_index, item in enumerate(annotations, start=1):
            annotation_count += 1
            if annotation_count > snapshot.limits.max_entries:
                raise _error(
                    ErrorCode.RESOURCE_LIMIT_EXCEEDED,
                    "The PDF contains too many annotations.",
                )
            annotation = _mapping(item)
            if annotation is None:
                continue
            location = f"page:{page_index}:annotation:{item_index}"
            source = EvidenceSource("pdf_annotation", location)
            observations.extend(_annotation_evidence(annotation, source))
    return tuple(observations)


def _byte_range(value: object | None) -> tuple[int, ...] | None:
    sequence = _sequence(value) if value is not None else None
    if sequence is None:
        return None
    integers: list[int] = []
    for item in sequence:
        resolved = _resolve(item)
        if not isinstance(resolved, int):
            return None
        integers.append(resolved)
    return tuple(integers)


def _read_signature(
    signature: Mapping[object, object],
    source: EvidenceSource,
    file_size: int,
) -> tuple[EvidenceObservation, ...]:
    observations = [
        make_observation(
            "digital_signature_present",
            "/FT",
            raw_value=True,
            value_type="boolean",
            source=source,
        ),
        make_observation(
            "signature_crypto_valid",
            "verification",
            raw_value=False,
            value_type="boolean",
            source=source,
        ),
    ]
    for key, canonical in (
        ("/Name", "signature_signer_name"),
        ("/M", "signature_time"),
        ("/Reason", "signature_reason"),
        ("/Location", "signature_location"),
        ("/ContactInfo", "signature_contact"),
        ("/Filter", "signature_filter"),
        ("/SubFilter", "signature_subfilter"),
    ):
        value = _get(signature, key)
        if value is not None:
            observations.append(
                make_observation(
                    canonical,
                    key,
                    value,
                    value_type=type(value).__name__,
                    source=source,
                )
            )
    ranges = _byte_range(_get(signature, "/ByteRange"))
    if ranges is not None:
        structurally_intact = (
            len(ranges) == _SIGNATURE_BYTE_RANGE_LENGTH
            and ranges[0] == 0
            and all(item >= 0 for item in ranges)
            and ranges[0] + ranges[1] <= ranges[2]
            and ranges[2] + ranges[3] <= file_size
        )
        observations.extend(
            (
                make_observation(
                    "signature_byte_range",
                    "/ByteRange",
                    ranges,
                    value_type="integer_array",
                    source=source,
                ),
                make_observation(
                    "signature_byte_range_intact",
                    "/ByteRange",
                    structurally_intact,
                    value_type="boolean",
                    source=source,
                ),
            )
        )
    contents = _get(signature, "/Contents")
    if contents is not None:
        digest, _ = _content_digest(contents)
        observations.append(
            make_observation(
                "signature_contents_sha256",
                "/Contents",
                digest,
                value_type="sha256",
                source=source,
            )
        )
    return tuple(observations)


def _read_forms(
    reader: PdfReader,
    snapshot: SourceSnapshot,
) -> tuple[EvidenceObservation, ...]:
    dynamic = cast("object", reader.get_fields())
    fields = _mapping(dynamic)
    if fields is None:
        return ()
    if len(fields) > snapshot.limits.max_entries:
        raise _error(
            ErrorCode.RESOURCE_LIMIT_EXCEEDED,
            "The PDF contains too many form fields.",
        )
    observations: list[EvidenceObservation] = []
    for raw_name, raw_field in sorted(fields.items(), key=lambda item: str(item[0])):
        name = str(raw_name)
        field = _mapping(raw_field)
        if field is None:
            continue
        source = EvidenceSource("pdf_acroform", f"AcroForm/Fields/{name}")
        observations.append(
            make_observation(
                "form_field_name",
                "/T",
                name,
                value_type="string",
                source=source,
            )
        )
        field_type = _text(_get(field, "/FT"))
        if field_type is not None:
            observations.append(
                make_observation(
                    "form_field_type",
                    "/FT",
                    field_type,
                    value_type="name",
                    source=source,
                )
            )
        value = _get(field, "/V")
        if field_type == "/Sig":
            signature = _mapping(value) if value is not None else None
            if signature is not None:
                observations.extend(
                    _read_signature(signature, source, snapshot.size_bytes)
                )
        elif value is not None:
            digest, length = _content_digest(value)
            observations.extend(
                (
                    make_observation(
                        "form_field_value_sha256",
                        "/V",
                        digest,
                        value_type="sha256",
                        source=source,
                    ),
                    make_observation(
                        "form_field_value_length",
                        "/V",
                        length,
                        value_type="integer",
                        source=source,
                    ),
                )
            )
    return tuple(observations)


def _read_attachments(reader: PdfReader) -> tuple[EvidenceObservation, ...]:
    observations: list[EvidenceObservation] = []
    for index, attachment in enumerate(reader.attachment_list, start=1):
        source = EvidenceSource("pdf_embedded_file", f"EmbeddedFiles/{index}")
        observations.append(
            make_observation(
                "embedded_file_name",
                "name",
                attachment.name,
                value_type="string",
                source=source,
            )
        )
        for raw_name, canonical, value in (
            (
                "alternative_name",
                "embedded_file_alternative_name",
                attachment.alternative_name,
            ),
            ("description", "embedded_file_description", attachment.description),
            ("subtype", "embedded_file_content_type", attachment.subtype),
            ("size", "embedded_file_declared_size", attachment.size),
            ("creation_date", "embedded_file_created_at", attachment.creation_date),
            (
                "modification_date",
                "embedded_file_modified_at",
                attachment.modification_date,
            ),
        ):
            if value is not None:
                observations.append(
                    make_observation(
                        canonical,
                        raw_name,
                        value,
                        value_type=type(value).__name__,
                        source=source,
                    )
                )
    return tuple(observations)


def _count_incremental_updates(snapshot: SourceSnapshot) -> EvidenceObservation:
    eof_count = 0
    previous = b""
    _ = snapshot.stream.seek(0)
    while chunk := snapshot.stream.read(_SCAN_CHUNK_BYTES):
        combined = previous + chunk
        eof_count += combined.count(b"%%EOF")
        previous = combined[-4:]
    _ = snapshot.stream.seek(0)
    return make_observation(
        "pdf_incremental_update_count",
        "%%EOF",
        max(0, eof_count - 1),
        value_type="integer",
        source=EvidenceSource("pdf_structure", "file"),
    )


def _open_reader(snapshot: SourceSnapshot) -> PdfReader:
    try:
        _ = snapshot.stream.seek(0)
        return PdfReader(
            snapshot.stream,
            strict=True,
            root_object_recovery_limit=snapshot.limits.max_entries,
        )
    except (PdfReadError, LimitReachedError, ValueError, OSError) as error:
        raise _error(
            ErrorCode.CORRUPT_CONTAINER,
            "The input is not a readable PDF object graph.",
            snapshot.name,
        ) from error


def _decrypt(
    reader: PdfReader,
    snapshot: SourceSnapshot,
    password_provider: PasswordProvider | None,
) -> None:
    if not reader.is_encrypted:
        return
    if password_provider is None:
        raise _error(
            ErrorCode.PASSWORD_REQUIRED,
            "The PDF requires a password.",
            snapshot.name,
        )
    password = password_provider(snapshot.name)
    if password is None:
        raise _error(
            ErrorCode.PASSWORD_REQUIRED,
            "The PDF requires a password.",
            snapshot.name,
        )
    try:
        result = reader.decrypt(password)
    except (WrongPasswordError, PdfReadError, ValueError) as error:
        raise _error(
            ErrorCode.WRONG_PASSWORD,
            "The PDF password is incorrect.",
            snapshot.name,
        ) from error
    finally:
        password = None
    if result is PasswordType.NOT_DECRYPTED:
        raise _error(
            ErrorCode.WRONG_PASSWORD,
            "The PDF password is incorrect.",
            snapshot.name,
        )


def extract_native_pdf(
    snapshot: SourceSnapshot,
    identity: FormatIdentity,
    password_provider: PasswordProvider | None = None,
) -> ParserRun:
    """Extract PDF metadata without executing actions or attachment content."""
    if (
        identity.expected_container is not ContainerKind.PDF
        or identity.status is not FormatIdentityStatus.CONFIRMED
    ):
        return _failure(
            _error(
                ErrorCode.FORMAT_MISMATCH,
                "The observed container does not match a declared PDF.",
                snapshot.name,
            )
        )
    try:
        reader = _open_reader(snapshot)
        _decrypt(reader, snapshot, password_provider)
        observations: list[EvidenceObservation] = []
        warnings: list[str] = []
        observations.extend(_read_info(reader))
        xmp, xmp_warnings = _read_xmp(reader, snapshot)
        observations.extend(xmp)
        warnings.extend(xmp_warnings)
        observations.extend(_read_trailer_and_catalog(reader))
        observations.extend(_read_encryption(reader))
        observations.extend(_read_annotations(reader, snapshot))
        observations.extend(_read_forms(reader, snapshot))
        observations.extend(_read_attachments(reader))
        observations.append(_count_incremental_updates(snapshot))
    except InspectionError as error:
        return _failure(error)
    except (
        FileNotDecryptedError,
        LimitReachedError,
        PdfReadError,
        PyPdfError,
        RecursionError,
        ValueError,
        XmpDocumentError,
    ):
        return _failure(
            _error(
                ErrorCode.CORRUPT_CONTAINER,
                "The PDF object graph could not be inspected safely.",
                snapshot.name,
            )
        )
    return ParserRun(
        parser_name=_PARSER_NAME,
        parser_version=pypdf.__version__,
        status=ParserStatus.PARTIAL if warnings else ParserStatus.SUCCEEDED,
        observations=tuple(observations),
        warnings=tuple(sorted(set(warnings))),
    )


__all__ = ("extract_native_pdf",)
