"""Explainable exact matching for identity-related metadata traces."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import Final

from document_metadata_inspector.models import (
    ComparisonReport,
    DocumentReport,
    EvidenceObservation,
    FrozenModel,
    JsonValue,
    TraceEvidenceLink,
    TraceKind,
    TraceMatch,
)
from document_metadata_inspector.normalization import normalize_identity_text


class IdentityField(StrEnum):
    """Closed set of fields permitted to participate in trace comparison."""

    AUTHOR = "author"
    LAST_MODIFIED_BY = "last_modified_by"
    COMMENT_AUTHOR = "comment_author"
    REVISION_AUTHOR = "revision_author"
    COMPANY = "company"
    MANAGER = "manager"
    APPLICATION = "application"
    APPLICATION_VERSION = "application_version"
    TEMPLATE = "template"
    SIGNER_IDENTITY = "signer_identity"
    USERNAME_PATH_TRACE = "username_path_trace"


_FIELD_FACTS: Final[dict[str, tuple[IdentityField, TraceKind]]] = {
    "author": (IdentityField.AUTHOR, TraceKind.PERSON),
    "last_modified_by": (IdentityField.LAST_MODIFIED_BY, TraceKind.PERSON),
    "annotation_author": (IdentityField.COMMENT_AUTHOR, TraceKind.PERSON),
    "comment_author": (IdentityField.COMMENT_AUTHOR, TraceKind.PERSON),
    "revision_author": (IdentityField.REVISION_AUTHOR, TraceKind.PERSON),
    "company": (IdentityField.COMPANY, TraceKind.ORGANIZATION),
    "manager": (IdentityField.MANAGER, TraceKind.PERSON),
    "application": (IdentityField.APPLICATION, TraceKind.SOFTWARE),
    "creator_application": (IdentityField.APPLICATION, TraceKind.SOFTWARE),
    "producer_application": (IdentityField.APPLICATION, TraceKind.SOFTWARE),
    "application_version": (IdentityField.APPLICATION_VERSION, TraceKind.SOFTWARE),
    "template": (IdentityField.TEMPLATE, TraceKind.DOCUMENT_ENVIRONMENT),
    "signature_signer_name": (IdentityField.SIGNER_IDENTITY, TraceKind.PERSON),
    "signer_identity": (IdentityField.SIGNER_IDENTITY, TraceKind.PERSON),
    "username_path_trace": (IdentityField.USERNAME_PATH_TRACE, TraceKind.PERSON),
}
_MIN_DISTINCT_DOCUMENTS: Final = 2


class ComparisonRequest(FrozenModel):
    """Provide already-inspected documents for deterministic exact comparison."""

    documents: tuple[DocumentReport, ...]


@dataclass(frozen=True, slots=True)
class _Candidate:
    document_key: str
    document_name: str
    field: IdentityField
    trace_kind: TraceKind
    normalized_value: str
    raw_value: JsonValue
    observation: EvidenceObservation
    value_index: int


def _document_key(document: DocumentReport) -> str:
    return document.source_path_sha256 or f"{document.display_name}:{document.sha256}"


def _scalar_text(value: JsonValue) -> str | None:
    if isinstance(value, str):
        return normalize_identity_text(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return normalize_identity_text(str(value))
    return None


def _value_pairs(
    observation: EvidenceObservation,
) -> tuple[tuple[int, JsonValue, str], ...]:
    raw = observation.raw_value
    normalized = observation.normalized_value
    scalar = _scalar_text(normalized)
    if scalar is not None and not isinstance(raw, (tuple, dict)):
        return ((0, raw, scalar),)
    if isinstance(raw, tuple) and isinstance(normalized, tuple):
        pairs: list[tuple[int, JsonValue, str]] = []
        for index, (raw_item, normalized_item) in enumerate(
            zip(raw, normalized, strict=False)
        ):
            item_text = _scalar_text(normalized_item)
            if item_text is not None and not isinstance(raw_item, (tuple, dict)):
                pairs.append((index, raw_item, item_text))
        return tuple(pairs)
    return ()


def _candidates(document: DocumentReport) -> tuple[_Candidate, ...]:
    result: list[_Candidate] = []
    document_key = _document_key(document)
    for observation in document.observations:
        fact = _FIELD_FACTS.get(observation.canonical_name)
        if fact is None:
            continue
        field, trace_kind = fact
        for index, raw_value, normalized in _value_pairs(observation):
            if not normalized:
                continue
            result.append(
                _Candidate(
                    document_key=document_key,
                    document_name=document.display_name,
                    field=field,
                    trace_kind=trace_kind,
                    normalized_value=normalized,
                    raw_value=raw_value,
                    observation=observation,
                    value_index=index,
                )
            )
    return tuple(result)


def _candidate_key(candidate: _Candidate) -> tuple[str | int, ...]:
    return (
        candidate.document_name.casefold(),
        candidate.document_key,
        candidate.field.value,
        candidate.observation.parser_name,
        candidate.observation.source_kind,
        candidate.observation.location,
        candidate.observation.raw_name,
        json.dumps(
            candidate.raw_value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        candidate.value_index,
    )


def _observation_id(candidate: _Candidate) -> str:
    parts = (
        candidate.document_key,
        candidate.field.value,
        candidate.observation.raw_name,
        json.dumps(
            candidate.raw_value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        candidate.observation.parser_name,
        candidate.observation.parser_version,
        candidate.observation.source_kind,
        candidate.observation.location,
        str(candidate.value_index),
    )
    return sha256("\0".join(parts).encode("utf-8")).hexdigest()


def _group_name(fields: tuple[str, ...], trace_kind: TraceKind) -> str:
    if len(fields) == 1:
        return fields[0]
    if trace_kind is TraceKind.PERSON:
        return "person_identity_trace"
    if trace_kind is TraceKind.ORGANIZATION:
        return "organization_identity_trace"
    if trace_kind is TraceKind.SOFTWARE:
        return "software_identity_trace"
    return "document_environment_identity_trace"


def _match(group: list[_Candidate]) -> TraceMatch:
    ordered = sorted(group, key=_candidate_key)
    fields = tuple(sorted({candidate.field.value for candidate in ordered}))
    trace_kind = ordered[0].trace_kind
    evidence = tuple(
        TraceEvidenceLink(
            observation_id=_observation_id(candidate),
            document_name=candidate.document_name,
            canonical_name=candidate.field.value,
            raw_value=candidate.raw_value,
            parser_name=candidate.observation.parser_name,
            source_kind=candidate.observation.source_kind,
            location=candidate.observation.location,
            document_id=candidate.document_key,
        )
        for candidate in ordered
    )
    raw_values: tuple[JsonValue, ...] = tuple(
        candidate.raw_value for candidate in ordered
    )
    return TraceMatch(
        canonical_name=_group_name(fields, trace_kind),
        normalized_value=ordered[0].normalized_value,
        document_names=tuple(
            sorted({candidate.document_name for candidate in ordered})
        ),
        evidence_count=len(ordered),
        trace_kind=trace_kind,
        field_names=fields,
        raw_values=raw_values,
        evidence=evidence,
        document_ids=tuple(sorted({candidate.document_key for candidate in ordered})),
    )


def compare_documents(request: ComparisonRequest) -> ComparisonReport:
    """Return exact cross-file traces without fuzzy identity or collusion claims."""
    documents = tuple(
        sorted(
            request.documents,
            key=lambda item: (
                item.display_name.casefold(),
                _document_key(item),
            ),
        )
    )
    grouped: dict[tuple[TraceKind, str], list[_Candidate]] = defaultdict(list)
    for document in documents:
        for candidate in _candidates(document):
            key = (candidate.trace_kind, candidate.normalized_value)
            grouped[key].append(candidate)

    matches = [
        _match(group)
        for _, group in sorted(
            grouped.items(),
            key=lambda item: (item[0][0].value, item[0][1]),
        )
        if len({candidate.document_key for candidate in group})
        >= _MIN_DISTINCT_DOCUMENTS
    ]
    return ComparisonReport(documents=documents, matches=tuple(matches))


__all__ = ("ComparisonRequest", "IdentityField", "compare_documents")
