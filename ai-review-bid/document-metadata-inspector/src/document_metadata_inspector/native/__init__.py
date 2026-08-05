"""Native read-only Office metadata adapters."""

from __future__ import annotations

from hashlib import sha256
from typing import TYPE_CHECKING

from document_metadata_inspector.errors import ErrorCode, InspectionError
from document_metadata_inspector.formats import (
    ContainerKind,
    FormatIdentityStatus,
)
from document_metadata_inspector.models import (
    EmbeddedDocumentReport,
    EvidenceObservation,
    ParserRun,
    ParserStatus,
)
from document_metadata_inspector.native.ole import extract_ole
from document_metadata_inspector.native.opc import extract_opc

if TYPE_CHECKING:
    from collections.abc import Callable

    from document_metadata_inspector.formats import FormatIdentity
    from document_metadata_inspector.source import SourceSnapshot

    type PasswordProvider = Callable[[str], str | None]

_PARSER_NAME = "native-office"
_PARSER_VERSION = "1"


def _embedded_resource_id(parent_id: str, path: str, content_sha256: str) -> str:
    value = f"{parent_id}\0{path}\0{content_sha256}".encode()
    return sha256(value).hexdigest()


def _embedded_documents(
    root_sha256: str,
    observations: tuple[EvidenceObservation, ...],
) -> tuple[EmbeddedDocumentReport, ...]:
    children: list[EmbeddedDocumentReport] = []
    for observation in observations:
        raw = observation.raw_value
        if observation.canonical_name != "embedded_object" or not isinstance(raw, dict):
            continue
        path = raw.get("path")
        content_type = raw.get("content_type")
        size_bytes = raw.get("size_bytes")
        content_sha256 = raw.get("sha256")
        if (
            not isinstance(path, str)
            or not isinstance(content_type, str)
            or isinstance(size_bytes, bool)
            or not isinstance(size_bytes, int)
            or not isinstance(content_sha256, str)
        ):
            continue
        children.append(
            EmbeddedDocumentReport(
                resource_id=_embedded_resource_id(
                    root_sha256,
                    path,
                    content_sha256,
                ),
                parent_id=root_sha256,
                depth=1,
                path=path,
                content_type=content_type,
                size_bytes=size_bytes,
                sha256=content_sha256,
                parser_names=(_PARSER_NAME,),
            )
        )
    return tuple(
        sorted(children, key=lambda child: (child.path.casefold(), child.resource_id))
    )


def _failure(error: InspectionError) -> ParserRun:
    return ParserRun(
        parser_name=_PARSER_NAME,
        parser_version=_PARSER_VERSION,
        status=ParserStatus.FAILED,
        error_code=error.code.value,
        warnings=(error.message,),
    )


def extract_native_office(
    snapshot: SourceSnapshot,
    identity: FormatIdentity,
    password_provider: PasswordProvider | None = None,
) -> ParserRun:
    """Run the matching native Office adapter without leaking parser errors."""
    del password_provider
    if identity.status in {
        FormatIdentityStatus.MISMATCH,
        FormatIdentityStatus.UNKNOWN,
    }:
        return _failure(
            InspectionError(
                code=ErrorCode.FORMAT_MISMATCH,
                message="The observed container does not match the declared format.",
                source=snapshot.name,
                stage="native_office",
            )
        )
    if identity.expected_container not in {ContainerKind.OPC, ContainerKind.OLE}:
        return _failure(
            InspectionError(
                code=ErrorCode.FORMAT_MISMATCH,
                message="The declared format is not a supported Office container.",
                source=snapshot.name,
                stage="native_office",
            )
        )
    try:
        if identity.expected_container is ContainerKind.OPC:
            observations, warnings = extract_opc(snapshot, identity)
        else:
            observations, warnings = extract_ole(snapshot, identity)
    except InspectionError as error:
        return _failure(error)

    ordered = tuple(
        sorted(
            observations,
            key=lambda item: (
                item.location,
                item.canonical_name,
                item.raw_name,
                item.value_type,
            ),
        )
    )
    return ParserRun(
        parser_name=_PARSER_NAME,
        parser_version=_PARSER_VERSION,
        status=ParserStatus.PARTIAL if warnings else ParserStatus.SUCCEEDED,
        observations=ordered,
        warnings=warnings,
        embedded_documents=_embedded_documents(snapshot.sha256, ordered),
    )


__all__ = ("extract_native_office",)
