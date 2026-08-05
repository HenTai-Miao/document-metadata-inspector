"""Bounded native inspection of legacy Word and Excel OLE containers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, Protocol, cast

from olefile import DEFECT_INCORRECT, OleFileIO
from olefile.olefile import OleFileError

from document_metadata_inspector.errors import ErrorCode, InspectionError
from document_metadata_inspector.formats import DocumentFamily
from document_metadata_inspector.native.office_properties import read_ole_property_set

if TYPE_CHECKING:
    from collections.abc import Mapping

    from document_metadata_inspector.formats import FormatIdentity
    from document_metadata_inspector.models import EvidenceObservation, InspectionLimits
    from document_metadata_inspector.source import SourceSnapshot

_SUMMARY_STREAM: Final = "\x05SummaryInformation"
_DOCUMENT_SUMMARY_STREAM: Final = "\x05DocumentSummaryInformation"
_ENCRYPTION_STREAMS: Final = frozenset({"EncryptedPackage", "EncryptionInfo"})
_BOF_RECORD_IDS: Final = frozenset({0x0009, 0x0209, 0x0409, 0x0809})
_BIFF_VERSIONS: Final = frozenset({0x0000, 0x0200, 0x0300, 0x0400, 0x0500, 0x0600})
_FILEPASS_RECORD_ID: Final = 0x002F
_EOF_RECORD_ID: Final = 0x000A
_WORKBOOK_GLOBALS_TYPE: Final = 0x0005
_WORD_FIB_MAGIC: Final = 0xA5EC
_BIFF_BOF_PAYLOAD_BYTES: Final = 4
_WORD_FIB_PREFIX_BYTES: Final = 12


def _error(code: ErrorCode, message: str, source: str | None = None) -> InspectionError:
    return InspectionError(
        code=code,
        message=message,
        source=source,
        stage="native_ole",
    )


def _u16(payload: bytes, offset: int) -> int:
    return int.from_bytes(payload[offset : offset + 2], byteorder="little")


def _read_exact(stream: object, length: int) -> bytes:
    reader = cast("_Readable", stream)
    payload = reader.read(length)
    if len(payload) != length:
        raise _error(
            ErrorCode.CORRUPT_CONTAINER,
            "An OLE stream ended unexpectedly.",
        )
    return payload


class _Readable(Protocol):
    """Minimal local typing boundary for olefile stream objects."""

    def read(self, size: int = -1) -> bytes:
        """Read at most ``size`` bytes."""
        ...

    def seek(
        self,
        offset: int,
        whence: int = 0,
    ) -> int:
        """Move to one absolute or relative stream offset."""
        ...


def _validate_excel_stream(
    ole: OleFileIO[str],
    stream_name: str,
    limits: InspectionLimits,
) -> None:
    stream_size = ole.get_size(stream_name)
    with ole.openstream(stream_name) as raw_stream:
        dynamic_stream = cast("object", raw_stream)
        stream = cast("_Readable", dynamic_stream)
        first = _read_exact(stream, 8)
        record_id = _u16(first, 0)
        record_length = _u16(first, 2)
        version = _u16(first, 4)
        substream_type = _u16(first, 6)
        if (
            record_id not in _BOF_RECORD_IDS
            or record_length < _BIFF_BOF_PAYLOAD_BYTES
            or version not in _BIFF_VERSIONS
            or substream_type != _WORKBOOK_GLOBALS_TYPE
            or 4 + record_length > stream_size
        ):
            raise _error(
                ErrorCode.FORMAT_MISMATCH,
                "The OLE workbook stream is not valid BIFF globals.",
                stream_name,
            )

        offset = 4 + record_length
        for _ in range(limits.max_entries):
            if offset + 4 > stream_size:
                break
            _ = stream.seek(offset)
            header = _read_exact(stream, 4)
            record_type = _u16(header, 0)
            payload_length = _u16(header, 2)
            if record_type == _FILEPASS_RECORD_ID:
                raise _error(
                    ErrorCode.PASSWORD_REQUIRED,
                    "The legacy Excel workbook is encrypted.",
                    stream_name,
                )
            if record_type == _EOF_RECORD_ID:
                if payload_length != 0:
                    break
                return
            offset += 4 + payload_length
            if offset > stream_size:
                break
    raise _error(
        ErrorCode.CORRUPT_CONTAINER,
        "The BIFF workbook globals stream is incomplete.",
        stream_name,
    )


def _validate_word_stream(
    ole: OleFileIO[str],
    stream_name: str,
) -> None:
    with ole.openstream(stream_name) as stream:
        prefix = stream.read(_WORD_FIB_PREFIX_BYTES)
    if len(prefix) != _WORD_FIB_PREFIX_BYTES or _u16(prefix, 0) != _WORD_FIB_MAGIC:
        raise _error(
            ErrorCode.FORMAT_MISMATCH,
            "The OLE WordDocument stream has an invalid FIB prefix.",
            stream_name,
        )
    flags = _u16(prefix, 10)
    if flags & 0x0100:
        raise _error(
            ErrorCode.PASSWORD_REQUIRED,
            "The legacy Word document is encrypted.",
            stream_name,
        )


def _validate_identity(
    ole: OleFileIO[str],
    entries: tuple[tuple[str, ...], ...],
    identity: FormatIdentity,
    limits: InspectionLimits,
) -> None:
    root_names = frozenset(entry[0] for entry in entries if len(entry) == 1)
    if root_names.intersection(_ENCRYPTION_STREAMS):
        raise _error(
            ErrorCode.PASSWORD_REQUIRED,
            "The OLE container holds an encrypted Office package.",
        )
    if identity.family is DocumentFamily.EXCEL:
        workbook_streams = tuple(
            name for name in ("Workbook", "Book") if name in root_names
        )
        if len(workbook_streams) != 1:
            raise _error(
                ErrorCode.FORMAT_MISMATCH,
                "The OLE container does not identify exactly one workbook.",
            )
        _validate_excel_stream(ole, workbook_streams[0], limits)
        return
    if identity.family is DocumentFamily.WORD:
        if "WordDocument" not in root_names:
            raise _error(
                ErrorCode.FORMAT_MISMATCH,
                "The OLE container does not contain a WordDocument stream.",
            )
        _validate_word_stream(ole, "WordDocument")
        return
    raise _error(
        ErrorCode.FORMAT_MISMATCH,
        "The declared document family does not use an OLE Office container.",
    )


def _properties(
    ole: OleFileIO[str],
    name: str,
    *,
    limits: InspectionLimits,
    remaining: int,
    document_summary: bool,
) -> tuple[tuple[EvidenceObservation, ...], int]:
    if not ole.exists(name):
        return (), remaining
    stream_size = ole.get_size(name)
    if stream_size > limits.max_part_bytes or stream_size > remaining:
        raise _error(
            ErrorCode.RESOURCE_LIMIT_EXCEEDED,
            "An OLE property set exceeds the configured read budget.",
            name,
        )
    if document_summary:
        raw_properties = ole.getproperties(name, convert_time=True)
    else:
        raw_properties = ole.getproperties(
            name,
            convert_time=True,
            no_conversion=[10],
        )
    dynamic = cast("object", raw_properties)
    properties = cast("Mapping[int, object]", dynamic)
    return (
        read_ole_property_set(
            properties,
            location=name,
            document_summary=document_summary,
        ),
        remaining - stream_size,
    )


def extract_ole(
    snapshot: SourceSnapshot,
    identity: FormatIdentity,
) -> tuple[tuple[EvidenceObservation, ...], tuple[str, ...]]:
    """Validate and enumerate native evidence from one OLE Office container."""
    try:
        _ = snapshot.stream.seek(0)
        ole: OleFileIO[str] = OleFileIO(
            snapshot.stream,
            raise_defects=DEFECT_INCORRECT,
        )
    except OleFileError as error:
        raise _error(
            ErrorCode.CORRUPT_CONTAINER,
            "The input is not a valid OLE container.",
            snapshot.name,
        ) from error
    except OSError as error:
        raise _error(
            ErrorCode.INVALID_DOCUMENT,
            "The OLE container could not be opened.",
            snapshot.name,
        ) from error

    with ole:
        try:
            dynamic_entries = cast(
                "object",
                ole.listdir(streams=True, storages=True),
            )
            listed_entries = cast("list[list[str]]", dynamic_entries)
            entries = tuple(tuple(path) for path in listed_entries)
            if len(entries) > snapshot.limits.max_entries:
                raise _error(
                    ErrorCode.RESOURCE_LIMIT_EXCEEDED,
                    "The OLE container contains too many directory entries.",
                    snapshot.name,
                )
            _validate_identity(ole, entries, identity, snapshot.limits)
            remaining = snapshot.limits.max_total_read_bytes
            summary, remaining = _properties(
                ole,
                _SUMMARY_STREAM,
                limits=snapshot.limits,
                remaining=remaining,
                document_summary=False,
            )
            document_summary, _ = _properties(
                ole,
                _DOCUMENT_SUMMARY_STREAM,
                limits=snapshot.limits,
                remaining=remaining,
                document_summary=True,
            )
            result = (*summary, *document_summary), ()
        except InspectionError:
            raise
        except (OleFileError, OSError) as error:
            raise _error(
                ErrorCode.CORRUPT_CONTAINER,
                "The OLE container could not be inspected safely.",
                snapshot.name,
            ) from error
        return result
