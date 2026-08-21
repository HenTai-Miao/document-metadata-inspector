"""Read-budget and streaming tests for OOXML package access."""

from hashlib import sha256
from pathlib import Path
from zipfile import ZipExtFile, ZipFile

import pytest

from tests.factories import make_workbook, rewrite_package
from xlsx_metadata_forensics.errors import ErrorCode, ExtractionError
from xlsx_metadata_forensics.models import ExtractionLimits
from xlsx_metadata_forensics.ooxml.package import open_package

VALIDATION_PARTS = (
    "[Content_Types].xml",
    "_rels/.rels",
    "xl/workbook.xml",
)


def _part_sizes(path: Path, names: tuple[str, ...]) -> tuple[int, ...]:
    with ZipFile(path, "r") as archive:
        return tuple(archive.getinfo(name).file_size for name in names)


def test_validation_reads_fail_when_total_budget_is_one_byte_short(
    tmp_path: Path,
) -> None:
    # Given: a genuine workbook and a budget one byte below critical XML sizes.
    workbook = make_workbook(tmp_path / "validation-budget.xlsx")
    validation_bytes = sum(_part_sizes(workbook, VALIDATION_PARTS))
    limits = ExtractionLimits(max_total_read_bytes=validation_bytes - 1)

    # When / Then: package validation itself exhausts the shared read budget.
    with pytest.raises(ExtractionError) as caught, open_package(workbook, limits):
        pass
    assert caught.value.code is ErrorCode.FILE_TOO_LARGE


def test_validation_reads_leave_no_hidden_fresh_budget(tmp_path: Path) -> None:
    # Given: a total budget exactly equal to all critical validation XML.
    workbook = make_workbook(tmp_path / "exact-validation-budget.xlsx")
    validation_bytes = sum(_part_sizes(workbook, VALIDATION_PARTS))
    limits = ExtractionLimits(max_total_read_bytes=validation_bytes)

    # When: a caller reads another non-empty part after validation succeeds.
    with (
        open_package(workbook, limits) as package,
        pytest.raises(ExtractionError) as caught,
    ):
        _ = package.read_bytes("[Content_Types].xml")

    # Then: validation and public reads demonstrably share one budget.
    assert caught.value.code is ErrorCode.FILE_TOO_LARGE


def test_xml_part_limit_is_checked_before_reading_optional_xml(tmp_path: Path) -> None:
    # Given: optional well-formed XML larger than every critical XML part.
    workbook = make_workbook(tmp_path / "large-xml.xlsx")
    max_critical_size = max(_part_sizes(workbook, VALIDATION_PARTS))
    payload = b"<root>" + (b"x" * max_critical_size) + b"</root>"
    rewrite_package(workbook, {}, {"custom/large.xml": payload})
    limits = ExtractionLimits(max_xml_part_bytes=max_critical_size)

    # When / Then: the per-XML limit rejects the present part with a typed code.
    with (
        open_package(workbook, limits) as package,
        pytest.raises(ExtractionError) as caught,
    ):
        _ = package.read_xml("custom/large.xml")
    assert caught.value.code is ErrorCode.FILE_TOO_LARGE


def test_rejected_oversized_xml_does_not_consume_unread_budget(tmp_path: Path) -> None:
    # Given: an XML part over its part limit but within the remaining total budget.
    workbook = make_workbook(tmp_path / "xml-preflight.xlsx")
    critical_sizes = _part_sizes(workbook, VALIDATION_PARTS)
    max_critical_size = max(critical_sizes)
    payload = b"<root>" + (b"x" * max_critical_size) + b"</root>"
    rewrite_package(workbook, {}, {"custom/large.xml": payload})
    limits = ExtractionLimits(
        max_xml_part_bytes=max_critical_size,
        max_total_read_bytes=sum(critical_sizes) + len(payload),
    )

    # When: XML preflight rejects the part, then a byte read requests the same data.
    with open_package(workbook, limits) as package:
        with pytest.raises(ExtractionError):
            _ = package.read_xml("custom/large.xml")
        binary = package.read_bytes("custom/large.xml")

    # Then: only bytes actually read were charged to the shared budget.
    assert binary == payload


