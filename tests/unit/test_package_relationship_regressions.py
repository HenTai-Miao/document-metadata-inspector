"""Malformed and over-depth workbook-relationship target regressions."""

from pathlib import Path
from zipfile import ZipFile

import pytest

from tests.factories import make_workbook, rewrite_package
from xlsx_metadata_forensics.errors import ErrorCode, ExtractionError
from xlsx_metadata_forensics.models import ExtractionLimits
from xlsx_metadata_forensics.ooxml.package import open_package

ROOT_RELS_PART = "_rels/.rels"
_WORKBOOK_TARGET = b"xl/workbook.xml"


def _replace_workbook_target(path: Path, target: bytes) -> None:
    with ZipFile(path, "r") as archive:
        relationships = archive.read(ROOT_RELS_PART)
    changed = relationships.replace(_WORKBOOK_TARGET, target)
    assert changed != relationships
    rewrite_package(path, {ROOT_RELS_PART: changed}, {})


@pytest.mark.parametrize(
    "target",
    [b"http://[", b"//["],
    ids=("scheme-authority", "network-path-authority"),
)
def test_malformed_bracket_uri_target_maps_to_invalid_xlsx(
    tmp_path: Path,
    target: bytes,
) -> None:
    # Given: valid root-relationship XML with a bracket-malformed URI target.
    workbook = make_workbook(tmp_path / "malformed-target.xlsx")
    _replace_workbook_target(workbook, target)

    # When / Then: URI parsing cannot leak and retains the relationships source.
    with (
        pytest.raises(ExtractionError) as caught,
        open_package(workbook, ExtractionLimits()),
    ):
        pass
    assert caught.value.code is ErrorCode.INVALID_XLSX
    assert caught.value.source == ROOT_RELS_PART


def test_rejects_workbook_target_still_changing_after_two_decoding_layers(
    tmp_path: Path,
) -> None:
    # Given: a triple-encoded target that fully decodes to xl/workbook.xml.
    workbook = make_workbook(tmp_path / "over-depth-target.xlsx")
    _replace_workbook_target(workbook, b"xl/%252577orkbook.xml")

    # When / Then: bounded URI normalization rejects it at the relationship source.
    with (
        pytest.raises(ExtractionError) as caught,
        open_package(workbook, ExtractionLimits()),
    ):
        pass
    assert caught.value.code is ErrorCode.INVALID_XLSX
    assert caught.value.source == ROOT_RELS_PART


def test_double_encoded_traversal_target_remains_invalid_xlsx(tmp_path: Path) -> None:
    # Given: a workbook target hiding a parent segment behind two encoding layers.
    workbook = make_workbook(tmp_path / "double-traversal-target.xlsx")
    _replace_workbook_target(workbook, b"%252e%252e/xl/workbook.xml")

    # When / Then: the existing repeated-decoding traversal defense is preserved.
    with (
        pytest.raises(ExtractionError) as caught,
        open_package(workbook, ExtractionLimits()),
    ):
        pass
    assert caught.value.code is ErrorCode.INVALID_XLSX
    assert caught.value.source == ROOT_RELS_PART
