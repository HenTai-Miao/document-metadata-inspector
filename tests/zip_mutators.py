"""Precise in-memory ZIP mutators for hostile package regressions."""

from dataclasses import dataclass
from io import BytesIO
from typing import Final
from zipfile import ZIP_BZIP2, ZIP_DEFLATED, ZIP_LZMA, ZipFile

_CENTRAL_SIGNATURE: Final = b"PK\x01\x02"
_LOCAL_SIGNATURE: Final = b"PK\x03\x04"
_EOCD_SIGNATURE: Final = b"PK\x05\x06"
_CENTRAL_HEADER_BYTES: Final = 46
_LOCAL_HEADER_BYTES: Final = 30
_EOCD_BYTES: Final = 22
_UTF8_FLAG: Final = 1 << 11
_ENCRYPTED_FLAG: Final = 1
_UNSUPPORTED_EXTRACT_VERSION: Final = 255
_UNKNOWN_COMPRESSION_METHOD: Final = 255


@dataclass(frozen=True, slots=True)
class _CentralRecord:
    central_offset: int
    local_offset: int
    compressed_size: int
    name: bytes


def _u16(package: bytes | bytearray, offset: int) -> int:
    return int.from_bytes(package[offset : offset + 2], "little")


def _u32(package: bytes | bytearray, offset: int) -> int:
    return int.from_bytes(package[offset : offset + 4], "little")


def _write_u16(package: bytearray, offset: int, value: int) -> None:
    package[offset : offset + 2] = value.to_bytes(2, "little")


def _central_records(package: bytes) -> tuple[_CentralRecord, ...]:
    eocd_offset = package.rfind(_EOCD_SIGNATURE)
    assert eocd_offset >= 0
    disk_number = _u16(package, eocd_offset + 4)
    central_disk = _u16(package, eocd_offset + 6)
    disk_entries = _u16(package, eocd_offset + 8)
    total_entries = _u16(package, eocd_offset + 10)
    central_size = _u32(package, eocd_offset + 12)
    central_offset = _u32(package, eocd_offset + 16)
    comment_size = _u16(package, eocd_offset + 20)
    assert disk_number == central_disk == 0
    assert disk_entries == total_entries
    assert eocd_offset + _EOCD_BYTES + comment_size == len(package)

    records: list[_CentralRecord] = []
    cursor = central_offset
    for _ in range(total_entries):
        assert package[cursor : cursor + 4] == _CENTRAL_SIGNATURE
        compressed_size = _u32(package, cursor + 20)
        name_size = _u16(package, cursor + 28)
        extra_size = _u16(package, cursor + 30)
        record_comment_size = _u16(package, cursor + 32)
        local_offset = _u32(package, cursor + 42)
        name_start = cursor + _CENTRAL_HEADER_BYTES
        name_end = name_start + name_size
        records.append(
            _CentralRecord(
                central_offset=cursor,
                local_offset=local_offset,
                compressed_size=compressed_size,
                name=package[name_start:name_end],
            )
        )
        cursor = name_end + extra_size + record_comment_size
    assert cursor == central_offset + central_size
    return tuple(records)


def _record(package: bytes, member_name: str) -> _CentralRecord:
    encoded_name = member_name.encode()
    matches = tuple(
        record for record in _central_records(package) if record.name == encoded_name
    )
    assert len(matches) == 1
    return matches[0]


def _local_name_start(package: bytes, record: _CentralRecord) -> int:
    assert package[record.local_offset : record.local_offset + 4] == _LOCAL_SIGNATURE
    name_size = _u16(package, record.local_offset + 26)
    name_start = record.local_offset + _LOCAL_HEADER_BYTES
    assert package[name_start : name_start + name_size] == record.name
    return name_start


def _local_data_start(package: bytes, record: _CentralRecord) -> int:
    assert package[record.local_offset : record.local_offset + 4] == _LOCAL_SIGNATURE
    name_size = _u16(package, record.local_offset + 26)
    extra_size = _u16(package, record.local_offset + 28)
    return record.local_offset + _LOCAL_HEADER_BYTES + name_size + extra_size


def _set_flag(package: bytearray, offset: int, flag: int) -> None:
    _write_u16(package, offset, _u16(package, offset) | flag)


def invalidate_central_utf8_name(package: bytes, member_name: str) -> bytes:
    """Set UTF-8 in one central record and inject one invalid leading byte."""
    record = _record(package, member_name)
    mutated = bytearray(package)
    _set_flag(mutated, record.central_offset + 8, _UTF8_FLAG)
    name_start = record.central_offset + _CENTRAL_HEADER_BYTES
    assert record.name
    mutated[name_start] = 0xFF
    return bytes(mutated)