def test_read_and_hash_operations_share_one_uncompressed_budget(tmp_path: Path) -> None:
    # Given: a binary part and budget for validation plus exactly one full read.
    workbook = make_workbook(tmp_path / "shared-budget.xlsx")
    payload = b"forensic-payload" * 5_000
    rewrite_package(workbook, {}, {"xl/embeddings/evidence.bin": payload})
    validation_bytes = sum(_part_sizes(workbook, VALIDATION_PARTS))
    limits = ExtractionLimits(
        max_total_read_bytes=validation_bytes + len(payload),
    )

    # When: bytes are read once and then the same part is hashed.
    with open_package(workbook, limits) as package:
        first_read = package.read_bytes("xl/embeddings/evidence.bin")
        with pytest.raises(ExtractionError) as caught:
            _ = package.sha256_part("xl/embeddings/evidence.bin")

    # Then: the read succeeds and hashing cannot obtain a separate budget.
    assert first_read == payload
    assert caught.value.code is ErrorCode.FILE_TOO_LARGE


def test_sha256_part_streams_bounded_chunks_and_returns_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a part larger than one normal streaming chunk and tracked ZIP reads.
    workbook = make_workbook(tmp_path / "streamed-hash.xlsx")
    payload = b"0123456789abcdef" * 20_000
    rewrite_package(workbook, {}, {"xl/embeddings/evidence.bin": payload})
    original_read = ZipExtFile.read
    requested_sizes: list[int] = []

    def tracked_read(stream: ZipExtFile, size: int = -1) -> bytes:
        requested_sizes.append(size)
        return original_read(stream, size)

    monkeypatch.setattr(ZipExtFile, "read", tracked_read)

    # When: the package computes the part digest.
    with open_package(workbook, ExtractionLimits()) as package:
        requested_sizes.clear()
        digest = package.sha256_part("xl/embeddings/evidence.bin")

    # Then: no unbounded or whole-part read was requested.
    assert digest == sha256(payload).hexdigest()
    assert requested_sizes
    assert all(0 < size <= 64 * 1024 for size in requested_sizes)


def test_every_successful_hash_byte_is_charged_again_on_later_read(
    tmp_path: Path,
) -> None:
    # Given: a budget that fits validation and one complete hash only.
    workbook = make_workbook(tmp_path / "hash-budget.xlsx")
    payload = b"hash-me" * 10_000
    rewrite_package(workbook, {}, {"xl/embeddings/evidence.bin": payload})
    validation_bytes = sum(_part_sizes(workbook, VALIDATION_PARTS))
    limits = ExtractionLimits(max_total_read_bytes=validation_bytes + len(payload))

    # When: hashing succeeds and a later byte read requests the same part.
    with open_package(workbook, limits) as package:
        digest = package.sha256_part("xl/embeddings/evidence.bin")
        with pytest.raises(ExtractionError) as caught:
            _ = package.read_bytes("xl/embeddings/evidence.bin")

    # Then: hashed bytes consumed the entire caller-visible budget.
    assert digest == sha256(payload).hexdigest()
    assert caught.value.code is ErrorCode.FILE_TOO_LARGE


def test_typed_read_error_propagates_through_owning_context(tmp_path: Path) -> None:
    # Given: a malformed optional XML part and an uncaught resource-backed read.
    workbook = make_workbook(tmp_path / "propagated-error.xlsx")
    rewrite_package(workbook, {}, {"custom/broken.xml": b"<broken>"})

    def read_malformed_part() -> None:
        with open_package(workbook, ExtractionLimits()) as package:
            _ = package.read_xml("custom/broken.xml")

    # When / Then: context cleanup preserves the public typed failure.
    with pytest.raises(ExtractionError) as caught:
        read_malformed_part()
    assert caught.value.code is ErrorCode.EXTRACTION_FAILED
    assert caught.value.source == "custom/broken.xml"


def test_validation_failure_closes_acquired_zip_resource(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a valid non-XLSX ZIP and an observer on archive close completion.
    fake = tmp_path / "not-xlsx.zip"
    with ZipFile(fake, "w") as archive:
        archive.writestr("note.txt", b"not a workbook")
    original_close = ZipFile.close
    closed_resources: set[int] = set()

    def tracked_close(archive: ZipFile) -> None:
        original_close(archive)
        closed_resources.add(id(archive))

    monkeypatch.setattr(ZipFile, "close", tracked_close)

    # When: validation fails after the ZIP resource has been acquired.
    with pytest.raises(ExtractionError), open_package(fake, ExtractionLimits()):
        pass

    # Then: exactly one acquired ZIP resource completed closure.
    assert len(closed_resources) == 1
