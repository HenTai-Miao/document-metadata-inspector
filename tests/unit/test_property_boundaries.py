"""Hostile lexical, lifecycle, and business-body isolation property tests."""

import ast
from inspect import getsource
from pathlib import Path
from textwrap import dedent
from typing import Final
from xml.etree.ElementTree import Element

import pytest

from tests.factories import make_workbook, rewrite_package
from tests.property_support import (
    APP,
    APP_XML,
    CORE,
    CORE_NS,
    CORE_XML,
    CUSTOM,
    DCTERMS_NS,
    INVALID_SCALAR_WARNING,
    TIMESTAMP_WARNING,
    app_total_time_xml,
    custom_xml,
    expected_property,
    make_property_workbook,
    read_facts,
)
from xlsx_metadata_forensics.errors import ErrorCode, ExtractionError
from xlsx_metadata_forensics.models import (
    ExtractionLimits,
    ExtractionWarning,
    TimestampValue,
)
from xlsx_metadata_forensics.ooxml._property_scalars import convert_scalar
from xlsx_metadata_forensics.ooxml.package import PackageView, open_package
from xlsx_metadata_forensics.ooxml.properties import read_properties

_TOTAL_TIME_WARNING: Final = ExtractionWarning(
    code="property_total_time_invalid",
    message="The extended TotalTime property is invalid.",
    source=APP,
)
_BUSINESS_PARTS: Final = (
    "xl/worksheets/sheet1.xml",
    "xl/sharedStrings.xml",
)


def test_scalar_dispatch_is_an_exhaustive_match_with_unreachable_fallback() -> None:
    # Given: the source of the bound supported-VT dispatcher.
    tree = ast.parse(dedent(getsource(convert_scalar)))

    # Then: the binding-required match and static unreachable guard remain present.
    assert any(isinstance(node, ast.Match) for node in ast.walk(tree))
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "assert_never"
        for node in ast.walk(tree)
    )


def test_read_properties_redacts_case_variants_and_compound_credential_names(
    tmp_path: Path,
) -> None:
    # Given: casing pairs for sensitive compounds and ordinary lookalikes.
    sensitive_names = (
        "PassWord",
        "pAsSwOrD",
        "tOkEn",
        "sEcReT",
        "clientkey",
        "secretkey",
        "databasePassword",
        "databasepassword",
        "API",
        "access",
        "private",
    )
    ordinary_names = (
        "monkey",
        "monKey",
        "keyboard",
        "keyBoard",
        "hockey",
        "hocKey",
    )
    redaction_probe = "SENTINEL-MUST-NOT-ESCAPE"
    ordinary = "ordinary-evidence"
    custom = custom_xml(
        tuple((name, "lpwstr", redaction_probe) for name in sensitive_names)
        + tuple((name, "lpwstr", ordinary) for name in ordinary_names)
    )

    # When: values cross the public real-package property boundary.
    facts = read_facts(tmp_path, {CORE: None, APP: None, CUSTOM: custom})

    # Then: casing cannot leak a credential or erase ordinary evidence.
    observed = {item.name: item.value for item in facts.custom_properties}
    assert {name: observed[name] for name in sensitive_names} == dict.fromkeys(
        sensitive_names,
        "***REDACTED***",
    )
    assert {name: observed[name] for name in ordinary_names} == dict.fromkeys(
        ordinary_names,
        ordinary,
    )
    assert redaction_probe not in repr(facts)
    assert facts.warnings == ()


@pytest.mark.parametrize("raw", ["hidden-text", "   "])
def test_read_properties_retains_nonempty_vt_empty_as_invalid_evidence(
    tmp_path: Path,
    raw: str,
) -> None:
    # Given: schema-invalid text hidden inside a nominally empty VT scalar.
    custom = custom_xml((("Evidence", "empty", raw),))

    # When: the real custom part is converted.
    facts = read_facts(tmp_path, {CORE: None, APP: None, CUSTOM: custom})

    # Then: exact raw evidence survives and one fixed warning marks invalidity.
    assert facts.custom_properties == expected_property("Evidence", "empty", raw)
    assert facts.warnings == (INVALID_SCALAR_WARNING,)
    assert raw not in facts.warnings[0].message


