"""Contract tests for supported Excel format identities."""

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from xlsx_metadata_forensics import formats


@pytest.mark.parametrize(
    ("format_name", "expected_member_name"),
    [
        ("xls", "XLS"),
        ("xlsx", "XLSX"),
        ("xlsm", "XLSM"),
        ("xlsb", "XLSB"),
        ("xlt", "XLT"),
        ("xltx", "XLTX"),
        ("xltm", "XLTM"),
    ],
)
def test_excel_format_has_exact_supported_values(
    format_name: str,
    expected_member_name: str,
) -> None:
    # Given: the frozen seven-format support contract.

    # When: the enum is constructed from its serialized value.
    actual = formats.ExcelFormat(format_name)

    # Then: each value has one exact enum identity.
    assert actual is formats.ExcelFormat[expected_member_name]


def test_excel_format_iteration_has_stable_order_without_aliases() -> None:
    # Given: consumers may expose the supported formats as a stable list.

    # When: the enum is iterated.
    actual = tuple(item.value for item in formats.ExcelFormat)

    # Then: it contains exactly the seven user-approved native Excel formats.
    assert actual == ("xls", "xlsx", "xlsm", "xlsb", "xlt", "xltx", "xltm")


@pytest.mark.parametrize("filename", ["book.xls", "BOOK.XLS", "报价.XlS"])
def test_declared_legacy_workbook_format_uses_ole_container(filename: str) -> None:
    # Given: an XLS filename with any suffix casing.

    # When: its declared format identity is resolved.
    identity = formats.identify_declared_format(Path(filename))

    # Then: it is one XLS format routed to the OLE adapter.
    assert identity == formats.FormatIdentity(
        format=formats.ExcelFormat.XLS,
        container=formats.ContainerKind.OLE,
    )


@pytest.mark.parametrize("suffix", ["xlsx", "xlsm", "xlsb", "xltx", "xltm"])
def test_declared_opc_format_uses_opc_container(suffix: str) -> None:
    # Given: one approved OPC-family filename.

    # When: its declared format identity is resolved.
    identity = formats.identify_declared_format(Path(f"fixture.{suffix}"))

    # Then: its exact format is retained and routed to OPC.
    assert identity.format.value == suffix
    assert identity.container is formats.ContainerKind.OPC


def test_declared_xlt_format_uses_ole_container() -> None:
    # Given: one legacy binary template filename.

    # When: its declared format identity is resolved.
    identity = formats.identify_declared_format(Path("fixture.xlt"))

    # Then: it retains the template identity and uses OLE.
    assert identity.format is formats.ExcelFormat.XLT
    assert identity.container is formats.ContainerKind.OLE


@pytest.mark.parametrize(
    "filename", ["fixture.csv", "fixture.ods", "fixture", "fixture.xlsx.txt"]
)
def test_unapproved_suffix_is_rejected_with_fixed_message(filename: str) -> None:
    # Given: a filename outside the seven-format contract.

    # When / Then: it is rejected without reflecting the untrusted filename.
    with pytest.raises(ValueError, match=r"^Unsupported Excel filename suffix\.$"):
        _ = formats.identify_declared_format(Path(filename))


def test_format_identity_is_frozen_and_slotted() -> None:
    # Given: one resolved immutable format identity.
    identity = formats.identify_declared_format(Path("fixture.xlsx"))
    field_name = "format"

    # When / Then: it has no per-instance dictionary and cannot be mutated.
    assert hasattr(identity, "__dict__") is False
    with pytest.raises(FrozenInstanceError):
        setattr(identity, field_name, formats.ExcelFormat.XLS)
