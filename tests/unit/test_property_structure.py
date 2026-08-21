"""Malformed mixed-content contracts for OOXML document properties."""

from pathlib import Path
from typing import Final

import pytest

from tests.property_support import (
    APP,
    CORE,
    CORE_NS,
    CUSTOM,
    CUSTOM_NS,
    DC_NS,
    EXT_NS,
    VT_NS,
    expected_property,
    read_facts,
)
from xlsx_metadata_forensics.models import ExtractionWarning

_VALUE_WARNING_MESSAGE: Final = "A document-property value has malformed content."
CORE_VALUE_MALFORMED_WARNING: Final = ExtractionWarning(
    code="property_value_malformed",
    message=_VALUE_WARNING_MESSAGE,
    source=CORE,
)
APP_VALUE_MALFORMED_WARNING: Final = CORE_VALUE_MALFORMED_WARNING.model_copy(
    update={"source": APP}
)
CUSTOM_MALFORMED_WARNING: Final = ExtractionWarning(
    code="custom_property_malformed",
    message="A custom document property is malformed.",
    source=CUSTOM,
)


@pytest.mark.parametrize(
    "malformed_title",
    [
        pytest.param(
            "<dc:title>visible<cp:inner>SENTINEL-NESTED</cp:inner>tail</dc:title>",
            id="nested-child",
        ),
        pytest.param(
            "<dc:title>visible</dc:title>SENTINEL-DIRECT-TAIL",
            id="non-whitespace-tail",
        ),
    ],
)
def test_read_properties_warns_and_skips_malformed_known_core_value(
    tmp_path: Path,
    malformed_title: str,
) -> None:
    # Given: one valid core fact beside malformed known scalar content.
    core = "".join(
        (
            f'<cp:coreProperties xmlns:cp="{CORE_NS}" xmlns:dc="{DC_NS}">',
            "<dc:creator>Alice</dc:creator>",
            malformed_title,
            "</cp:coreProperties>",
        )
    )

    # When: the well-formed but structurally invalid part is read.
    facts = read_facts(tmp_path, {CORE: core, APP: None, CUSTOM: None})

    # Then: valid evidence survives; the malformed field gets a fixed warning.
    assert facts.metadata.author == "Alice"
    assert facts.metadata.title is None
    assert facts.warnings == (CORE_VALUE_MALFORMED_WARNING,)
    assert "SENTINEL" not in repr(facts)


@pytest.mark.parametrize(
    "malformed_value",
    [
        pytest.param(
            "<Application>Excel<Inner>SENTINEL-APP</Inner>tail</Application>",
            id="application-nested",
        ),
        pytest.param(
            "<TotalTime>42<Inner>SENTINEL-TIME</Inner>tail</TotalTime>",
            id="total-time-nested",
        ),
    ],
)
def test_read_properties_warns_and_skips_malformed_known_app_value(
    tmp_path: Path,
    malformed_value: str,
) -> None:
    # Given: one valid extended fact beside malformed known scalar content.
    app = (
        f'<Properties xmlns="{EXT_NS}"><Company>Acme</Company>'
        f"{malformed_value}</Properties>"
    )

    # When: the well-formed but structurally invalid part is read.
    facts = read_facts(tmp_path, {CORE: None, APP: app, CUSTOM: None})

    # Then: valid evidence survives and no partial scalar is fabricated.
    assert facts.metadata.company == "Acme"
    assert facts.metadata.application is None
    assert facts.metadata.total_editing_minutes is None
    assert facts.warnings == (APP_VALUE_MALFORMED_WARNING,)
    assert "SENTINEL" not in repr(facts)


def test_read_properties_warns_and_skips_custom_prefix_and_tail_content(
    tmp_path: Path,
) -> None:
    # Given: malformed text around VT children beside one valid custom property.
    custom = "".join(
        (
            f'<Properties xmlns="{CUSTOM_NS}" xmlns:vt="{VT_NS}">',
            '<property name="Prefix">SENTINEL-PREFIX<vt:i4>7</vt:i4></property>',
            '<property name="Good"><vt:i4>8</vt:i4></property>',
            '<property name="Tail"><vt:i4>9</vt:i4>SENTINEL-TAIL</property>',
            "</Properties>",
        )
    )

    # When: the well-formed custom part is read.
    facts = read_facts(tmp_path, {CORE: None, APP: None, CUSTOM: custom})

    # Then: only the valid property survives and one warning is deduplicated.
    assert facts.custom_properties == expected_property("Good", "i4", 8)
    assert facts.warnings == (CUSTOM_MALFORMED_WARNING,)
    assert "SENTINEL" not in repr(facts)
