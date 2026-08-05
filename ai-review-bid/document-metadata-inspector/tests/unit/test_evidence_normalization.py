"""Canonical-aware normalization shared by independent metadata parsers."""

from document_metadata_inspector.normalization import normalize_evidence_value


def test_equivalent_exif_and_iso_timestamps_share_one_normalized_value() -> None:
    exif = normalize_evidence_value("created_at", "2024:07:11 07:07:00Z")
    iso = normalize_evidence_value("created_at", "2024-07-11T07:07:00Z")

    assert exif == "2024-07-11T07:07:00+00:00"
    assert exif == iso


def test_timestamp_normalization_never_invents_a_timezone() -> None:
    naive_exif = normalize_evidence_value("modified_at", "2026:08:04 18:07:49")
    naive_iso = normalize_evidence_value("modified_at", "2026-08-04T18:07:49")
    utc = normalize_evidence_value("modified_at", "2026-08-04T18:07:49Z")

    assert naive_exif == naive_iso == "2026-08-04T18:07:49"
    assert utc == "2026-08-04T18:07:49+00:00"
    assert naive_exif != utc


def test_numeric_identity_and_revision_values_match_their_text_forms() -> None:
    assert normalize_evidence_value("last_modified_by", 32522) == "32522"
    assert normalize_evidence_value("last_modified_by", "32522") == "32522"
    assert normalize_evidence_value("revision", 0) == "0"
    assert normalize_evidence_value("revision", "0") == "0"


def test_office_application_versions_match_across_storage_encodings() -> None:
    assert normalize_evidence_value("application_version", "16.0300") == "16.03"
    assert normalize_evidence_value("application_version", 16.03) == "16.03"
    assert normalize_evidence_value("application_version", 1_048_576) == "16"


def test_generic_numeric_metadata_retains_its_json_type() -> None:
    assert normalize_evidence_value("page_count", 12) == 12


def test_unknown_string_metadata_remains_case_and_whitespace_sensitive() -> None:
    value = "  AbC/Case-Sensitive-ID  "

    assert normalize_evidence_value("vendor.opaque_identifier", value) == value
