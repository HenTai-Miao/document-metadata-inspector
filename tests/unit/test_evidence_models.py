"""Contract tests for immutable multi-engine evidence reports."""

import pytest
from pydantic import ValidationError

from document_metadata_inspector.formats import identify_declared_format
from document_metadata_inspector.models import (
    ComparisonReport,
    DocumentReport,
    DocumentStatus,
    EvidenceObservation,
    ParserRun,
    ParserStatus,
    ScanReport,
    TraceMatch,
)
from document_metadata_inspector.normalization import normalize_identity_text


def _observation() -> EvidenceObservation:
    return EvidenceObservation(
        canonical_name="author",
        raw_name="dc:creator",
        raw_value=("  Alice  ", "ALICE"),
        normalized_value=("alice", "alice"),
        value_type="string_list",
        source_kind="opc_core_properties",
        location="docProps/core.xml",
        parser_name="native-opc",
        parser_version="1",
    )


def test_evidence_preserves_raw_and_normalized_values() -> None:
    observation = _observation()

    assert observation.raw_value == ("  Alice  ", "ALICE")
    assert observation.normalized_value == ("alice", "alice")


def test_evidence_models_are_frozen_and_reject_unknown_fields() -> None:
    observation = _observation()

    with pytest.raises(ValidationError):
        observation.canonical_name = "manager"

    payload = observation.model_dump()
    payload["unexpected"] = True
    with pytest.raises(ValidationError):
        _ = EvidenceObservation.model_validate(payload)


def test_tuple_fields_serialize_stably_to_json_arrays() -> None:
    payload = _observation().model_dump(mode="json")

    assert payload["raw_value"] == ["  Alice  ", "ALICE"]
    assert payload["normalized_value"] == ["alice", "alice"]
    assert payload["warnings"] == []


def test_report_models_compose_without_losing_parser_provenance() -> None:
    observation = _observation()
    parser_run = ParserRun(
        parser_name="native-opc",
        parser_version="1",
        status=ParserStatus.SUCCEEDED,
        observations=(observation,),
    )
    document = DocumentReport(
        display_name="bid.docx",
        size_bytes=123,
        sha256="0" * 64,
        identity=identify_declared_format("bid.docx"),
        status=DocumentStatus.COMPLETE,
        observations=(observation,),
        parser_runs=(parser_run,),
    )
    scan = ScanReport(documents=(document,))
    match = TraceMatch(
        canonical_name="author",
        normalized_value="alice",
        document_names=("bid.docx", "other.pdf"),
        evidence_count=2,
    )
    comparison = ComparisonReport(documents=(document,), matches=(match,))

    assert scan.documents[0].parser_runs[0].observations == (observation,)
    assert comparison.matches[0].normalized_value == "alice"


def test_identity_normalization_is_exact_and_conservative() -> None:
    assert normalize_identity_text("  \uff21lice\t  ZHANG  ") == "alice zhang"
    assert normalize_identity_text("张-三") == "张-三"
