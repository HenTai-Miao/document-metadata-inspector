"""Real-package behavior tests for OOXML document properties."""

from dataclasses import FrozenInstanceError
from pathlib import Path
from zipfile import ZipFile

import pytest

from tests.property_support import (
    APP,
    APP_UNREADABLE_WARNING,
    APP_XML,
    CORE,
    CORE_NS,
    CORE_XML,
    CUSTOM,
    CUSTOM_NS,
    CUSTOM_UNREADABLE_WARNING,
    DCTERMS_NS,
    EXPECTED_METADATA,
    EXPECTED_REDACTED,
    INVALID_SCALAR_WARNING,
    INVALID_SCALARS,
    OPTIONAL_FAILURE_CASES,
    ORDER_ENTRIES,
    ORDER_WARNINGS,
    PROPERTY_PARTS,
    SENSITIVE_ENTRIES,
    VALID_SCALARS,
    VALIDATION_PARTS,
    VT_NS,
    app_total_time_xml,
    custom_xml,
    expected_property,
    make_property_workbook,
    read_facts,
)
from xlsx_metadata_forensics.models import (
    DocumentMetadata,
    ExtractionLimits,
    ExtractionWarning,
    JsonScalar,
    TimestampValue,
)
from xlsx_metadata_forensics.ooxml.package import open_package
from xlsx_metadata_forensics.ooxml.properties import PropertyFacts, read_properties


def test_read_properties_maps_every_core_and_extended_field_exactly(
    tmp_path: Path,
) -> None:
    # Given: a genuine XLSX with controlled core and extended OOXML after save.
    # When: only its document-property parts are read.
    facts = read_facts(tmp_path, {CORE: CORE_XML, APP: APP_XML})

    # Then: every approved direct expanded name maps without invented defaults.
    assert facts.metadata == EXPECTED_METADATA
    assert facts.custom_properties == ()
    assert facts.warnings == ()


@pytest.mark.parametrize(("value_type", "raw", "expected"), VALID_SCALARS)
def test_read_properties_converts_each_supported_vt_scalar_family(
    tmp_path: Path,
    value_type: str,
    raw: str | None,
    expected: JsonScalar,
) -> None:
    # Given: one genuine package carrying one supported VT scalar spelling.
    custom = custom_xml((("Evidence", value_type, raw),))

    # When: the custom property is converted.
    facts = read_facts(tmp_path, {CORE: None, APP: None, CUSTOM: custom})

    # Then: its exact JSON scalar type, VT provenance, and source are retained.
    assert facts.custom_properties == expected_property(
        "Evidence",
        value_type,
        expected,
    )
    assert type(facts.custom_properties[0].value) is type(expected)
    assert facts.warnings == ()


@pytest.mark.parametrize(("value_type", "raw"), INVALID_SCALARS)
def test_read_properties_retains_invalid_known_scalars_as_warning_text(
    tmp_path: Path,
    value_type: str,
    raw: str,
) -> None:
    # Given: a known VT scalar with invalid lexical text or width.
    custom = custom_xml((("Bad", value_type, raw),))

    # When: its package is inspected.
    facts = read_facts(tmp_path, {CORE: None, APP: None, CUSTOM: custom})

    # Then: raw text survives and the fixed warning leaks no value.
    assert facts.custom_properties == expected_property("Bad", value_type, raw)
    assert facts.warnings == (INVALID_SCALAR_WARNING,)
    assert raw not in facts.warnings[0].message


def test_read_properties_redacts_sensitive_non_none_scalars_after_conversion(
    tmp_path: Path,
) -> None:
    # Given: sensitive names spanning strings, numbers, booleans, time, and empty.
    custom = custom_xml(SENSITIVE_ENTRIES)

    # When: custom values cross the reader boundary.
    facts = read_facts(tmp_path, {CORE: None, APP: None, CUSTOM: custom})

    # Then: every non-None value is wholly redacted while provenance remains intact.
    assert (
        tuple(
            (item.name, item.value_type, item.value, item.source)
            for item in facts.custom_properties
        )
        == EXPECTED_REDACTED
    )
    assert "secret" not in repr(facts)


def test_read_properties_warns_for_unknown_type_and_skips_malformed_evidence(
    tmp_path: Path,
) -> None:
    # Given: unknown correct-VT evidence plus malformed and wrong-namespace properties.
    body = "".join(
        (
            f'<property name="Unknown"><vt:blob xmlns:vt="{VT_NS}">',
            "opaque</vt:blob></property>",
            '<property name="Wrong"><x:i4 xmlns:x="urn:wrong">7</x:i4></property>',
            f'<property><vt:i4 xmlns:vt="{VT_NS}">8</vt:i4></property>',
            '<property name="Missing" />',
        )
    )
    custom = f'<Properties xmlns="{CUSTOM_NS}" xmlns:vt="{VT_NS}">{body}</Properties>'

    # When: independent custom-property evidence is read.
    facts = read_facts(tmp_path, {CORE: None, APP: None, CUSTOM: custom})

    # Then: unknown text survives while malformed items are skipped deterministically.
    assert facts.custom_properties == expected_property("Unknown", "blob", "opaque")
    assert tuple(warning.code for warning in facts.warnings) == (
        "custom_property_malformed",
        "custom_property_type_unknown",
    )


