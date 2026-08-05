"""Hostile ZIP parser and decompressor regressions for package access."""

from collections.abc import Callable
from errno import EIO
from pathlib import Path
from zipfile import ZIP_BZIP2, ZIP_LZMA, ZipExtFile

import pytest

from tests.factories import make_workbook
from tests.zip_mutators import (
    corrupt_bzip2_stream,
    corrupt_deflate_stream,
    corrupt_lzma_stream,
    invalidate_central_utf8_name,
    invalidate_local_utf8_name,
    mark_member_encrypted,
    recompress_member,
    require_unsupported_extract_version,
    set_unknown_compression,
)
from xlsx_metadata_forensics.errors import ErrorCode, ExtractionError
from xlsx_metadata_forensics.models import ExtractionLimits
from xlsx_metadata_forensics.ooxml.package import open_package

CORE_PART = "docProps/core.xml"


def test_invalid_utf8_central_name_maps_to_corrupt_package(tmp_path: Path) -> None:
    # Given: a genuine workbook with one invalid UTF-8 central-directory name.
    workbook = make_workbook(tmp_path / "invalid-central-name.xlsx")
    mutated = invalidate_central_utf8_name(workbook.read_bytes(), CORE_PART)
    _ = workbook.write_bytes(mutated)

    # When / Then: construction translates the hostile name to the stable code.
    with (
        pytest.raises(ExtractionError) as caught,
        open_package(workbook, ExtractionLimits()),
    ):
        pass
    assert caught.value.code is ErrorCode.CORRUPT_PACKAGE
    assert caught.value.source == workbook.name


def test_invalid_utf8_local_name_maps_to_corrupt_package_with_part_source(
    tmp_path: Path,
) -> None:
    # Given: a valid central name whose matching local-header name is invalid UTF-8.
    workbook = make_workbook(tmp_path / "invalid-local-name.xlsx")
    mutated = invalidate_local_utf8_name(workbook.read_bytes(), CORE_PART)
    _ = workbook.write_bytes(mutated)

    # When / Then: opening the member reports corruption and its logical part name.
    with (
        open_package(workbook, ExtractionLimits()) as package,
        pytest.raises(ExtractionError) as caught,
    ):
        _ = package.read_bytes(CORE_PART)
    assert caught.value.code is ErrorCode.CORRUPT_PACKAGE
    assert caught.value.source == CORE_PART


def test_unsupported_extract_version_maps_to_corrupt_package(tmp_path: Path) -> None:
    # Given: a genuine workbook requiring a ZIP extraction version CPython rejects.
    workbook = make_workbook(tmp_path / "unsupported-version.xlsx")
    mutated = require_unsupported_extract_version(workbook.read_bytes(), CORE_PART)
    _ = workbook.write_bytes(mutated)

    # When / Then: construction returns the package-corruption contract.
    with (
        pytest.raises(ExtractionError) as caught,
        open_package(workbook, ExtractionLimits()),
    ):
        pass
    assert caught.value.code is ErrorCode.CORRUPT_PACKAGE
    assert caught.value.source == workbook.name


def test_corrupted_deflate_member_maps_to_corrupt_package(tmp_path: Path) -> None:
    # Given: a valid workbook whose optional core part has an invalid DEFLATE block.
    workbook = make_workbook(tmp_path / "corrupt-deflate.xlsx")
    mutated = corrupt_deflate_stream(workbook.read_bytes(), CORE_PART)
    _ = workbook.write_bytes(mutated)

    # When / Then: the decompressor failure is translated with a stable part source.
    with (
        open_package(workbook, ExtractionLimits()) as package,
        pytest.raises(ExtractionError) as caught,
    ):
        _ = package.read_bytes(CORE_PART)
    assert caught.value.code is ErrorCode.CORRUPT_PACKAGE
    assert caught.value.source == CORE_PART


@pytest.mark.parametrize(
    ("method", "corrupt"),
    [
        (ZIP_BZIP2, corrupt_bzip2_stream),
        (ZIP_LZMA, corrupt_lzma_stream),
    ],
    ids=("bzip2", "lzma"),
)
def test_corrupted_standard_member_maps_to_corrupt_package(
    tmp_path: Path,
    method: int,
    corrupt: Callable[[bytes, str], bytes],
) -> None:
    # Given: an optional part using a supported method with corrupt compressed bytes.
    workbook = make_workbook(tmp_path / "corrupt-standard-compression.xlsx")
    recompressed = recompress_member(workbook.read_bytes(), CORE_PART, method)
    mutated = corrupt(recompressed, CORE_PART)
    _ = workbook.write_bytes(mutated)

    # When / Then: decoder failures remain package corruption, never raw exceptions.
    with (
        open_package(workbook, ExtractionLimits()) as package,
        pytest.raises(ExtractionError) as caught,
    ):
        _ = package.read_bytes(CORE_PART)
    assert caught.value.code is ErrorCode.CORRUPT_PACKAGE
    assert caught.value.source == CORE_PART


def test_bzip2_errno_read_failure_maps_to_extraction_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a valid BZIP2 member whose underlying read reports an operational errno.
    workbook = make_workbook(tmp_path / "bzip2-io-error.xlsx")
    recompressed = recompress_member(workbook.read_bytes(), CORE_PART, ZIP_BZIP2)
    _ = workbook.write_bytes(recompressed)
    message = "simulated local read failure"

    def fail_read(_stream: ZipExtFile, _size: int = -1) -> bytes:
        raise OSError(EIO, message)

    # When / Then: errno-bearing I/O remains extraction failure, not corruption.
    with open_package(workbook, ExtractionLimits()) as package:
        monkeypatch.setattr(ZipExtFile, "read", fail_read)
        with pytest.raises(ExtractionError) as caught:
            _ = package.read_bytes(CORE_PART)
    assert caught.value.code is ErrorCode.EXTRACTION_FAILED
    assert caught.value.source == CORE_PART


def test_zip_encrypted_member_maps_to_encrypted_xlsx(tmp_path: Path) -> None:
    # Given: a genuine workbook with the ZIP encryption bit set on one member.
    workbook = make_workbook(tmp_path / "encrypted-member.xlsx")
    mutated = mark_member_encrypted(workbook.read_bytes(), CORE_PART)
    _ = workbook.write_bytes(mutated)

    # When / Then: central inventory detects ZIP encryption independently of CFB.
    with (
        pytest.raises(ExtractionError) as caught,
        open_package(workbook, ExtractionLimits()),
    ):
        pass
    assert caught.value.code is ErrorCode.ENCRYPTED_XLSX


def test_unknown_compression_method_maps_to_corrupt_package(tmp_path: Path) -> None:
    # Given: a genuine workbook with an unknown method on an optional member.
    workbook = make_workbook(tmp_path / "unknown-compression.xlsx")
    mutated = set_unknown_compression(workbook.read_bytes(), CORE_PART)
    _ = workbook.write_bytes(mutated)

    # When / Then: public reading translates unsupported compression as corruption.
    with (
        open_package(workbook, ExtractionLimits()) as package,
        pytest.raises(ExtractionError) as caught,
    ):
        _ = package.read_bytes(CORE_PART)
    assert caught.value.code is ErrorCode.CORRUPT_PACKAGE
    assert caught.value.source == CORE_PART
