"""Own and verify one single-open, read-only source file snapshot."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from os import fstat
from stat import S_ISREG
from typing import TYPE_CHECKING, Final

from document_metadata_inspector.errors import ErrorCode, InspectionError

if TYPE_CHECKING:
    from collections.abc import Generator
    from os import stat_result
    from pathlib import Path
    from typing import BinaryIO

    from document_metadata_inspector.models import InspectionLimits

_HASH_CHUNK_BYTES: Final = 1024 * 1024
_OPEN_MESSAGE: Final = "The input file could not be opened."
_INSPECT_MESSAGE: Final = "The input file could not be inspected."
_NOT_REGULAR_MESSAGE: Final = "The input path is not a regular file."
_TOO_LARGE_MESSAGE: Final = "The input file exceeds the configured size limit."
_CHANGED_MESSAGE: Final = "The input file changed during inspection."


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    """Bind all parser evidence to one already-open file descriptor and hash."""

    stream: BinaryIO
    name: str
    size_bytes: int
    sha256: str
    limits: InspectionLimits


def _error(code: ErrorCode, message: str, source: str) -> InspectionError:
    return InspectionError(code=code, message=message, source=source, stage="source")


def _stream_sha256(stream: BinaryIO, source_name: str) -> str:
    digest = sha256()
    try:
        _ = stream.seek(0)
        while chunk := stream.read(_HASH_CHUNK_BYTES):
            digest.update(chunk)
        _ = stream.seek(0)
    except OSError as error:
        raise _error(
            ErrorCode.INVALID_DOCUMENT, _INSPECT_MESSAGE, source_name
        ) from error
    return digest.hexdigest()


def _identity(stat: stat_result) -> tuple[int, int, int, int, int]:
    return (
        stat.st_dev,
        stat.st_ino,
        stat.st_size,
        stat.st_mtime_ns,
        stat.st_ctime_ns,
    )


def _inspect_stream(stream: BinaryIO, source_name: str) -> stat_result:
    try:
        return fstat(stream.fileno())
    except OSError as error:
        raise _error(
            ErrorCode.INVALID_DOCUMENT, _INSPECT_MESSAGE, source_name
        ) from error


@contextmanager
def open_source_snapshot(
    path: Path,
    limits: InspectionLimits,
) -> Generator[SourceSnapshot]:
    """Hash, yield and reverify the same open file descriptor."""
    source_name = path.name
    try:
        stream = path.open("rb")
    except OSError as error:
        raise _error(ErrorCode.INVALID_DOCUMENT, _OPEN_MESSAGE, source_name) from error

    with stream:
        initial_stat = _inspect_stream(stream, source_name)
        if not S_ISREG(initial_stat.st_mode):
            raise _error(ErrorCode.INVALID_DOCUMENT, _NOT_REGULAR_MESSAGE, source_name)
        if initial_stat.st_size > limits.max_file_bytes:
            raise _error(
                ErrorCode.RESOURCE_LIMIT_EXCEEDED,
                _TOO_LARGE_MESSAGE,
                source_name,
            )

        initial_identity = _identity(initial_stat)
        initial_sha256 = _stream_sha256(stream, source_name)
        if _identity(_inspect_stream(stream, source_name)) != initial_identity:
            raise _error(ErrorCode.SOURCE_CHANGED, _CHANGED_MESSAGE, source_name)

        snapshot = SourceSnapshot(
            stream=stream,
            name=source_name,
            size_bytes=initial_stat.st_size,
            sha256=initial_sha256,
            limits=limits,
        )
        yield snapshot

        if _identity(_inspect_stream(stream, source_name)) != initial_identity:
            raise _error(ErrorCode.SOURCE_CHANGED, _CHANGED_MESSAGE, source_name)
        final_sha256 = _stream_sha256(stream, source_name)
        if (
            final_sha256 != initial_sha256
            or _identity(_inspect_stream(stream, source_name)) != initial_identity
        ):
            raise _error(ErrorCode.SOURCE_CHANGED, _CHANGED_MESSAGE, source_name)
