"""Hostile ZIP central-directory inventory validation."""

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final
from unicodedata import category
from urllib.parse import unquote
from zipfile import ZipFile, ZipInfo

from xlsx_metadata_forensics.errors import ErrorCode, ExtractionError
from xlsx_metadata_forensics.models import ExtractionLimits

_MAX_PERCENT_DECODE_DEPTH: Final = 2


def _failure(
    code: ErrorCode,
    message: str,
    source: str | None = None,
) -> ExtractionError:
    return ExtractionError(code, message, source)


def bounded_unquote(value: str) -> str | None:
    """Decode package identifiers to a fixed depth or reject non-convergence."""
    decoded = value
    for _ in range(_MAX_PERCENT_DECODE_DEPTH):
        candidate = unquote(decoded)
        if candidate == decoded:
            return decoded
        decoded = candidate
    return decoded if unquote(decoded) == decoded else None


def _safe_canonical_name(name: str) -> str | None:
    decoded = bounded_unquote(name)
    if decoded is None:
        return None
    candidate = decoded.removesuffix("/")
    segments = candidate.split("/")
    has_drive = bool(segments and len(segments[0]) > 1 and segments[0][1] == ":")
    if not candidate or (
        decoded.startswith("/")
        or "\\" in decoded
        or has_drive
        or any(category(character) == "Cc" for character in decoded)
        or any(segment in {"", ".", ".."} for segment in segments)
    ):
        return None
    return candidate.casefold()


def build_inventory(
    archive: ZipFile,
    limits: ExtractionLimits,
) -> tuple[Mapping[str, ZipInfo], tuple[str, ...]]:
    """Validate central-directory safety and return an immutable inventory."""
    infos = archive.infolist()
    if len(infos) > limits.max_entries:
        raise _failure(
            ErrorCode.UNSAFE_PACKAGE,
            "The package contains too many central-directory entries.",
        )
    names = tuple(info.filename for info in infos)
    canonical_names = tuple(_safe_canonical_name(name) for name in names)
    if (
        any(info.orig_filename != info.filename for info in infos)
        or any(name is None for name in canonical_names)
        or len(set(names)) != len(names)
        or len(set(canonical_names)) != len(canonical_names)
    ):
        raise _failure(
            ErrorCode.UNSAFE_PACKAGE,
            "The package contains unsafe or ambiguous member names.",
        )
    if any(info.flag_bits & 1 for info in infos):
        raise _failure(
            ErrorCode.ENCRYPTED_EXCEL,
            "Encrypted Excel OPC packages are not supported.",
        )
    return (
        MappingProxyType({info.filename: info for info in infos}),
        tuple(sorted(names)),
    )
