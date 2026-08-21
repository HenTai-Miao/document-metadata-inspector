"""Hand-derived OOXML fixtures and package builders for property tests."""

from collections.abc import Mapping
from pathlib import Path
from typing import Final

import pytest

from tests.factories import ZipPayload, make_workbook, rewrite_package
from xlsx_metadata_forensics.models import (
    CustomProperty,
    DocumentMetadata,
    ExtractionLimits,
    ExtractionWarning,
    JsonScalar,
    TimestampValue,
)
from xlsx_metadata_forensics.ooxml.package import open_package
from xlsx_metadata_forensics.ooxml.properties import PropertyFacts, read_properties

type PropertyEntry = tuple[str, str, str | None]

CORE: Final = "docProps/core.xml"
APP: Final = "docProps/app.xml"
CUSTOM: Final = "docProps/custom.xml"
CORE_NS: Final = (
    "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
)
EXT_NS: Final = (
    "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
)
CUSTOM_NS: Final = (
    "http://schemas.openxmlformats.org/officeDocument/2006/custom-properties"
)
VT_NS: Final = "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"
DC_NS: Final = "http://purl.org/dc/elements/1.1/"
DCTERMS_NS: Final = "http://purl.org/dc/terms/"
VALIDATION_PARTS: Final = (
    "[Content_Types].xml",
    "_rels/.rels",
    "xl/workbook.xml",
)
PROPERTY_PARTS: Final = (CORE, APP, CUSTOM)

CORE_XML: Final = f"""<cp:coreProperties
 xmlns:cp="{CORE_NS}" xmlns:dc="{DC_NS}" xmlns:dcterms="{DCTERMS_NS}">
<dc:creator>Alice</dc:creator><cp:lastModifiedBy>Bob</cp:lastModifiedBy>
<dcterms:created>2026-08-01T09:20:00Z</dcterms:created>
<dcterms:modified>2026-08-02T10:30:00+08:00</dcterms:modified>
<cp:lastPrinted>2026-08-03</cp:lastPrinted><dc:title>Bid</dc:title>
<dc:subject>Review</dc:subject><dc:description>Evidence</dc:description>
<cp:keywords>xlsx,metadata</cp:keywords><cp:category>Audit</cp:category>
<cp:contentStatus>Final</cp:contentStatus><dc:identifier>ID-7</dc:identifier>
<dc:language>zh-CN</dc:language><cp:revision>9</cp:revision><cp:version>1.2</cp:version>
</cp:coreProperties>"""
APP_XML: Final = f"""<Properties xmlns="{EXT_NS}"><Application>Excel</Application>
<AppVersion>16.0300</AppVersion><Company>Acme</Company><Manager>Lin</Manager>
<Template>Normal.xltx</Template><TotalTime>42</TotalTime></Properties>"""

EXPECTED_METADATA: Final = DocumentMetadata(
    author="Alice",
    last_modified_by="Bob",
    created_at=TimestampValue(
        raw="2026-08-01T09:20:00Z",
        normalized="2026-08-01T09:20:00+00:00",
    ),
    modified_at=TimestampValue(
        raw="2026-08-02T10:30:00+08:00",
        normalized="2026-08-02T10:30:00+08:00",
    ),
    last_printed_at=TimestampValue(raw="2026-08-03", normalized="2026-08-03"),
    title="Bid",
    subject="Review",
    description="Evidence",
    keywords="xlsx,metadata",
    category="Audit",
    content_status="Final",
    identifier="ID-7",
    language="zh-CN",
    revision="9",
    version="1.2",
    application="Excel",
    application_version="16.0300",
    company="Acme",
    manager="Lin",
    template="Normal.xltx",
    total_editing_minutes=42,
)

