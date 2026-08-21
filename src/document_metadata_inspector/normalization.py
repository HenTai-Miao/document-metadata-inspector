"""Conservative normalization used for exact metadata-trace comparison."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from math import isfinite
from typing import TYPE_CHECKING, Final
from unicodedata import normalize

if TYPE_CHECKING:
    from document_metadata_inspector.models import JsonValue

_TIMESTAMP_FIELDS: Final = frozenset({"created_at", "modified_at", "last_printed_at"})
_TEXT_FIELDS: Final = frozenset(
    {
        "author",
        "last_modified_by",
        "annotation_author",
        "comment_author",
        "revision_author",
        "company",
        "manager",
        "application",
        "creator_application",
        "producer_application",
        "template",
        "signature_signer_name",
        "signer_identity",
        "username_path_trace",
        "identifier",
        "revision",
    }
)
_ISO_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})?\Z"
)
_EXIF_TIMESTAMP = re.compile(
    r"(?P<date>\d{4}:\d{2}:\d{2}) (?P<time>\d{2}:\d{2}:\d{2})(?P<fraction>\.\d{1,6})?(?P<zone>Z|[+-]\d{2}:\d{2})?\Z"  # noqa: E501
)
_NUMERIC_VERSION = re.compile(r"\d+(?:\.\d+)?\Z")
_PACKED_VERSION_MIN: Final = 0x10000


def normalize_identity_text(value: str) -> str:
    """Apply NFKC, whitespace collapse and case folding without fuzzy matching."""
    compatible = normalize("NFKC", value)
    collapsed = " ".join(compatible.split())
    return collapsed.casefold()


def _normalize_timestamp(value: str) -> str | None:
    candidate = value
    exif_match = _EXIF_TIMESTAMP.fullmatch(candidate)
    if exif_match is not None:
        date = exif_match.group("date").replace(":", "-")
        fraction = exif_match.group("fraction") or ""
        zone = exif_match.group("zone") or ""
        candidate = f"{date}T{exif_match.group('time')}{fraction}{zone}"
    elif _ISO_TIMESTAMP.fullmatch(candidate) is None:
        return None
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    return parsed.isoformat()


def _normalize_application_version(value: JsonValue) -> str | None:
    candidate: str | None = None
    if isinstance(value, bool):
        candidate = None
    elif isinstance(value, int):
        if value >= _PACKED_VERSION_MIN:
            major = value >> 16
            minor = value & 0xFFFF
            if major:
                candidate = str(major) if minor == 0 else f"{major}.{minor}"
        if candidate is None:
            candidate = str(value)
    elif isinstance(value, float):
        candidate = str(value) if isfinite(value) else None
    elif isinstance(value, str):
        candidate = normalize_identity_text(value)
    if candidate is None or _NUMERIC_VERSION.fullmatch(candidate) is None:
        return None
    try:
        decimal = Decimal(candidate)
    except InvalidOperation:
        return None
    normalized = format(decimal.normalize(), "f")
    return "0" if normalized == "-0" else normalized


def _normalize_scalar(canonical_name: str, value: JsonValue) -> JsonValue:
    if canonical_name == "application_version":
        normalized_version = _normalize_application_version(value)
        if normalized_version is not None:
            return normalized_version
    if isinstance(value, str):
        if canonical_name in _TIMESTAMP_FIELDS:
            normalized_timestamp = _normalize_timestamp(value)
            if normalized_timestamp is not None:
                return normalized_timestamp
        if canonical_name in _TEXT_FIELDS:
            return normalize_identity_text(value)
        return value
    if canonical_name in _TEXT_FIELDS and isinstance(value, (int, float)):
        return normalize_identity_text(str(value))
    return value


def normalize_evidence_value(canonical_name: str, value: JsonValue) -> JsonValue:
    """Normalize one value according to its evidence field without changing raw data."""
    if isinstance(value, tuple):
        result: JsonValue = tuple(
            normalize_evidence_value(canonical_name, item) for item in value
        )
    elif isinstance(value, dict):
        result = value
    else:
        result = _normalize_scalar(canonical_name, value)
    return result


__all__ = ("normalize_evidence_value", "normalize_identity_text")
