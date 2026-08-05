"""Unicode-control and bounded-decoding member-name regressions."""

from pathlib import Path
from zipfile import ZipFile

import pytest

from tests.factories import make_workbook, rewrite_package
from tests.zip_mutators import embed_raw_nul_member_name
from xlsx_metadata_forensics.errors import ErrorCode, ExtractionError
from xlsx_metadata_forensics.models import ExtractionLimits
from xlsx_metadata_forensics.ooxml.package import open_package

CORE_PART = "docProps/core.xml"


def test_rejects_raw_nul_before_zipfile_filename_sanitization(tmp_path: Path) -> None:
    # Given: a real central/local name whose raw NUL is hidden by ZipInfo.filename.
    workbook = make_workbook(tmp_path / "raw-nul-name.xlsx")
    byte_index = CORE_PART.index("c")
    mutated = embed_raw_nul_member_name(
        workbook.read_bytes(),
        CORE_PART,
        byte_index,
    )
    _ = workbook.write_bytes(mutated)
    with ZipFile(workbook) as archive:
        nul_infos = tuple(
            info for info in archive.infolist() if "\x00" in info.orig_filename
        )
    assert len(nul_infos) == 1
    assert nul_infos[0].orig_filename != nul_infos[0].filename

    # When / Then: validation sees the original identity and rejects without echoing it.
    with (
        pytest.raises(ExtractionError) as caught,
        open_package(workbook, ExtractionLimits()),
    ):
        pass
    assert caught.value.code is ErrorCode.UNSAFE_PACKAGE
    assert caught.value.source is None


@pytest.mark.parametrize(
    "member_name",
    [
        "custom/raw-\u007f.xml",
        "custom/raw-\u0080.xml",
        "custom/raw-\u009f.xml",
    ],
    ids=("delete", "c1-first", "c1-last"),
)
def test_rejects_raw_unicode_category_cc_member_names(
    tmp_path: Path,
    member_name: str,
) -> None:
    # Given: a genuine workbook with one raw Unicode control member name.
    workbook = make_workbook(tmp_path / "raw-control-name.xlsx")
    rewrite_package(workbook, {}, {member_name: b"control"})

    # When / Then: every Cc name is rejected as package-unsafe.
    with (
        pytest.raises(ExtractionError) as caught,
        open_package(workbook, ExtractionLimits()),
    ):
        pass
    assert caught.value.code is ErrorCode.UNSAFE_PACKAGE


@pytest.mark.parametrize(
    "member_name",
    [
        "custom/encoded-%7F.xml",
        "custom/encoded-%C2%80.xml",
        "custom/encoded-%C2%9F.xml",
    ],
    ids=("delete", "c1-first", "c1-last"),
)
def test_rejects_percent_encoded_unicode_category_cc_member_names(
    tmp_path: Path,
    member_name: str,
) -> None:
    # Given: a genuine workbook with one percent-encoded Unicode control name.
    workbook = make_workbook(tmp_path / "encoded-control-name.xlsx")
    rewrite_package(workbook, {}, {member_name: b"control"})

    # When / Then: decoding cannot hide a Cc name from package safety checks.
    with (
        pytest.raises(ExtractionError) as caught,
        open_package(workbook, ExtractionLimits()),
    ):
        pass
    assert caught.value.code is ErrorCode.UNSAFE_PACKAGE


def test_rejects_member_name_still_changing_after_two_decoding_layers(
    tmp_path: Path,
) -> None:
    # Given: a triple-encoded member name that fully decodes to custom/A.xml.
    workbook = make_workbook(tmp_path / "over-depth-name.xlsx")
    rewrite_package(workbook, {}, {"custom/%252541.xml": b"safe after full decode"})

    # When / Then: bounded normalization rejects still-changing input deterministically.
    with (
        pytest.raises(ExtractionError) as caught,
        open_package(workbook, ExtractionLimits()),
    ):
        pass
    assert caught.value.code is ErrorCode.UNSAFE_PACKAGE
