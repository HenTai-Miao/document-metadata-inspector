"""Contract tests for the generic document format identity layer."""

from pathlib import Path

import pytest

from document_metadata_inspector.formats import (
    SUPPORTED_SUFFIXES,
    ContainerKind,
    DocumentFamily,
    DocumentFormat,
    FormatIdentityStatus,
    UnsupportedDocumentFormatError,
    identify_declared_format,
    identify_format,
)


def test_supported_suffix_contract_is_exact() -> None:
    assert SUPPORTED_SUFFIXES == (
        ".pdf",
        ".doc",
        ".docx",
        ".docm",
        ".dot",
        ".dotx",
        ".dotm",
        ".xls",
        ".xlsx",
        ".xlsm",
        ".xlsb",
        ".xlt",
        ".xltx",
        ".xltm",
    )


@pytest.mark.parametrize(
    ("name", "expected_format", "expected_family", "expected_container"),
    [
        ("report.PDF", DocumentFormat.PDF, DocumentFamily.PDF, ContainerKind.PDF),
        ("bid.DoC", DocumentFormat.DOC, DocumentFamily.WORD, ContainerKind.OLE),
        ("bid.docm", DocumentFormat.DOCM, DocumentFamily.WORD, ContainerKind.OPC),
        ("bid.dotm", DocumentFormat.DOTM, DocumentFamily.WORD, ContainerKind.OPC),
        ("price.XLS", DocumentFormat.XLS, DocumentFamily.EXCEL, ContainerKind.OLE),
        ("price.xlsb", DocumentFormat.XLSB, DocumentFamily.EXCEL, ContainerKind.OPC),
        ("price.xltm", DocumentFormat.XLTM, DocumentFamily.EXCEL, ContainerKind.OPC),
    ],
)
def test_declared_format_is_case_insensitive_and_typed(
    name: str,
    expected_format: DocumentFormat,
    expected_family: DocumentFamily,
    expected_container: ContainerKind,
) -> None:
    identity = identify_declared_format(Path(name))

    assert identity.declared_format is expected_format
    assert identity.family is expected_family
    assert identity.expected_container is expected_container
    assert identity.observed_container is None
    assert identity.status is FormatIdentityStatus.UNVERIFIED


def test_unsupported_suffix_is_rejected() -> None:
    with pytest.raises(UnsupportedDocumentFormatError):
        _ = identify_declared_format(Path("bid.rtf"))


def test_magic_mismatch_is_explicit_instead_of_trusting_extension() -> None:
    ole_magic = bytes.fromhex("D0CF11E0A1B11AE1")

    identity = identify_format(Path("bid.docx"), ole_magic)

    assert identity.declared_format is DocumentFormat.DOCX
    assert identity.expected_container is ContainerKind.OPC
    assert identity.observed_container is ContainerKind.OLE
    assert identity.status is FormatIdentityStatus.MISMATCH


def test_matching_magic_confirms_the_declared_container() -> None:
    identity = identify_format(Path("report.pdf"), b"%PDF-1.7\n")

    assert identity.observed_container is ContainerKind.PDF
    assert identity.status is FormatIdentityStatus.CONFIRMED
