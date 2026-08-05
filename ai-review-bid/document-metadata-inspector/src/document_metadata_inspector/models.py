"""Immutable evidence, parser-run and aggregate report contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict

# Pydantic resolves this dataclass while building the runtime schema.
from document_metadata_inspector.formats import FormatIdentity  # noqa: TC001

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | tuple[JsonValue, ...] | dict[str, JsonValue]


class FrozenModel(BaseModel):
    """Base for immutable JSON boundaries that reject unknown fields."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")


@dataclass(frozen=True, slots=True)
class InspectionLimits:
    """Bound resource use for one untrusted document and its parser workers."""

    max_file_bytes: int = 256 * 1024 * 1024
    max_entries: int = 20_000
    max_part_bytes: int = 64 * 1024 * 1024
    max_total_read_bytes: int = 512 * 1024 * 1024
    parser_timeout_seconds: float = 30.0
    max_worker_output_bytes: int = 8 * 1024 * 1024
    max_worker_memory_bytes: int = 768 * 1024 * 1024
    max_embedded_depth: int = 8
    max_embedded_resources: int = 1_000
    max_embedded_total_bytes: int = 256 * 1024 * 1024

    def __post_init__(self) -> None:
        """Reject disabled or nonsensical safety budgets."""
        values = (
            self.max_file_bytes,
            self.max_entries,
            self.max_part_bytes,
            self.max_total_read_bytes,
            self.parser_timeout_seconds,
            self.max_worker_output_bytes,
            self.max_worker_memory_bytes,
            self.max_embedded_depth,
            self.max_embedded_resources,
            self.max_embedded_total_bytes,
        )
        if any(value <= 0 for value in values):
            msg = "inspection limits must all be positive"
            raise ValueError(msg)


class EvidenceStatus(StrEnum):
    """Describe how one value was observed or interpreted."""

    OBSERVED = "observed"
    CORROBORATED = "corroborated"
    CONFLICT = "conflict"
    UNKNOWN = "unknown"
    REDACTED = "redacted"


class ParserStatus(StrEnum):
    """Describe one isolated parser invocation."""

    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    SKIPPED = "skipped"


class DocumentStatus(StrEnum):
    """Summarize extraction coverage for one source document."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"
    ENCRYPTED_UNREADABLE = "encrypted_unreadable"


class EvidenceObservation(FrozenModel):
    """Preserve one raw parser value beside its conservative normalization."""

    canonical_name: str
    raw_name: str
    raw_value: JsonValue
    normalized_value: JsonValue
    value_type: str
    source_kind: str
    location: str
    parser_name: str
    parser_version: str
    status: EvidenceStatus = EvidenceStatus.OBSERVED
    warnings: tuple[str, ...] = ()


class EmbeddedDocumentReport(FrozenModel):
    """Identify one embedded document and keep its metadata in a child scope."""

    resource_id: str
    parent_id: str
    depth: int
    path: str
    content_type: str
    size_bytes: int
    sha256: str
    parser_names: tuple[str, ...] = ()
    observations: tuple[EvidenceObservation, ...] = ()
    warnings: tuple[str, ...] = ()


class ParserRun(FrozenModel):
    """Record the result and evidence of one versioned parser invocation."""

    parser_name: str
    parser_version: str
    status: ParserStatus
    observations: tuple[EvidenceObservation, ...] = ()
    warnings: tuple[str, ...] = ()
    error_code: str | None = None
    duration_ms: int | None = None
    embedded_documents: tuple[EmbeddedDocumentReport, ...] = ()


class DocumentReport(FrozenModel):
    """Aggregate all non-overwriting evidence for one immutable source snapshot."""

    display_name: str
    source_path_sha256: str | None = None
    size_bytes: int
    sha256: str
    identity: FormatIdentity
    status: DocumentStatus
    observations: tuple[EvidenceObservation, ...] = ()
    parser_runs: tuple[ParserRun, ...] = ()
    encrypted: bool = False
    password_required: bool = False
    warnings: tuple[str, ...] = ()
    embedded_documents: tuple[EmbeddedDocumentReport, ...] = ()


class ScanReport(FrozenModel):
    """Contain independent reports for a batch scan."""

    schema_version: Literal["1.0"] = "1.0"
    documents: tuple[DocumentReport, ...]
    warnings: tuple[str, ...] = ()


class TraceKind(StrEnum):
    """Classify exact traces without turning them into identity conclusions."""

    PERSON = "person_trace"
    ORGANIZATION = "organization_trace"
    SOFTWARE = "software_trace"
    DOCUMENT_ENVIRONMENT = "document_environment_trace"


class TraceEvidenceLink(FrozenModel):
    """Link one comparison match back to its raw parser evidence."""

    observation_id: str
    document_name: str
    canonical_name: str
    raw_value: JsonValue
    parser_name: str
    source_kind: str
    location: str
    document_id: str = ""


class TraceMatch(FrozenModel):
    """Group an exact normalized trace found across documents."""

    canonical_name: str
    normalized_value: JsonValue
    document_names: tuple[str, ...]
    evidence_count: int
    trace_kind: TraceKind = TraceKind.PERSON
    field_names: tuple[str, ...] = ()
    raw_values: tuple[JsonValue, ...] = ()
    evidence: tuple[TraceEvidenceLink, ...] = ()
    document_ids: tuple[str, ...] = ()


class ComparisonReport(FrozenModel):
    """Return document evidence and conservative cross-file trace matches."""

    schema_version: Literal["1.0"] = "1.0"
    documents: tuple[DocumentReport, ...]
    matches: tuple[TraceMatch, ...]
    warnings: tuple[str, ...] = ()