@pytest.mark.parametrize(
    ("value_type", "raw"),
    [
        pytest.param("i4", "\uff11\uff12", id="i4-fullwidth"),
        pytest.param("r8", "\uff11.\uff12\uff15", id="r8-fullwidth"),
        pytest.param("decimal", "\u0661\u0662.\u0665", id="decimal-arabic-indic"),
    ],
)
def test_read_properties_rejects_non_ascii_numeric_scalar_lexicals(
    tmp_path: Path,
    value_type: str,
    raw: str,
) -> None:
    # Given: a known numeric VT carrying non-ASCII decimal digits.
    custom = custom_xml((("Bad", value_type, raw),))

    # When: the real package is read through the public property boundary.
    facts = read_facts(tmp_path, {CORE: None, APP: None, CUSTOM: custom})

    # Then: exact evidence remains text and one fixed warning marks it invalid.
    assert facts.custom_properties == expected_property("Bad", value_type, raw)
    assert facts.warnings == (INVALID_SCALAR_WARNING,)
    assert raw not in facts.warnings[0].message


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param("\uff11\uff12", id="fullwidth"),
        pytest.param("\u0661\u0662", id="arabic-indic"),
    ],
)
def test_read_properties_rejects_non_ascii_total_time(
    tmp_path: Path,
    raw: str,
) -> None:
    # Given: extended TotalTime text outside the ASCII integer grammar.
    app = app_total_time_xml(raw)

    # When: the real package is read through the public property boundary.
    facts = read_facts(tmp_path, {CORE: None, APP: app, CUSTOM: None})

    # Then: no integer is fabricated and the warning leaks no payload.
    assert facts.metadata.total_editing_minutes is None
    assert facts.warnings == (_TOTAL_TIME_WARNING,)
    assert raw not in facts.warnings[0].message


@pytest.mark.parametrize(
    "raw",
    ["2026-08-01T09:20:00+08:60", "2026-08-01T09:20:00-00:99"],
)
def test_read_properties_retains_invalid_offset_raw_and_warns(
    tmp_path: Path,
    raw: str,
) -> None:
    # Given: a direct core timestamp with an overflowing offset minute.
    core = "".join(
        (
            f'<cp:coreProperties xmlns:cp="{CORE_NS}" ',
            f'xmlns:dcterms="{DCTERMS_NS}">',
            f"<dcterms:created>{raw}</dcterms:created>",
            "</cp:coreProperties>",
        )
    )

    # When: the real package is read through the public property boundary.
    facts = read_facts(tmp_path, {CORE: core, APP: None, CUSTOM: None})

    # Then: raw evidence survives without normalization and one warning is emitted.
    assert facts.metadata.created_at == TimestampValue(raw=raw, normalized=raw)
    assert facts.warnings == (TIMESTAMP_WARNING,)
    assert raw not in facts.warnings[0].message


def test_read_properties_propagates_closed_package_lifecycle_error(
    tmp_path: Path,
) -> None:
    # Given: a real package view retained beyond its owning context.
    workbook = make_property_workbook(
        tmp_path,
        {CORE: CORE_XML, APP: None, CUSTOM: None},
    )
    with open_package(workbook, ExtractionLimits()) as package:
        retained = package

    # When: the closed view is passed to the property reader.
    with pytest.raises(ExtractionError) as captured:
        _ = read_properties(retained)

    # Then: the source-less programming/lifecycle error remains visible.
    assert captured.value.code is ErrorCode.EXTRACTION_FAILED
    assert captured.value.source is None
    assert (
        captured.value.message == "Package reads cannot outlive their owning context."
    )


def test_read_properties_calls_only_fixed_property_xml_parts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: valid properties beside business bodies and forwarding read tracers.
    workbook = make_workbook(tmp_path / "body-read-trap.xlsx")
    body = "<root>business-body-trap</root>"
    rewrite_package(
        workbook,
        {CORE: CORE_XML, APP: APP_XML, _BUSINESS_PARTS[0]: body},
        {_BUSINESS_PARTS[1]: body},
    )
    xml_reads: list[str] = []
    byte_reads: list[str] = []
    hash_reads: list[str] = []
    original_read_xml = PackageView.read_xml
    original_read_bytes = PackageView.read_bytes
    original_sha256_part = PackageView.sha256_part

    def traced_read_xml(
        package: PackageView,
        name: str,
        *,
        required: bool = False,
    ) -> Element | None:
        xml_reads.append(name)
        if required:
            return original_read_xml(package, name, required=True)
        return original_read_xml(package, name, required=False)

    def traced_read_bytes(package: PackageView, name: str) -> bytes:
        byte_reads.append(name)
        return original_read_bytes(package, name)

    def traced_sha256_part(package: PackageView, name: str) -> str:
        hash_reads.append(name)
        return original_sha256_part(package, name)

    # When: property extraction runs through the real traced package view.
    with open_package(workbook, ExtractionLimits()) as package:
        monkeypatch.setattr(PackageView, "read_xml", traced_read_xml)
        monkeypatch.setattr(PackageView, "read_bytes", traced_read_bytes)
        monkeypatch.setattr(PackageView, "sha256_part", traced_sha256_part)
        facts = read_properties(package)

    # Then: only the fixed optional XML parts were called; no raw body was read.
    assert facts.metadata.title == "Bid"
    assert facts.metadata.application == "Excel"
    assert facts.warnings == ()
    assert xml_reads == [CORE, APP, CUSTOM]
    assert byte_reads == []
    assert hash_reads == []
