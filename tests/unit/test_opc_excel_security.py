"""XLSB identity read-budget and access-boundary tests."""

from pathlib import Path
from typing import IO, Literal
from zipfile import ZipExtFile, ZipFile, ZipInfo

import pytest

from tests.factories import rewrite_package
from tests.opc_factories import (
    BINARY_WORKBOOK_PART,
    BRT_BEGIN_BOOK,
    CONTENT_TYPES_PART,
    ROOT_RELS_PART,
    make_opc_workbook,
)
from tests.zip_mutators import mark_member_encrypted
from xlsx_metadata_forensics.errors import ErrorCode, ExtractionError
from xlsx_metadata_forensics.formats import ExcelFormat
from xlsx_metadata_forensics.models import ExtractionLimits
from xlsx_metadata_forensics.ooxml.package import open_package

IDENTITY_PARTS = (CONTENT_TYPES_PART, ROOT_RELS_PART, BINARY_WORKBOOK_PART)


def _part_sizes(path: Path, names: tuple[str, ...]) -> tuple[int, ...]:
    with ZipFile(path, "r") as archive:
        return tuple(archive.getinfo(name).file_size for name in names)


def test_xlsb_identity_reads_only_fixed_parts_and_three_binary_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: an XLSB package and observers at the ZIP content-consumption seam.
    workbook = make_opc_workbook(tmp_path / "access.xlsb", ExcelFormat.XLSB)
    original_open = ZipFile.open
    original_read = ZipExtFile.read
    opened_parts: list[str] = []
    requested_sizes: list[int] = []

    def tracked_open(
        archive: ZipFile,
        name: str | ZipInfo,
        mode: Literal["r", "w"] = "r",
        pwd: bytes | None = None,
        *,
        force_zip64: bool = False,
    ) -> IO[bytes]:
        opened_parts.append(name.filename if isinstance(name, ZipInfo) else name)
        return original_open(
            archive,
            name,
            mode,
            pwd,
            force_zip64=force_zip64,
        )

    def tracked_read(stream: ZipExtFile, size: int = -1) -> bytes:
        requested_sizes.append(size)
        return original_read(stream, size)

    monkeypatch.setattr(ZipFile, "open", tracked_open)
    monkeypatch.setattr(ZipExtFile, "read", tracked_read)

    # When: package identity is validated without any public content read.
    with open_package(
        workbook,
        ExtractionLimits(),
        expected_format=ExcelFormat.XLSB,
    ) as package:
        actual_format = package.format

    # Then: no worksheet/shared-string/VBA part is opened or decoded.
    assert actual_format is ExcelFormat.XLSB
    assert tuple(opened_parts) == IDENTITY_PARTS
    assert requested_sizes[-1] == 3


def test_xlsb_prefix_consumes_the_shared_validation_budget(tmp_path: Path) -> None:
    # Given: a binary main part longer than its identity prefix and an exact budget.
    workbook = make_opc_workbook(tmp_path / "budget.xlsb", ExcelFormat.XLSB)
    rewrite_package(
        workbook,
        {BINARY_WORKBOOK_PART: BRT_BEGIN_BOOK + b"non-identity workbook payload"},
        {},
    )
    content_types_size, relationships_size, binary_size = _part_sizes(
        workbook, IDENTITY_PARTS
    )
    assert binary_size > len(BRT_BEGIN_BOOK)
    validation_bytes = content_types_size + relationships_size + len(BRT_BEGIN_BOOK)
    limits = ExtractionLimits(max_total_read_bytes=validation_bytes)

    # When: validation consumes that budget and a public read asks for more.
    with (
        open_package(
            workbook,
            limits,
            expected_format=ExcelFormat.XLSB,
        ) as package,
        pytest.raises(ExtractionError) as caught,
    ):
        _ = package.read_bytes(CONTENT_TYPES_PART)

    # Then: the binary-prefix check did not receive a hidden fresh budget.
    assert caught.value.code is ErrorCode.FILE_TOO_LARGE


