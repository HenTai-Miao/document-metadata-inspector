"""Adversarial identity, budget, and lifecycle tests for legacy OLE workbooks."""

from __future__ import annotations

from pathlib import Path
from struct import pack_into
from typing import TYPE_CHECKING, final

import pytest
from olefile import DEFECT_INCORRECT, OleFileIO

from xlsx_metadata_forensics.errors import ErrorCode, ExtractionError
from xlsx_metadata_forensics.extractor import extract_metadata
from xlsx_metadata_forensics.formats import ExcelFormat
from xlsx_metadata_forensics.legacy.package import open_legacy_workbook
from xlsx_metadata_forensics.models import ExtractionLimits, ExtractionRequest

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import BinaryIO

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures"
XLS_PATH = FIXTURE_DIR / "metadata.xls"


def _fixture_copy(tmp_path: Path, name: str = "test.xls") -> Path:
    path = tmp_path / name
    _ = path.write_bytes(XLS_PATH.read_bytes())
    return path


def _rewrite_workbook(
    path: Path,
    transform: Callable[[bytearray], None],
) -> None:
    with OleFileIO(str(path), raise_defects=DEFECT_INCORRECT) as ole:
        payload = bytearray(ole.openstream("Workbook").read())
    transform(payload)
    with OleFileIO(
        str(path),
        raise_defects=DEFECT_INCORRECT,
        write_mode=True,
    ) as ole:
        ole.write_stream("Workbook", bytes(payload))


def _assert_open_error(path: Path, code: ErrorCode) -> None:
    with (
        pytest.raises(ExtractionError) as exc_info,
        open_legacy_workbook(
            path,
            ExtractionLimits(),
            expected_format=ExcelFormat.XLS,
        ),
    ):
        pass
    assert exc_info.value.code == code