def invalidate_local_utf8_name(package: bytes, member_name: str) -> bytes:
    """Set UTF-8 in one local header and inject one invalid leading byte."""
    record = _record(package, member_name)
    mutated = bytearray(package)
    _set_flag(mutated, record.local_offset + 6, _UTF8_FLAG)
    name_start = _local_name_start(package, record)
    assert record.name
    mutated[name_start] = 0xFF
    return bytes(mutated)


def embed_raw_nul_member_name(
    package: bytes,
    member_name: str,
    byte_index: int,
) -> bytes:
    """Insert one NUL into matching central and local member-name bytes."""
    record = _record(package, member_name)
    assert 0 <= byte_index < len(record.name)
    assert record.name[byte_index] != 0
    central_name_start = record.central_offset + _CENTRAL_HEADER_BYTES
    local_name_start = _local_name_start(package, record)
    mutated = bytearray(package)
    mutated[central_name_start + byte_index] = 0
    mutated[local_name_start + byte_index] = 0
    return bytes(mutated)


def require_unsupported_extract_version(package: bytes, member_name: str) -> bytes:
    """Require CPython's unsupported ZIP extraction version in both headers."""
    record = _record(package, member_name)
    mutated = bytearray(package)
    _write_u16(mutated, record.central_offset + 6, _UNSUPPORTED_EXTRACT_VERSION)
    _write_u16(mutated, record.local_offset + 4, _UNSUPPORTED_EXTRACT_VERSION)
    return bytes(mutated)


def mark_member_encrypted(package: bytes, member_name: str) -> bytes:
    """Set the ZIP encryption bit consistently in central and local headers."""
    record = _record(package, member_name)
    mutated = bytearray(package)
    _set_flag(mutated, record.central_offset + 8, _ENCRYPTED_FLAG)
    _set_flag(mutated, record.local_offset + 6, _ENCRYPTED_FLAG)
    return bytes(mutated)


def set_unknown_compression(package: bytes, member_name: str) -> bytes:
    """Set one member's compression method to an unsupported numeric value."""
    record = _record(package, member_name)
    mutated = bytearray(package)
    _write_u16(mutated, record.central_offset + 10, _UNKNOWN_COMPRESSION_METHOD)
    _write_u16(mutated, record.local_offset + 8, _UNKNOWN_COMPRESSION_METHOD)
    return bytes(mutated)


def corrupt_deflate_stream(package: bytes, member_name: str) -> bytes:
    """Turn the first DEFLATE block into the reserved block type."""
    record = _record(package, member_name)
    central_method = _u16(package, record.central_offset + 10)
    local_method = _u16(package, record.local_offset + 8)
    assert central_method == local_method == ZIP_DEFLATED
    assert record.compressed_size > 0
    data_start = _local_data_start(package, record)
    mutated = bytearray(package)
    original = mutated[data_start]
    mutated[data_start] = (original & 0xF8) | 0x07
    assert mutated[data_start] != original
    return bytes(mutated)


def recompress_member(package: bytes, member_name: str, method: int) -> bytes:
    """Rebuild one member with a selected standard-library ZIP method."""
    source_buffer = BytesIO(package)
    target_buffer = BytesIO()
    with ZipFile(source_buffer, "r") as source, ZipFile(target_buffer, "w") as target:
        for info in source.infolist():
            payload = source.read(info)
            compression = method if info.filename == member_name else info.compress_type
            target.writestr(info, payload, compress_type=compression)
    return target_buffer.getvalue()


def corrupt_bzip2_stream(package: bytes, member_name: str) -> bytes:
    """Invalidate the first byte of one BZIP2 member stream."""
    record = _record(package, member_name)
    method = _u16(package, record.central_offset + 10)
    assert method == ZIP_BZIP2
    data_start = _local_data_start(package, record)
    mutated = bytearray(package)
    mutated[data_start] ^= 0xFF
    return bytes(mutated)


def corrupt_lzma_stream(package: bytes, member_name: str) -> bytes:
    """Invalidate a deterministic payload byte in one ZIP-LZMA stream."""
    record = _record(package, member_name)
    method = _u16(package, record.central_offset + 10)
    assert method == ZIP_LZMA
    assert record.compressed_size > 12
    data_start = _local_data_start(package, record)
    mutated = bytearray(package)
    mutated[data_start + 12] ^= 0xFF
    return bytes(mutated)
