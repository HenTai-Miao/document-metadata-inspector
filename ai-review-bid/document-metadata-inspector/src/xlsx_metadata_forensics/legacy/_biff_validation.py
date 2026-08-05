"""Minimal BIFF workbook-globals identity and encryption validation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from xlsx_metadata_forensics.errors import ErrorCode, ExtractionError
from xlsx_metadata_forensics.legacy._ole_adapter import read_stream_prefix

if TYPE_CHECKING:
    from olefile import OleFileIO

    from xlsx_metadata_forensics.legacy._read_budget import LegacyReadBudget

_BOF_RECORD_IDS: Final = frozenset({0x0009, 0x0209, 0x0409, 0x0809})
_BIFF_VERSIONS: Final = frozenset({0x0000, 0x0200, 0x0300, 0x0400, 0x0500, 0x0600})
_FILEPASS_RECORD_ID: Final = 0x002F
_EOF_RECORD_ID: Final = 0x000A
_WORKBOOK_GLOBALS_TYPE: Final = 0x0005
_MIN_BOF_BYTES: Final = 8
_RECORD_HEADER_BYTES: Final = 4


def _invalid(source: str) -> ExtractionError:
    return ExtractionError(
        ErrorCode.INVALID_EXCEL,
        "The OLE workbook stream does not contain valid BIFF globals.",
        source,
    )


def _u16(payload: bytes, offset: int) -> int:
    """Decode one little-endian unsigned 16-bit integer."""
    return int.from_bytes(payload[offset : offset + 2], byteorder="little")


def select_workbook_stream(
    entries: tuple[tuple[str, ...], ...],
    source: str,
) -> str:
    """Require exactly one root-level Workbook or Book stream."""
    candidates = tuple(
        entry[0]
        for entry in entries
        if len(entry) == 1 and entry[0] in {"Workbook", "Book"}
    )
    if len(candidates) != 1:
        raise _invalid(source)
    return candidates[0]


def _prefix(
    ole: OleFileIO[str],
    stream_name: str,
    stream_size: int,
    length: int,
    budget: LegacyReadBudget,
) -> bytes:
    required = min(stream_size, length)
    budget.claim(required, stream_name)
    payload = read_stream_prefix(ole, stream_name, required)
    if len(payload) != required:
        raise _invalid(stream_name)
    return payload


def validate_biff_globals(
    ole: OleFileIO[str],
    stream_name: str,
    budget: LegacyReadBudget,
) -> None:
    """Validate BOF and scan record headers through globals EOF for FILEPASS."""
    stream_size = ole.get_size(stream_name)
    first = _prefix(ole, stream_name, stream_size, _MIN_BOF_BYTES, budget)
    if len(first) < _MIN_BOF_BYTES:
        raise _invalid(stream_name)

    record_id = _u16(first, 0)
    record_length = _u16(first, 2)
    version = _u16(first, 4)
    substream_type = _u16(first, 6)
    if (
        record_id not in _BOF_RECORD_IDS
        or record_length < _RECORD_HEADER_BYTES
        or version not in _BIFF_VERSIONS
        or substream_type != _WORKBOOK_GLOBALS_TYPE
        or _RECORD_HEADER_BYTES + record_length > stream_size
    ):
        raise _invalid(stream_name)

    offset = _RECORD_HEADER_BYTES + record_length
    while offset + _RECORD_HEADER_BYTES <= stream_size:
        end = offset + _RECORD_HEADER_BYTES
        prefix = _prefix(ole, stream_name, stream_size, end, budget)
        next_id = _u16(prefix, offset)
        next_length = _u16(prefix, offset + 2)
        if next_id == _FILEPASS_RECORD_ID:
            raise ExtractionError(
                ErrorCode.ENCRYPTED_EXCEL,
                "Encrypted BIFF workbooks are not supported.",
                stream_name,
            )
        if next_id == _EOF_RECORD_ID:
            if next_length != 0:
                raise _invalid(stream_name)
            return
        offset = end + next_length
        if offset > stream_size:
            raise _invalid(stream_name)

    raise _invalid(stream_name)