def test_legacy_open_uses_incorrect_defect_threshold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CFB structural defects at the incorrect level are not tolerated."""
    path = _fixture_copy(tmp_path)
    observed: list[int] = []

    def capturing_constructor(
        source: BinaryIO,
        *,
        raise_defects: int,
    ) -> OleFileIO[str]:
        observed.append(raise_defects)
        result: OleFileIO[str] = OleFileIO(source, raise_defects=raise_defects)
        return result

    monkeypatch.setattr(
        "xlsx_metadata_forensics.legacy.package.OleFileIO",
        capturing_constructor,
    )

    with open_legacy_workbook(
        path,
        ExtractionLimits(),
        expected_format=ExcelFormat.XLS,
    ):
        pass

    assert observed == [DEFECT_INCORRECT]


def test_legacy_entry_limit_is_enforced(tmp_path: Path) -> None:
    """CFB directory entries are counted before any workbook stream read."""
    path = _fixture_copy(tmp_path)
    limits = ExtractionLimits(max_entries=0)

    with (
        pytest.raises(ExtractionError) as exc_info,
        open_legacy_workbook(path, limits, expected_format=ExcelFormat.XLS),
    ):
        pass

    assert exc_info.value.code == ErrorCode.UNSAFE_PACKAGE


def test_legacy_total_read_budget_is_enforced_during_identity(tmp_path: Path) -> None:
    """Even the minimum BIFF identity evidence is charged to the shared budget."""
    path = _fixture_copy(tmp_path)
    limits = ExtractionLimits(max_total_read_bytes=0)

    with (
        pytest.raises(ExtractionError) as exc_info,
        open_legacy_workbook(path, limits, expected_format=ExcelFormat.XLS),
    ):
        pass

    assert exc_info.value.code == ErrorCode.FILE_TOO_LARGE


def test_legacy_report_uses_real_cfb_entry_count(tmp_path: Path) -> None:
    """The public report exposes the validated CFB inventory count."""
    path = _fixture_copy(tmp_path)
    with OleFileIO(str(path), raise_defects=DEFECT_INCORRECT) as ole:
        actual_count = len(ole.listdir(streams=True, storages=True))

    report = extract_metadata(ExtractionRequest(path=path, display_name=path.name))

    assert actual_count > 0
    assert report.file.package_entry_count == actual_count


def test_invalid_biff_bof_record_is_rejected(tmp_path: Path) -> None:
    """A CFB stream name alone cannot establish Excel identity."""
    path = _fixture_copy(tmp_path)

    def corrupt_record_id(payload: bytearray) -> None:
        pack_into("<H", payload, 0, 0x1234)

    _rewrite_workbook(path, corrupt_record_id)
    _assert_open_error(path, ErrorCode.INVALID_EXCEL)


def test_non_globals_biff_substream_is_rejected(tmp_path: Path) -> None:
    """The first BOF must identify workbook globals, not a worksheet."""
    path = _fixture_copy(tmp_path)

    def change_substream_type(payload: bytearray) -> None:
        pack_into("<H", payload, 6, 0x0010)

    _rewrite_workbook(path, change_substream_type)
    _assert_open_error(path, ErrorCode.INVALID_EXCEL)


def test_biff_filepass_record_is_reported_as_encrypted(tmp_path: Path) -> None:
    """FILEPASS in workbook globals is explicit encryption evidence."""
    path = _fixture_copy(tmp_path)

    def insert_filepass_record(payload: bytearray) -> None:
        bof_length = int.from_bytes(payload[2:4], byteorder="little")
        next_record = 4 + bof_length
        pack_into("<H", payload, next_record, 0x002F)

    _rewrite_workbook(path, insert_filepass_record)
    _assert_open_error(path, ErrorCode.ENCRYPTED_EXCEL)


@final
class _DualWorkbookOle:
    def __init__(self) -> None:
        self.closed = False

    def listdir(
        self,
        *,
        streams: bool = True,
        storages: bool = False,
    ) -> list[list[str]]:
        del streams, storages
        return [["Workbook"], ["Book"]]

    def close(self) -> None:
        self.closed = True


def test_ambiguous_workbook_and_book_streams_are_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exactly one root-level Excel workbook stream is required."""
    path = _fixture_copy(tmp_path)
    fake = _DualWorkbookOle()

    def constructor(
        source: BinaryIO,
        *,
        raise_defects: int,
    ) -> _DualWorkbookOle:
        del source, raise_defects
        return fake

    monkeypatch.setattr(
        "xlsx_metadata_forensics.legacy.package.OleFileIO",
        constructor,
    )

    with (
        pytest.raises(ExtractionError) as exc_info,
        open_legacy_workbook(
            path,
            ExtractionLimits(),
            expected_format=ExcelFormat.XLS,
        ),
    ):
        pass

    assert exc_info.value.code == ErrorCode.INVALID_EXCEL
    assert fake.closed is True


@final
class _ControlledValidationError(OSError):
    """Synthetic validation failure used by the lifecycle regression test."""


@final
class _ExplodingOle:
    def __init__(self) -> None:
        self.closed = False

    def listdir(
        self,
        *,
        streams: bool = True,
        storages: bool = False,
    ) -> list[list[str]]:
        del streams, storages
        raise _ControlledValidationError

    def close(self) -> None:
        self.closed = True


def test_pre_yield_oserror_is_typed_and_closes_handle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validation failure closes OLE and preserves the public error contract."""
    path = _fixture_copy(tmp_path)
    fake = _ExplodingOle()

    def constructor(
        source: BinaryIO,
        *,
        raise_defects: int,
    ) -> _ExplodingOle:
        del source, raise_defects
        return fake

    monkeypatch.setattr(
        "xlsx_metadata_forensics.legacy.package.OleFileIO",
        constructor,
    )

    with (
        pytest.raises(ExtractionError) as exc_info,
        open_legacy_workbook(
            path,
            ExtractionLimits(),
            expected_format=ExcelFormat.XLS,
        ),
    ):
        pass

    assert exc_info.value.code == ErrorCode.EXTRACTION_FAILED
    assert fake.closed is True
