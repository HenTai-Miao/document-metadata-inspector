"""Own one immutable-by-verification input snapshot for an extraction."""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from os import fstat
from stat import S_ISREG
from typing import BinaryIO, Final

from xlsx_metadata_forensics.errors import ErrorCode, ExtractionError
from xlsx_metadata_forensics.models import ExtractionRequest

_HASH_CHUNK_BYTES: Final = 1024 * 1024
_CHANGED_MESSAGE: Final = "The input file changed during extraction."
_INSPECT_MESSAGE: Final = "The input file could not be inspected."
_NOT_REGULAR_MESSAGE: Final = "The input path is not a regular file."
_OPEN_MESSAGE: Final = "The input file could not be opened."
_VERIFY_MESSAGE: Final = "The input file could not be verified after extraction."


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    """Bind extraction evidence to one already-open read-only file descriptor."""

    stream: BinaryIO
    name: str
    size_bytes: int
    sha256: str


def _failure(message: str, source: str) -> ExtractionError:
    return ExtractionError(ErrorCode.EXTRACTION_FAILED, message, source)


def _stream_sha256(stream: BinaryIO, source_name: str) -> str:
    """Hash one seekable stream incrementally and rewind it for its parser."""
    digest = sha256()
    try:
        _ = stream.seek(0)
        while chunk := stream.read(_HASH_CHUNK_BYTES):
            digest.update(chunk)
        _ = stream.seek(0)
    except OSError as error:
        raise _failure(_INSPECT_MESSAGE, source_name) from error
    return digest.hexdigest()


@contextmanager
def open_source_snapshot(request: ExtractionRequest) -> Generator[SourceSnapshot]:
    """Open, preflight, hash, parse, and verify one stable file descriptor."""
    source_name = request.path.name
    try:
        stream = request.path.open("rb")
    except OSError as error:
        raise _failure(_OPEN_MESSAGE, source_name) from error

    with stream:
        try:
            stat_result = fstat(stream.fileno())
        except OSError as error:
            raise _failure(_INSPECT_MESSAGE, source_name) from error

        if not S_ISREG(stat_result.st_mode):
            raise _failure(_NOT_REGULAR_MESSAGE, source_name)
        if stat_result.st_size > request.limits.max_file_bytes:
            raise ExtractionError(
                ErrorCode.FILE_TOO_LARGE,
                "The input file exceeds the configured size limit.",
                source_name,
            )

        initial_sha256 = _stream_sha256(stream, source_name)
        snapshot = SourceSnapshot(
            stream=stream,
            name=source_name,
            size_bytes=stat_result.st_size,
            sha256=initial_sha256,
        )
        yield snapshot

        try:
            final_size = fstat(stream.fileno()).st_size
        except OSError as error:
            raise _failure(_VERIFY_MESSAGE, source_name) from error
        final_sha256 = _stream_sha256(stream, source_name)
        if final_size != snapshot.size_bytes or final_sha256 != snapshot.sha256:
            raise _failure(_CHANGED_MESSAGE, source_name)
