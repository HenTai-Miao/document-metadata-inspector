"""Native OLE identity and property-set adapter tests."""

from base64 import b64encode
from hashlib import sha256
from pathlib import Path

import pytest

from document_metadata_inspector.formats import identify_format
from document_metadata_inspector.models import InspectionLimits, ParserRun, ParserStatus
from document_metadata_inspector.native import extract_native_office
from document_metadata_inspector.native.office_properties import read_ole_property_set
from document_metadata_inspector.source import open_source_snapshot

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _extract(path: Path) -> ParserRun:
    with open_source_snapshot(path, InspectionLimits()) as snapshot:
        header = snapshot.stream.read(1024)
        _ = snapshot.stream.seek(0)
        identity = identify_format(path, header)
        return extract_native_office(snapshot, identity)


@pytest.mark.parametrize("suffix", ["xls", "xlt"])
def test_excel_ole_extracts_known_and_raw_property_evidence(
    tmp_path: Path,
    suffix: str,
) -> None:
    path = tmp_path / f"metadata.{suffix}"
    _ = path.write_bytes((_FIXTURES / f"metadata.{suffix}").read_bytes())

    run = _extract(path)

    assert run.status is ParserStatus.SUCCEEDED
    author = next(item for item in run.observations if item.canonical_name == "author")
    assert author.raw_value == "Alice Analyst"
    assert author.normalized_value == "alice analyst"
    assert author.source_kind == "ole_property_set"
    assert any(item.raw_name.startswith("property:") for item in run.observations)


def test_word_suffix_cannot_relabel_an_excel_ole_container(tmp_path: Path) -> None:
    path = tmp_path / "renamed.doc"
    _ = path.write_bytes((_FIXTURES / "metadata.xls").read_bytes())

    run = _extract(path)

    assert run.status is ParserStatus.FAILED
    assert run.error_code == "format_mismatch"


def test_ole_codepage_decodes_legacy_chinese_property_strings() -> None:
    observations = read_ole_property_set(
        {
            1: 10008,
            4: b"\xd6\xd0\xb6\xfe\xb2\xa1",
        },
        location="\x05SummaryInformation",
        document_summary=False,
    )

    author = next(item for item in observations if item.canonical_name == "author")
    assert author.raw_value == "中二病"
    assert author.normalized_value == "中二病"


def test_ole_application_version_keeps_raw_packed_value_and_normalizes_it() -> None:
    observations = read_ole_property_set(
        {1: 10008, 23: 1_048_576},
        location="\x05DocumentSummaryInformation",
        document_summary=True,
    )

    version = next(
        item for item in observations if item.canonical_name == "application_version"
    )
    assert version.raw_value == 1_048_576
    assert version.normalized_value == "16"


def test_uncertain_ole_byte_strings_preserve_original_byte_evidence() -> None:
    payload = b"\xff\x81"

    observations = read_ole_property_set(
        {1: 777, 4: payload},
        location="\x05SummaryInformation",
        document_summary=False,
    )

    author = next(item for item in observations if item.canonical_name == "author")
    assert author.raw_value == {
        "decoded_text": "��",
        "encoding": "utf-8-replacement",
        "decoding_status": "uncertain",
        "byte_length": len(payload),
        "sha256": sha256(payload).hexdigest(),
        "bytes_base64": b64encode(payload).decode("ascii"),
        "base64_complete": True,
    }
    assert author.normalized_value == author.raw_value
    assert author.warnings == ("ole_string_decode_uncertain",)
