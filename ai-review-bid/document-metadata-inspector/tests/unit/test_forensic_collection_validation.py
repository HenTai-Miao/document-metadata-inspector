"""Behavior tests for forensic collection validation boundaries."""

import pytest
from pydantic import ValidationError

from xlsx_metadata_forensics.models import ExternalLink, ForensicInfo, HiddenSheet


def test_forensic_collection_rejects_a_wrong_named_model() -> None:
    # Given: a valid named model belonging to a different forensic collection.
    wrong_item = ExternalLink(
        target="[redacted-external-target]",
        relationship_type="externalLink",
        source="xl/_rels/workbook.xml.rels",
    )
    raw_input = {"hidden_sheets": (wrong_item,)}

    # When/Then: the wrong named model cannot inhabit hidden-sheet evidence.
    with pytest.raises(ValidationError, match=r"hidden_sheets\.0"):
        _ = ForensicInfo.model_validate(raw_input)


def test_forensic_collection_rejects_a_wrong_scalar() -> None:
    # Given: a scalar where one named hidden-sheet model is required.
    raw_input = {"hidden_sheets": ("Audit",)}

    # When/Then: the scalar cannot inhabit hidden-sheet evidence.
    with pytest.raises(ValidationError, match=r"hidden_sheets\.0"):
        _ = ForensicInfo.model_validate(raw_input)


def test_valid_raw_mapping_becomes_the_exact_named_item_model() -> None:
    # Given: structurally valid raw input for one hidden-sheet item.
    raw_input = {
        "hidden_sheets": (
            {
                "name": "Audit",
                "state": "veryHidden",
                "source": "xl/workbook.xml",
            },
        ),
    }

    # When: the untrusted mapping crosses the Pydantic boundary.
    forensics = ForensicInfo.model_validate(raw_input)

    # Then: validation retains a tuple containing the exact named model.
    assert type(forensics.hidden_sheets) is tuple
    assert type(forensics.hidden_sheets[0]) is HiddenSheet
    assert forensics.hidden_sheets == (
        HiddenSheet(
            name="Audit",
            state="veryHidden",
            source="xl/workbook.xml",
        ),
    )