def test_read_properties_contains_huge_total_time_and_preserves_duplicate_order(
    tmp_path: Path,
) -> None:
    # Given: opposite XML orders with duplicate evidence and repeated warnings.
    core = "".join(
        (
            f'<cp:coreProperties xmlns:cp="{CORE_NS}" ',
            f'xmlns:dcterms="{DCTERMS_NS}">',
            "<dcterms:created>bad</dcterms:created>",
            "<dcterms:modified>bad</dcterms:modified>",
            "</cp:coreProperties>",
        )
    )
    app = app_total_time_xml("9" * 5000)

    # When: both real packages are read independently.
    first = read_facts(
        tmp_path / "first",
        {CORE: core, APP: app, CUSTOM: custom_xml(ORDER_ENTRIES)},
    )
    second = read_facts(
        tmp_path / "second",
        {CORE: core, APP: app, CUSTOM: custom_xml(tuple(reversed(ORDER_ENTRIES)))},
    )

    # Then: huge TotalTime is contained and ordering ignores XML order.
    assert first == second
    assert first.metadata.total_editing_minutes is None
    assert tuple(item.name for item in first.custom_properties) == (
        "Alpha",
        "alpha",
        "Dup",
        "Dup",
        "zeta",
    )
    assert first.warnings == ORDER_WARNINGS


@pytest.mark.parametrize("part", PROPERTY_PARTS)
def test_read_properties_rejects_wrong_root_namespace_without_local_fallback(
    tmp_path: Path,
    part: str,
) -> None:
    # Given: a familiar local root under an unverified namespace.
    local = "coreProperties" if part == CORE else "Properties"

    # When: the wrong-namespace part is read without other optional parts.
    facts = read_facts(
        tmp_path,
        {CORE: None, APP: None, part: f'<{local} xmlns="urn:wrong" />'},
    )

    # Then: it contributes no evidence and exactly one fixed-source warning.
    assert facts == PropertyFacts(
        DocumentMetadata(),
        (),
        (
            ExtractionWarning(
                code="property_part_invalid",
                message="A document-property part has an invalid root.",
                source=part,
            ),
        ),
    )


@pytest.mark.parametrize(("custom", "limits"), OPTIONAL_FAILURE_CASES)
def test_read_properties_contains_optional_failures_and_keeps_other_parts(
    tmp_path: Path,
    custom: str,
    limits: ExtractionLimits,
) -> None:
    # Given: valid core/app beside a malformed or oversized custom part.
    # When: the optional failure is contained at the reader boundary.
    facts = read_facts(
        tmp_path,
        {CORE: CORE_XML, APP: APP_XML, CUSTOM: custom},
        limits,
    )

    # Then: unrelated metadata survives and the warning remains sanitized.
    assert facts.metadata.author == "Alice"
    assert facts.metadata.application == "Excel"
    assert facts.custom_properties == ()
    assert facts.warnings == (CUSTOM_UNREADABLE_WARNING,)


def test_read_properties_treats_missing_parts_as_normal_and_returns_frozen_tuples(
    tmp_path: Path,
) -> None:
    # Given: a genuine workbook with every optional property part removed.
    # When: document-property facts are read.
    facts = read_facts(tmp_path, {CORE: None, APP: None, CUSTOM: None})

    # Then: absence is silent and the internal contract is frozen and slotted.
    assert facts == PropertyFacts(DocumentMetadata(), (), ())
    assert type(facts.custom_properties) is tuple
    assert type(facts.warnings) is tuple
    assert not hasattr(facts, "__dict__")
    field_name = "warnings"
    with pytest.raises(FrozenInstanceError):
        setattr(facts, field_name, ())


def test_read_properties_retains_invalid_core_timestamp_raw_text(
    tmp_path: Path,
) -> None:
    # Given: a direct core timestamp with invalid lexical text.
    core = "".join(
        (
            f'<cp:coreProperties xmlns:cp="{CORE_NS}" ',
            f'xmlns:dcterms="{DCTERMS_NS}">',
            "<dcterms:created>invalid-created</dcterms:created>",
            "</cp:coreProperties>",
        )
    )

    # When: the core property part is read.
    facts = read_facts(tmp_path, {CORE: core, APP: None, CUSTOM: None})

    # Then: raw evidence is retained exactly and the field-level warning is safe.
    assert facts.metadata.created_at == TimestampValue(
        raw="invalid-created",
        normalized="invalid-created",
    )
    assert tuple(warning.code for warning in facts.warnings) == (
        "property_timestamp_invalid",
    )
    assert "invalid-created" not in facts.warnings[0].message


def test_read_properties_ignores_nested_known_core_children(tmp_path: Path) -> None:
    # Given: a known core field nested below an unrecognized direct child.
    core = "".join(
        (
            f'<cp:coreProperties xmlns:cp="{CORE_NS}" ',
            'xmlns:dc="http://purl.org/dc/elements/1.1/">',
            "<cp:wrapper><dc:title>Nested title</dc:title></cp:wrapper>",
            "</cp:coreProperties>",
        )
    )

    # When: the core property part is read.
    facts = read_facts(tmp_path, {CORE: core, APP: None, CUSTOM: None})

    # Then: parsing remains direct-child-only and does not invent nested evidence.
    assert facts.metadata.title is None
    assert facts.warnings == ()


def test_read_properties_consumes_the_shared_package_read_budget(
    tmp_path: Path,
) -> None:
    # Given: exactly enough aggregate budget for identity validation and core XML.
    workbook = make_property_workbook(tmp_path, {CORE: CORE_XML, APP: APP_XML})
    with ZipFile(workbook, "r") as archive:
        validation_bytes = sum(
            archive.getinfo(part).file_size for part in VALIDATION_PARTS
        )
        core_bytes = archive.getinfo(CORE).file_size
    limits = ExtractionLimits(max_total_read_bytes=validation_bytes + core_bytes)

    # When: the reader attempts the next optional property part.
    with open_package(workbook, limits) as package:
        facts = read_properties(package)

    # Then: core survives while the exhausted app read becomes a fixed warning.
    assert facts.metadata.author == "Alice"
    assert facts.metadata.application is None
    assert facts.warnings == (APP_UNREADABLE_WARNING,)
