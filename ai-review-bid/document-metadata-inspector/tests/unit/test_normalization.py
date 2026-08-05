"""Behavior tests for timestamp normalization and custom-value redaction."""

from typing import Literal

import pytest

from xlsx_metadata_forensics.models import TimestampValue
from xlsx_metadata_forensics.normalization import (
    inspect_timestamp,
    is_sensitive_name,
    normalize_timestamp,
    redact_sensitive_value,
)


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [
        ("2026-08-01", "2026-08-01"),
        ("2024-02-29", "2024-02-29"),
        ("2026-08-01T09:20:00Z", "2026-08-01T09:20:00+00:00"),
        ("2026-08-01T09:20:00+08:00", "2026-08-01T09:20:00+08:00"),
        ("2026-08-01T09:20:00-05:30", "2026-08-01T09:20:00-05:30"),
        ("2026-08-01T09:20:00+23:59", "2026-08-01T09:20:00+23:59"),
        ("2026-08-01T09:20:00", "2026-08-01T09:20:00"),
        ("2026-08-01T09:20:00.1Z", "2026-08-01T09:20:00.1+00:00"),
        (
            "2026-08-01T09:20:00.123456+08:00",
            "2026-08-01T09:20:00.123456+08:00",
        ),
    ],
)
def test_normalize_timestamp_preserves_exact_supported_semantics(
    raw: str,
    normalized: str,
) -> None:
    # Given: an exact accepted OOXML timestamp lexical form.
    # When: the public normalizer inspects it.
    result = normalize_timestamp(raw)

    # Then: raw evidence and the exact canonical representation are retained.
    assert result == TimestampValue(raw=raw, normalized=normalized)
    assert inspect_timestamp(raw).valid is True


@pytest.mark.parametrize(
    "raw",
    [
        "not-a-date",
        " 2026-08-01T09:20:00Z",
        "2026-08-01T09:20:00Z ",
        "2026-08-01 09:20:00Z",
        "2026-08-01t09:20:00Z",
        "2026-08-01T09:20:00z",
        "2026-02-29",
        "2026-08-01T24:00:00Z",
        "2026-08-01T09:20:00.1234567Z",
        "2026-08-01T09:20:00+24:00",
        "2026-08-01T09:20:00+08:60",
        "2026-08-01T09:20:00-00:99",
        "2026-08-01Z",
    ],
)
def test_inspect_timestamp_rejects_nonconforming_text_without_fabrication(
    raw: str,
) -> None:
    # Given: text outside the exact timestamp grammar or calendar boundary.
    # When: the typed inspection seam validates it.
    result = inspect_timestamp(raw)

    # Then: invalidity is explicit and no date, midnight, or timezone is invented.
    assert result.valid is False
    assert result.value == TimestampValue(raw=raw, normalized=raw)


@pytest.mark.parametrize(
    "name",
    [
        "database_password",
        "backup-passwd",
        "admin pwd",
        "loginPassphrase",
        "APIKey",
        "apikey",
        "PassWord",
        "pAsSwOrD",
        "PASSWORD",
        "tOkEn",
        "sEcReT",
        "clientkey",
        "secretkey",
        "accessToken",
        "clientSecret",
        "service.credentials",
        "private-key",
        "databasePassword",
        "databasepassword",
        "API",
        "access",
        "private",
        "\uff21\uff30\uff29Key",
    ],
)
def test_redact_sensitive_value_recognizes_only_credential_name_tokens(
    name: str,
) -> None:
    # Given: a Unicode, separator, camel, or acronym credential property name.
    # When: its non-empty custom value is filtered.
    result = redact_sensitive_value(name, "must-not-escape")

    # Then: the complete value is replaced by the exact public marker.
    assert result == "***REDACTED***"


@pytest.mark.parametrize(
    "name",
    [
        "monkey",
        "monKey",
        "keyboard",
        "keyBoard",
        "hockey",
        "hocKey",
        "Secretariat",
        "tokenizer",
        "publicity",
    ],
)
def test_redact_sensitive_value_avoids_substring_false_positives(name: str) -> None:
    # Given: an ordinary property whose name only contains credential-like letters.
    # When: its custom value is filtered.
    result = redact_sensitive_value(name, "ordinary-value")

    # Then: token-aware matching leaves the complete value unchanged.
    assert result == "ordinary-value"


@pytest.mark.parametrize(
    ("base_name", "expected_classification"),
    [
        ("databasepassword", "sensitive"),
        ("apikey", "sensitive"),
        ("access", "sensitive"),
        ("private", "sensitive"),
        ("monkey", "ordinary"),
        ("keyboard", "ordinary"),
        ("hockey", "ordinary"),
    ],
)
def test_sensitive_name_classification_is_invariant_for_every_ascii_casing(
    base_name: str,
    expected_classification: Literal["sensitive", "ordinary"],
) -> None:
    # Given: every possible ASCII casing of one semantic property name.
    for mask in range(1 << len(base_name)):
        variant = "".join(
            character.upper() if mask & (1 << index) else character
            for index, character in enumerate(base_name)
        )

        # When / Then: casing alone never changes the classification.
        assert is_sensitive_name(variant) is (expected_classification == "sensitive")
