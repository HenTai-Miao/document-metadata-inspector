"""Small public adapter for bounded OLE stream reads."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from olefile import OleFileIO


def read_stream_prefix(
    ole: OleFileIO[str],
    stream_name: str,
    length: int,
) -> bytes:
    """Read at most ``length`` bytes through olefile's public stream API."""
    if length <= 0:
        return b""
    with ole.openstream(stream_name) as stream:
        return stream.read(length)