VALID_SCALARS: Final[tuple[tuple[str, str | None, JsonScalar], ...]] = (
    ("lpwstr", "wide", "wide"),
    ("bstr", "basic", "basic"),
    ("i1", "-128", -128),
    ("i2", "32767", 32767),
    ("i4", "-2147483648", -2147483648),
    ("i8", "9223372036854775807", 9223372036854775807),
    ("int", "+7", 7),
    ("ui1", "255", 255),
    ("ui2", "65535", 65535),
    ("ui4", "4294967295", 4294967295),
    ("ui8", "18446744073709551615", 18446744073709551615),
    ("uint", "+8", 8),
    ("r4", "1.25", 1.25),
    ("r8", "-2.5e3", -2500.0),
    ("decimal", "+001.2300", "+001.2300"),
    ("bool", "true", True),
    ("bool", "false", False),
    ("bool", "1", True),
    ("bool", "0", False),
    ("filetime", "2026-08-01T09:20:00Z", "2026-08-01T09:20:00+00:00"),
    ("date", "2026-08-01", "2026-08-01"),
    ("empty", None, None),
)
INVALID_SCALARS: Final = (
    ("i1", "-129"),
    ("i2", "32768"),
    ("i4", "2147483648"),
    ("i8", "9223372036854775808"),
    pytest.param("i8", "9" * 5000, id="i8-python-digit-limit"),
    ("int", "1_000"),
    ("ui1", "-1"),
    ("ui2", "65536"),
    ("ui4", "4294967296"),
    ("ui8", "18446744073709551616"),
    ("uint", "-1"),
    ("r4", "NaN"),
    ("r8", "1e999"),
    ("decimal", "1e2"),
    ("bool", "TRUE"),
    ("filetime", "not-a-timestamp"),
)
SENSITIVE_ENTRIES: Final[tuple[PropertyEntry, ...]] = (
    ("database_password", "lpwstr", "secret"),
    ("APIKey", "i4", "7"),
    ("accessToken", "bool", "true"),
    ("clientSecret", "filetime", "2026-08-01T09:20:00Z"),
    ("emptySecret", "empty", None),
)
EXPECTED_REDACTED: Final = (
    ("accessToken", "bool", "***REDACTED***", CUSTOM),
    ("APIKey", "i4", "***REDACTED***", CUSTOM),
    ("clientSecret", "filetime", "***REDACTED***", CUSTOM),
    ("database_password", "lpwstr", "***REDACTED***", CUSTOM),
    ("emptySecret", "empty", None, CUSTOM),
)
ORDER_ENTRIES: Final[tuple[PropertyEntry, ...]] = (
    ("zeta", "blob", "text"),
    ("Alpha", "bool", "TRUE"),
    ("alpha", "i4", "2"),
    ("Dup", "lpwstr", "one"),
    ("Dup", "i4", "2"),
)
OVERSIZED_CUSTOM_XML: Final = "".join(
    (
        f'<Properties xmlns="{CUSTOM_NS}"><property name="Huge"><x>',
        "x" * 5000,
        "</x></property></Properties>",
    )
)
OPTIONAL_FAILURE_CASES: Final = (
    ("<broken>", ExtractionLimits()),
    (OVERSIZED_CUSTOM_XML, ExtractionLimits(max_xml_part_bytes=4096)),
)
INVALID_SCALAR_WARNING: Final = ExtractionWarning(
    code="custom_property_value_invalid",
    message="A custom document-property scalar is invalid.",
    source=CUSTOM,
)
TIMESTAMP_WARNING: Final = ExtractionWarning(
    code="property_timestamp_invalid",
    message="A document-property timestamp is invalid.",
    source=CORE,
)
CORE_UNREADABLE_WARNING: Final = ExtractionWarning(
    code="property_part_unreadable",
    message="An optional document-property part could not be read.",
    source=CORE,
)
CUSTOM_UNREADABLE_WARNING: Final = CORE_UNREADABLE_WARNING.model_copy(
    update={"source": CUSTOM}
)
APP_UNREADABLE_WARNING: Final = CORE_UNREADABLE_WARNING.model_copy(
    update={"source": APP}
)
ORDER_WARNINGS: Final = (
    ExtractionWarning(
        code="property_total_time_invalid",
        message="The extended TotalTime property is invalid.",
        source=APP,
    ),
    TIMESTAMP_WARNING,
    ExtractionWarning(
        code="custom_property_type_unknown",
        message="Custom property type 'blob' is unsupported.",
        source=CUSTOM,
    ),
    INVALID_SCALAR_WARNING,
)


def app_total_time_xml(raw: str) -> str:
    return f'<Properties xmlns="{EXT_NS}"><TotalTime>{raw}</TotalTime></Properties>'


def _property_xml(pid: int, entry: PropertyEntry) -> str:
    name, value_type, raw = entry
    text = "" if raw is None else raw
    return "".join(
        (
            f'<property fmtid="fmt" pid="{pid}" name="{name}">',
            f"<vt:{value_type}>{text}</vt:{value_type}>",
            "</property>",
        )
    )


def custom_xml(entries: tuple[PropertyEntry, ...]) -> str:
    """Build controlled custom-property XML from hand-authored test data."""
    properties = "".join(
        _property_xml(pid, entry) for pid, entry in enumerate(entries, 2)
    )
    return "".join(
        (
            f'<Properties xmlns="{CUSTOM_NS}" xmlns:vt="{VT_NS}">',
            properties,
            "</Properties>",
        )
    )


def make_property_workbook(
    directory: Path,
    parts: Mapping[str, ZipPayload | None],
) -> Path:
    """Create a genuine XLSX and rewrite only controlled property parts."""
    directory.mkdir(parents=True, exist_ok=True)
    workbook = make_workbook(directory / "metadata.xlsx")
    replacements = {name: payload for name, payload in parts.items() if name != CUSTOM}
    custom = parts.get(CUSTOM)
    additions: dict[str, ZipPayload] = {} if custom is None else {CUSTOM: custom}
    rewrite_package(workbook, replacements, additions)
    return workbook


def read_facts(
    directory: Path,
    parts: Mapping[str, ZipPayload | None],
    limits: ExtractionLimits | None = None,
) -> PropertyFacts:
    """Read property facts from a genuine controlled XLSX package."""
    workbook = make_property_workbook(directory, parts)
    effective_limits = ExtractionLimits() if limits is None else limits
    with open_package(workbook, effective_limits) as package:
        return read_properties(package)


def expected_property(
    name: str,
    value_type: str,
    value: JsonScalar,
) -> tuple[CustomProperty, ...]:
    """Return one hand-specified expected custom-property tuple."""
    return (
        CustomProperty(
            name=name,
            value_type=value_type,
            value=value,
            source=CUSTOM,
        ),
    )