def test_xlsb_validation_fails_when_prefix_budget_is_one_byte_short(
    tmp_path: Path,
) -> None:
    # Given: a non-degenerate binary part and a budget one identity byte short.
    workbook = make_opc_workbook(tmp_path / "short-budget.xlsb", ExcelFormat.XLSB)
    rewrite_package(
        workbook,
        {BINARY_WORKBOOK_PART: BRT_BEGIN_BOOK + b"non-identity workbook payload"},
        {},
    )
    content_types_size, relationships_size, binary_size = _part_sizes(
        workbook, IDENTITY_PARTS
    )
    assert binary_size > len(BRT_BEGIN_BOOK)
    limits = ExtractionLimits(
        max_total_read_bytes=(
            content_types_size + relationships_size + len(BRT_BEGIN_BOOK) - 1
        )
    )

    # When / Then: XLSB identity cannot read an uncharged third prefix byte.
    with (
        pytest.raises(ExtractionError) as caught,
        open_package(
            workbook,
            limits,
            expected_format=ExcelFormat.XLSB,
        ),
    ):
        pass
    assert caught.value.code is ErrorCode.FILE_TOO_LARGE
    assert caught.value.source == BINARY_WORKBOOK_PART


def test_encrypted_xlsb_uses_generic_excel_opc_error_contract(tmp_path: Path) -> None:
    # Given: a genuine XLSB identity with one encrypted ZIP member flag.
    workbook = make_opc_workbook(tmp_path / "encrypted.xlsb", ExcelFormat.XLSB)
    encrypted = mark_member_encrypted(
        workbook.read_bytes(),
        BINARY_WORKBOOK_PART,
    )
    _ = workbook.write_bytes(encrypted)

    # When: central inventory rejects encryption before opening package parts.
    with (
        pytest.raises(ExtractionError) as caught,
        open_package(
            workbook,
            ExtractionLimits(),
            expected_format=ExcelFormat.XLSB,
        ),
    ):
        pass

    # Then: code and public message describe the whole Excel OPC family.
    assert caught.value.code is ErrorCode.ENCRYPTED_EXCEL
    assert caught.value.message == "Encrypted Excel OPC packages are not supported."


def test_read_time_encryption_error_uses_generic_excel_opc_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a validated XLSB package whose next ZIP stream read reports encryption.
    workbook = make_opc_workbook(tmp_path / "read-time.xlsb", ExcelFormat.XLSB)
    message = "simulated encrypted member read"

    def encrypted_read(_stream: ZipExtFile, _size: int = -1) -> bytes:
        raise RuntimeError(message)

    # When: a bounded public read reaches the characterized RuntimeError seam.
    with open_package(
        workbook,
        ExtractionLimits(),
        expected_format=ExcelFormat.XLSB,
    ) as package:
        monkeypatch.setattr(ZipExtFile, "read", encrypted_read)
        with pytest.raises(ExtractionError) as caught:
            _ = package.read_bytes(CONTENT_TYPES_PART)

    # Then: the translated error is generic to the supported Excel OPC family.
    assert caught.value.code is ErrorCode.ENCRYPTED_EXCEL
    assert caught.value.source == CONTENT_TYPES_PART
    assert caught.value.message == "Encrypted Excel OPC packages are not supported."


def test_invalid_xlsb_prefix_closes_acquired_zip_resource(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: invalid XLSB bytes and an observer on archive closure.
    workbook = make_opc_workbook(tmp_path / "invalid-prefix.xlsb", ExcelFormat.XLSB)
    rewrite_package(workbook, {BINARY_WORKBOOK_PART: b"wrong"}, {})
    original_close = ZipFile.close
    closed_resources: set[int] = set()

    def tracked_close(archive: ZipFile) -> None:
        original_close(archive)
        closed_resources.add(id(archive))

    monkeypatch.setattr(ZipFile, "close", tracked_close)

    # When: binary identity validation fails after ZIP acquisition.
    with (
        pytest.raises(ExtractionError),
        open_package(
            workbook,
            ExtractionLimits(),
            expected_format=ExcelFormat.XLSB,
        ),
    ):
        pass

    # Then: the acquired archive closes exactly once.
    assert len(closed_resources) == 1
