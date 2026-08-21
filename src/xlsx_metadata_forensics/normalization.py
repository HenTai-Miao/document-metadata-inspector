"""Normalize OOXML timestamps and redact sensitive custom-property values."""

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Final
from unicodedata import normalize

from xlsx_metadata_forensics.models import TimestampValue

_DATE_PATTERN: Final[re.Pattern[str]] = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_DATETIME_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"""
    [0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}
    (?:\.[0-9]{1,6})?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])?
    """,
    re.VERBOSE,
)
_NAME_TOKEN: Final[re.Pattern[str]] = re.compile(r"[a-z0-9]+")
_REDACTION_MARKER: Final = "***REDACTED***"
_CREDENTIAL_MARKERS: Final = frozenset(
    {
        "credential",
        "credentials",
        "key",
        "passphrase",
        "passwd",
        "password",
        "pwd",
        "secret",
        "token",
    }
)
_SENSITIVE_TOKENS: Final = _CREDENTIAL_MARKERS | frozenset(
    {
        "access",
        "api",
        "private",
    }
)
_CREDENTIAL_CONTEXTS: Final = frozenset(
    {
        "access",
        "admin",
        "api",
        "backup",
        "client",
        "database",
        "empty",
        "login",
        "private",
        "secret",
        "service",
    }
)
_SENSITIVE_COMPOUNDS: Final = frozenset(
    f"{context}{marker}"
    for context in _CREDENTIAL_CONTEXTS
    for marker in _CREDENTIAL_MARKERS
)


@dataclass(frozen=True, slots=True)
class TimestampInspection:
    """Carry a timestamp value and independently typed validity state."""

    value: TimestampValue
    valid: bool


def _is_valid_date(raw: str) -> bool:
    try:
        _ = date.fromisoformat(raw)
    except ValueError:
        return False
    return True


def _validated_datetime(raw: str) -> str | None:
    candidate = f"{raw[:-1]}+00:00" if raw.endswith("Z") else raw
    try:
        _ = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    return candidate


def inspect_timestamp(raw: str) -> TimestampInspection:
    """Validate the exact accepted timestamp grammar without inventing timezone."""
    normalized = raw
    valid = _DATE_PATTERN.fullmatch(raw) is not None and _is_valid_date(raw)
    if (
        _DATETIME_PATTERN.fullmatch(raw) is not None
        and (candidate := _validated_datetime(raw)) is not None
    ):
        normalized = candidate
        valid = True
    return TimestampInspection(
        value=TimestampValue(raw=raw, normalized=normalized),
        valid=valid,
    )


def normalize_timestamp(raw: str) -> TimestampValue:
    """Preserve raw timestamp evidence and return its exact normalized value."""
    return inspect_timestamp(raw).value


def is_sensitive_name(name: str) -> bool:
    """Recognize credential markers across Unicode and identifier boundaries."""
    compatible = normalize("NFKC", name).casefold()
    tokens = frozenset(match.group(0) for match in _NAME_TOKEN.finditer(compatible))
    return bool(_SENSITIVE_TOKENS.intersection(tokens)) or any(
        token in _SENSITIVE_COMPOUNDS for token in tokens
    )


def redact_sensitive_value(name: str, value: str) -> str:
    """Replace a complete custom value when its name denotes a credential."""
    return _REDACTION_MARKER if is_sensitive_name(name) else value


_CHINA_TZ: Final = timezone(timedelta(hours=8))


def to_china_time(ts: TimestampValue | None) -> str | None:
    """Convert a TimestampValue to YYYY-MM-DD HH:MM:SS in China time (UTC+8)."""
    if ts is None:
        return None
    try:
        dt = datetime.fromisoformat(ts.normalized)
    except ValueError:
        return ts.raw
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    china = dt.astimezone(_CHINA_TZ)
    return china.strftime("%Y-%m-%d %H:%M:%S")
