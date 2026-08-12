"""Private incremental result bundle used by the desktop application."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Final, Literal, final

from document_metadata_inspector.exporters import write_atomic_output
from document_metadata_inspector.models import (
    DocumentReport,
    DocumentStatus,
    EvidenceObservation,
    FrozenModel,
    JsonValue,
    TraceKind,
    TraceMatch,
)

if TYPE_CHECKING:
    from pathlib import Path

_DOCUMENT_ID_PATTERN: Final = re.compile(r"[0-9a-f]{64}")
_KEY_FIELD_PATTERNS: Final[dict[str, tuple[str, ...]]] = {
    "author": ("author", "creator"),
    "created": ("creationdate", "created", "createdate", "createdat"),
    "modified": (
        "moddate",
        "modified",
        "modifydate",
        "modificationdate",
        "modifiedat",
    ),
    "last_modified_by": (
        "lastmodifiedby",
        "lastsavedby",
    ),
    "company": ("company",),
    "template": ("template",),
}


class DesktopBundleError(RuntimeError):
    """Report a sanitized private-bundle publication failure."""


class DesktopObservationSummary(FrozenModel):
    """Contain one presentation-ready metadata row."""

    label: str
    value: str


class DesktopKeyFields(FrozenModel):
    """Contain the small metadata projection shown on document cards."""

    author: str = ""
    created: str = ""
    modified: str = ""
    last_modified_by: str = ""
    company: str = ""
    template: str = ""


class DesktopParserRunSummary(FrozenModel):
    """Summarize one parser without retaining its observations."""

    name: str
    status: str
    warning_count: int


class DesktopDocumentSummary(FrozenModel):
    """Summarize one terminal document for initial desktop rendering."""

    source_path_sha256: str
    display_name: str
    declared_format: str
    family: str
    status: str
    observation_count: int
    parser_run_count: int
    warning_count: int
    size_bytes: int
    sha256_prefix: str
    parser_runs: tuple[DesktopParserRunSummary, ...]
    key_fields: DesktopKeyFields


class DesktopTraceSummary(FrozenModel):
    """Retain only fields needed to render an exact comparison trace."""

    canonical_name: str
    normalized_value: JsonValue
    trace_kind: TraceKind
    field_names: tuple[str, ...]
    raw_values: tuple[JsonValue, ...]
    evidence_count: int
    document_ids: tuple[str, ...]


class DesktopDocumentDetail(FrozenModel):
    """Contain lazily loaded, deduplicated presentation rows."""

    schema_version: Literal["1.0"] = "1.0"
    document_id: str
    observations: tuple[DesktopObservationSummary, ...]


class DesktopBundleSummary(FrozenModel):
    """Describe a complete private result bundle without full evidence."""

    schema_version: Literal["1.0"] = "1.0"
    document_count: int
    complete_document_count: int
    observation_count: int
    parser_run_count: int
    warning_count: int
    documents: tuple[DesktopDocumentSummary, ...]
    matches: tuple[DesktopTraceSummary, ...]
    warnings: tuple[str, ...] = ()


def _display_value(value: JsonValue, normalized: JsonValue) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        if isinstance(normalized, str):
            return normalized
        if normalized is None:
            return ""
        value = normalized
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _observation_label(observation: EvidenceObservation) -> str:
    return (
        observation.raw_name.strip() or observation.canonical_name.strip() or "未知字段"
    )


def _detail_observations(
    observations: tuple[EvidenceObservation, ...],
) -> tuple[DesktopObservationSummary, ...]:
    result: list[DesktopObservationSummary] = []
    seen: set[tuple[str, str]] = set()
    for observation in observations:
        label = _observation_label(observation)
        value = _display_value(
            observation.raw_value,
            observation.normalized_value,
        )
        key = (label, value)
        if not value or key in seen:
            continue
        seen.add(key)
        result.append(DesktopObservationSummary(label=label, value=value))
    return tuple(result)


def _normalized_field_name(observation: EvidenceObservation) -> str:
    source = observation.canonical_name or observation.raw_name
    return "".join(
        character
        for character in source.casefold()
        if character.isascii() and character.isalnum()
    )


def _key_fields(observations: tuple[EvidenceObservation, ...]) -> DesktopKeyFields:
    values: dict[str, str] = {}
    for observation in observations:
        key = _normalized_field_name(observation)
        if not key or key in values:
            continue
        value = _display_value(
            observation.raw_value,
            observation.normalized_value,
        )
        if value:
            values[key] = value

    projected: dict[str, str] = {}
    for field, patterns in _KEY_FIELD_PATTERNS.items():
        projected[field] = next(
            (values[pattern] for pattern in patterns if pattern in values),
            "",
        )
    return DesktopKeyFields.model_validate(projected)


def _warning_count(document: DocumentReport) -> int:
    return (
        len(document.warnings)
        + sum(len(run.warnings) for run in document.parser_runs)
        + sum(len(child.warnings) for child in document.embedded_documents)
    )


def _document_summary(
    document: DocumentReport,
    document_id: str,
) -> DesktopDocumentSummary:
    return DesktopDocumentSummary(
        source_path_sha256=document_id,
        display_name=document.display_name,
        declared_format=document.identity.declared_format.value,
        family=document.identity.family.value,
        status=document.status.value,
        observation_count=len(document.observations),
        parser_run_count=len(document.parser_runs),
        warning_count=_warning_count(document),
        size_bytes=document.size_bytes,
        sha256_prefix=document.sha256[:12],
        parser_runs=tuple(
            DesktopParserRunSummary(
                name=run.parser_name,
                status=run.status.value,
                warning_count=len(run.warnings),
            )
            for run in document.parser_runs
        ),
        key_fields=_key_fields(document.observations),
    )


def _trace_summary(match: TraceMatch) -> DesktopTraceSummary:
    return DesktopTraceSummary(
        canonical_name=match.canonical_name,
        normalized_value=match.normalized_value,
        trace_kind=match.trace_kind,
        field_names=match.field_names,
        raw_values=match.raw_values,
        evidence_count=match.evidence_count,
        document_ids=match.document_ids,
    )


def _write_model(path: Path, model: FrozenModel) -> None:
    _ = path.write_text(model.model_dump_json(indent=2), encoding="utf-8")


@final
class DesktopBundleWriter:
    """Publish terminal document evidence without retaining full batch reports."""

    def __init__(self, root: Path) -> None:
        """Create a fresh private root without replacing an existing entry."""
        self._root = root
        try:
            root.parent.mkdir(parents=True, exist_ok=True)
            root.mkdir(mode=0o700)
            self._details = root / "details"
            self._evidence = root / "evidence"
            self._details.mkdir(mode=0o700)
            self._evidence.mkdir(mode=0o700)
        except FileExistsError as error:
            msg = "desktop bundle result root already exists"
            raise DesktopBundleError(msg) from error
        except OSError as error:
            msg = "desktop bundle result root could not be created"
            raise DesktopBundleError(msg) from error
        self._documents: list[DesktopDocumentSummary] = []
        self._document_ids: set[str] = set()
        self._complete_document_count = 0
        self._observation_count = 0
        self._parser_run_count = 0

    def add(self, document: DocumentReport) -> None:
        """Atomically publish one terminal document's evidence and detail."""
        document_id = document.source_path_sha256
        if (
            document_id is None
            or _DOCUMENT_ID_PATTERN.fullmatch(document_id) is None
            or document_id in self._document_ids
        ):
            msg = "desktop bundle document identity is invalid"
            raise DesktopBundleError(msg)

        detail = DesktopDocumentDetail(
            document_id=document_id,
            observations=_detail_observations(document.observations),
        )
        try:
            _ = write_atomic_output(
                self._evidence / f"{document_id}.json",
                lambda path: _write_model(path, document),
            )
            _ = write_atomic_output(
                self._details / f"{document_id}.json",
                lambda path: _write_model(path, detail),
            )
        except (OSError, RuntimeError, ValueError) as error:
            msg = "desktop bundle document could not be published"
            raise DesktopBundleError(msg) from error

        summary = _document_summary(document, document_id)
        self._documents.append(summary)
        self._document_ids.add(document_id)
        self._complete_document_count += int(document.status is DocumentStatus.COMPLETE)
        self._observation_count += len(document.observations)
        self._parser_run_count += len(document.parser_runs)

    def finish(
        self,
        *,
        matches: tuple[TraceMatch, ...],
        warnings: tuple[str, ...] = (),
    ) -> DesktopBundleSummary:
        """Publish the compact summary last, marking the bundle complete."""
        document_warning_count = sum(
            document.warning_count for document in self._documents
        )
        summary = DesktopBundleSummary(
            document_count=len(self._documents),
            complete_document_count=self._complete_document_count,
            observation_count=self._observation_count,
            parser_run_count=self._parser_run_count,
            warning_count=document_warning_count + len(warnings),
            documents=tuple(self._documents),
            matches=tuple(_trace_summary(match) for match in matches),
            warnings=warnings,
        )
        try:
            _ = write_atomic_output(
                self._root / "summary.json",
                lambda path: _write_model(path, summary),
            )
        except (OSError, RuntimeError, ValueError) as error:
            msg = "desktop bundle summary could not be published"
            raise DesktopBundleError(msg) from error
        return summary


__all__ = (
    "DesktopBundleError",
    "DesktopBundleSummary",
    "DesktopBundleWriter",
    "DesktopDocumentDetail",
)
