"""Contract tests for immutable extraction models."""

from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Literal

import pytest
from pydantic import ValidationError

from xlsx_metadata_forensics.models import (
    DocumentMetadata,
    ExtractionLimits,
    ExtractionReport,
    ExtractionRequest,
    ExtractionWarning,
    FileInfo,
    ForensicInfo,
    TimestampValue,
)

type SupportedExcelFormat = Literal[
    "xls", "xlsx", "xlsm", "xlsb", "xlt", "xltx", "xltm"
]


def test_extraction_limits_have_exact_security_defaults() -> None:
    # Given: no caller-supplied extraction limits.
    limits = ExtractionLimits()

    # When: each package safety budget is read.
    actual = (
        limits.max_file_bytes,
        limits.max_entries,
        limits.max_xml_part_bytes,
        limits.max_total_read_bytes,
    )

    # Then: every accepted design limit is represented in bytes or entries.
    assert actual == (
        100 * 1024 * 1024,
        10_000,
        16 * 1024 * 1024,
        256 * 1024 * 1024,
    )


def test_extraction_limits_reject_field_mutation() -> None:
    # Given: the independently decorated extraction limits dataclass.
    limits = ExtractionLimits()

    # When: mutation of one security budget is attempted.
    field_name = "max_entries"

    # Then: dataclass freezing rejects the mutation.
    with pytest.raises(FrozenInstanceError):
        setattr(limits, field_name, 1)


def test_extraction_limits_have_no_instance_dict() -> None:
    # Given: the independently decorated extraction limits dataclass.
    limits = ExtractionLimits()

    # When: its instance storage shape is observed.
    has_instance_dict = hasattr(limits, "__dict__")

    # Then: slots prevent per-instance dictionary storage.
    assert has_instance_dict is False


def test_extraction_request_uses_default_limits() -> None:
    # Given: a request using the default limits.
    request = ExtractionRequest(
        path=Path("fixture.xlsx"),
        display_name="报价表.xlsx",
    )

    # When: its implicit resource limits are observed.
    limits = request.limits

    # Then: the exact extraction-limit defaults are retained.
    assert limits == ExtractionLimits()


def test_extraction_request_rejects_field_mutation() -> None:
    # Given: the independently decorated extraction request dataclass.
    request = ExtractionRequest(
        path=Path("fixture.xlsx"),
        display_name="报价表.xlsx",
    )

    # When: mutation of its display name is attempted.
    field_name = "display_name"

    # Then: dataclass freezing rejects the mutation.
    with pytest.raises(FrozenInstanceError):
        setattr(request, field_name, "changed.xlsx")


def test_extraction_request_has_no_instance_dict() -> None:
    # Given: the independently decorated extraction request dataclass.
    request = ExtractionRequest(
        path=Path("fixture.xlsx"),
        display_name="报价表.xlsx",
    )

    # When: its instance storage shape is observed.
    has_instance_dict = hasattr(request, "__dict__")

    # Then: slots prevent per-instance dictionary storage.
    assert has_instance_dict is False


def test_complete_report_serializes_to_the_stable_json_contract() -> None:
    # Given: a complete successful report with empty forensic collections.
    report = ExtractionReport(
        file=FileInfo(
            name="报价表.xlsx",
            size_bytes=512,
            sha256="a" * 64,
            package_entry_count=7,
        ),
        metadata=DocumentMetadata(),
        forensics=ForensicInfo(),
    )

    # When: the immutable report crosses the JSON boundary.
    payload = report.model_dump(mode="json")

    # Then: fixed literals and tuple collections use their stable JSON forms.
    assert payload["success"] is True
    assert payload["schema_version"] == "1.0"
    assert payload["file"]["format"] == "xlsx"
    assert payload["forensics"]["hidden_sheets"] == []


@pytest.mark.parametrize(
    "format_name",
    ["xls", "xlsx", "xlsm", "xlsb", "xlt", "xltx", "xltm"],
)
def test_file_info_accepts_each_supported_excel_format(
    format_name: SupportedExcelFormat,
) -> None:
    # Given: one of the seven supported Excel-family format identities.

    # When: it crosses the immutable file-info boundary.
    info = FileInfo.model_validate(
        {
            "name": f"fixture.{format_name}",
            "size_bytes": 1,
            "sha256": "d" * 64,
            "format": format_name,
            "package_entry_count": 1,
        }
    )

    # Then: the exact format identity is retained in the JSON contract.
    assert info.model_dump(mode="json")["format"] == format_name


def test_extraction_report_is_immutable() -> None:
    # Given: a valid report boundary model.
    report = ExtractionReport(
        file=FileInfo(
            name="fixture.xlsx",
            size_bytes=1,
            sha256="b" * 64,
            package_entry_count=1,
        ),
        metadata=DocumentMetadata(),
        forensics=ForensicInfo(),
    )

    # When: mutation of its schema version is attempted.
    field_name = "schema_version"

    # Then: Pydantic rejects mutation of the frozen model.
    with pytest.raises(ValidationError, match="frozen_instance"):
        setattr(report, field_name, "2.0")


def test_timestamp_value_preserves_raw_and_normalized_serialization() -> None:
    # Given: an OOXML timestamp whose raw and normalized forms differ.
    timestamp = TimestampValue(
        raw="2026-08-03 12:34:56",
        normalized="2026-08-03T12:34:56",
    )

    # When: the timestamp crosses the JSON boundary.
    payload = timestamp.model_dump(mode="json")

    # Then: both required representations retain their exact field names.
    assert payload == {
        "raw": "2026-08-03 12:34:56",
        "normalized": "2026-08-03T12:34:56",
    }


def test_extraction_warning_serializes_as_a_typed_report_collection() -> None:
    # Given: one non-fatal warning in an otherwise valid report.
    warning = ExtractionWarning(
        code="metadata_part_skipped",
        message="One metadata part could not be parsed.",
        source="docProps/custom.xml",
    )
    report = ExtractionReport(
        file=FileInfo(
            name="fixture.xlsx",
            size_bytes=1,
            sha256="c" * 64,
            package_entry_count=1,
        ),
        metadata=DocumentMetadata(),
        forensics=ForensicInfo(),
        warnings=(warning,),
    )

    # When: the report crosses the JSON boundary.
    payload = report.model_dump(mode="json")

    # Then: the named warning model remains typed and serializes every field.
    assert report.warnings == (warning,)
    assert payload["warnings"] == [
        {
            "code": "metadata_part_skipped",
            "message": "One metadata part could not be parsed.",
            "source": "docProps/custom.xml",
        },
    ]
