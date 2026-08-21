"""Immutable extraction request and report contracts."""

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict

from xlsx_metadata_forensics.formats import ExcelFormat

type JsonScalar = str | int | float | bool | None


class FrozenModel(BaseModel):
    """Base for immutable, closed JSON boundary contracts."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")


@dataclass(frozen=True, slots=True)
class ExtractionLimits:
    """Bound resource use while inspecting one XLSX package."""

    max_file_bytes: int = 100 * 1024 * 1024
    max_entries: int = 10_000
    max_xml_part_bytes: int = 16 * 1024 * 1024
    max_total_read_bytes: int = 256 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ExtractionRequest:
    """Identify one local XLSX and the limits applied to its extraction."""

    path: Path
    display_name: str
    limits: ExtractionLimits = ExtractionLimits()


class TimestampValue(FrozenModel):
    """Preserve an OOXML timestamp beside its normalized representation."""

    raw: str
    normalized: str


class FileInfo(FrozenModel):
    """Describe the inspected package itself."""

    name: str
    size_bytes: int
    sha256: str
    format: ExcelFormat = ExcelFormat.XLSX
    package_entry_count: int


class DocumentMetadata(FrozenModel):
    """Represent standard OOXML core and extended document properties."""

    author: str | None = None
    last_modified_by: str | None = None
    created_at: TimestampValue | None = None
    modified_at: TimestampValue | None = None
    last_printed_at: TimestampValue | None = None
    title: str | None = None
    subject: str | None = None
    description: str | None = None
    keywords: str | None = None
    category: str | None = None
    content_status: str | None = None
    identifier: str | None = None
    language: str | None = None
    revision: str | None = None
    version: str | None = None
    application: str | None = None
    application_version: str | None = None
    company: str | None = None
    manager: str | None = None
    template: str | None = None
    total_editing_minutes: int | None = None


class CustomProperty(FrozenModel):
    """Represent one typed OOXML custom property."""

    name: str
    value_type: str
    value: JsonScalar
    source: str


class CommentAuthor(FrozenModel):
    """Group comment authorship without retaining comment body text."""

    author: str
    sheet: str
    cells: tuple[str, ...]
    kind: str
    count: int
    source: str


class HiddenSheet(FrozenModel):
    """Record one hidden or very-hidden worksheet."""

    name: str
    state: str
    source: str


class ExternalLink(FrozenModel):
    """Record an external package relationship without dereferencing it."""

    target: str
    relationship_type: str
    source: str


class DataConnection(FrozenModel):
    """Record redacted external data-connection evidence."""

    name: str | None
    connection_type: str | None
    target: str | None
    source: str


class EmbeddedObject(FrozenModel):
    """Identify and fingerprint one embedded package object."""

    part_name: str
    display_name: str | None
    content_type: str | None
    size_bytes: int
    sha256: str
    source: str


class DigitalSignature(FrozenModel):
    """Describe certificate evidence without claiming signature validity."""

    source: str
    subject: str | None = None
    issuer: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    serial_number: str | None = None
    certificate_sha256: str | None = None
    cryptographically_verified: Literal[False] = False


class OfficeBuild(FrozenModel):
    """Record Office/WPS build and calculation-engine traces."""

    source: str
    application: str | None = None
    version: str | None = None
    build: str | None = None
    calculation_engine: str | None = None
    calculation_id: str | None = None


class ActiveContent(FrozenModel):
    """Identify inactive evidence of executable package content."""

    kind: str
    part_name: str
    content_type: str | None
    source: str


class PathTrace(FrozenModel):
    """Record a redacted local or external path trace."""

    value: str
    kind: str
    username: str | None
    source: str


class RevisionPart(FrozenModel):
    """Identify an OOXML revision part that actually exists."""

    part_name: str
    content_type: str | None
    source: str


class ForensicInfo(FrozenModel):
    """Collect every approved forensic evidence category."""

    custom_properties: tuple[CustomProperty, ...] = ()
    comment_authors: tuple[CommentAuthor, ...] = ()
    hidden_sheets: tuple[HiddenSheet, ...] = ()
    external_links: tuple[ExternalLink, ...] = ()
    data_connections: tuple[DataConnection, ...] = ()
    embedded_objects: tuple[EmbeddedObject, ...] = ()
    digital_signatures: tuple[DigitalSignature, ...] = ()
    office_build: OfficeBuild | None = None
    active_content: tuple[ActiveContent, ...] = ()
    path_traces: tuple[PathTrace, ...] = ()
    revision_parts: tuple[RevisionPart, ...] = ()


class ExtractionWarning(FrozenModel):
    """Describe one non-fatal extraction problem."""

    code: str
    message: str
    source: str | None = None


class ExtractionReport(FrozenModel):
    """Return the stable successful-extraction JSON contract."""

    success: Literal[True] = True
    schema_version: Literal["1.0"] = "1.0"
    file: FileInfo
    metadata: DocumentMetadata
    forensics: ForensicInfo
    warnings: tuple[ExtractionWarning, ...] = ()
