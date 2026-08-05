"""Security and lifecycle tests for the generic single-open source snapshot."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, final

import pytest

from document_metadata_inspector.errors import ErrorCode, InspectionError
from document_metadata_inspector.models import InspectionLimits
from document_metadata_inspector.source import open_source_snapshot

if TYPE_CHECKING:
    from typing import BinaryIO, Literal, Self


def test_snapshot_hashes_and_rewinds_the_single_open_stream(tmp_path: Path) -> None:
    path = tmp_path / "sample.pdf"
    payload = b"%PDF-1.7\ncontrolled"
    _ = path.write_bytes(payload)

    with open_source_snapshot(path, InspectionLimits()) as snapshot:
        stream = snapshot.stream
        assert snapshot.name == "sample.pdf"
        assert snapshot.size_bytes == len(payload)
        assert snapshot.sha256 == sha256(payload).hexdigest()
        assert stream.tell() == 0
        assert stream.read() == payload

    assert stream.closed is True


def test_missing_path_returns_a_sanitized_typed_error(tmp_path: Path) -> None:
    path = tmp_path / "missing.docx"

    with (
        pytest.raises(InspectionError) as exc_info,
        open_source_snapshot(path, InspectionLimits()),
    ):
        pass

    assert exc_info.value.code is ErrorCode.INVALID_DOCUMENT
    assert exc_info.value.source == "missing.docx"
    assert str(path) not in exc_info.value.message


def test_size_limit_is_checked_before_content_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "oversized.docx"
    _ = path.write_bytes(b"too large")
    original_open = Path.open

    @final
    class _ReadGuard:
        def __init__(self, wrapped: BinaryIO) -> None:
            self._wrapped = wrapped

        def __enter__(self) -> Self:
            return self

        def __exit__(
            self,
            exc_type: object,
            exc_value: object,
            traceback: object,
        ) -> None:
            self._wrapped.close()

        def fileno(self) -> int:
            return self._wrapped.fileno()

        def read(self, size: int = -1) -> bytes:
            del size
            message = "content was read before the size check"
            raise AssertionError(message)

        def seek(self, offset: int, whence: int = 0) -> int:
            return self._wrapped.seek(offset, whence)

    def guarded_open(
        candidate: Path,
        mode: Literal["rb"] = "rb",
    ) -> _ReadGuard:
        return _ReadGuard(original_open(candidate, mode))

    monkeypatch.setattr(Path, "open", guarded_open)

    with (
        pytest.raises(InspectionError) as exc_info,
        open_source_snapshot(path, InspectionLimits(max_file_bytes=1)),
    ):
        pass

    assert exc_info.value.code is ErrorCode.RESOURCE_LIMIT_EXCEEDED


def test_path_replacement_after_open_cannot_mix_source_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "target.docx"
    replacement = tmp_path / "replacement.docx"
    first = b"PK\x03\x04first-source"
    second = b"PK\x03\x04replacement-source"
    _ = path.write_bytes(first)
    _ = replacement.write_bytes(second)
    original_open = Path.open
    replaced = False

    def replace_after_open(
        candidate: Path,
        mode: Literal["rb"] = "rb",
    ) -> BinaryIO:
        nonlocal replaced
        stream = original_open(candidate, mode)
        if candidate == path and not replaced:
            replaced = True
            _ = replacement.replace(path)
        return stream

    monkeypatch.setattr(Path, "open", replace_after_open)

    with open_source_snapshot(path, InspectionLimits()) as snapshot:
        assert snapshot.sha256 == sha256(first).hexdigest()
        assert snapshot.stream.read() == first

    assert replaced is True
    assert path.read_bytes() == second


def test_in_place_mutation_is_rejected_before_success(tmp_path: Path) -> None:
    path = tmp_path / "mutable.pdf"
    _ = path.write_bytes(b"%PDF-1.7\noriginal")

    def mutate_during_snapshot() -> None:
        with open_source_snapshot(path, InspectionLimits()) as snapshot:
            with path.open("r+b") as mutable:
                _ = mutable.seek(-1, 2)
                _ = mutable.write(b"X")
            _ = snapshot.stream.seek(0)

    with pytest.raises(InspectionError) as exc_info:
        mutate_during_snapshot()

    assert exc_info.value.code is ErrorCode.SOURCE_CHANGED
