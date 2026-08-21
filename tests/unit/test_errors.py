"""Contract tests for typed extraction errors."""

from dataclasses import FrozenInstanceError
from typing import Literal

import pytest

from xlsx_metadata_forensics.errors import ErrorCode, ErrorResponse, ExtractionError

ErrorFieldName = Literal["code", "message", "source"]

ERROR_FIELD_MUTATIONS: tuple[tuple[ErrorFieldName, ErrorCode | str], ...] = (
    ("code", ErrorCode.CORRUPT_PACKAGE),
    ("message", "Changed message."),
    ("source", "changed.xml"),
)


def test_extraction_error_string_is_its_sanitized_message() -> None:
    # Given: a typed extraction failure with source evidence.
    error = ExtractionError(
        code=ErrorCode.INVALID_XLSX,
        message="The workbook is invalid.",
        source="[Content_Types].xml",
    )

    # When: the error is rendered for a boundary consumer.
    rendered = str(error)

    # Then: only its sanitized message is returned.
    assert rendered == "The workbook is invalid."


@pytest.mark.parametrize(("field_name", "replacement"), ERROR_FIELD_MUTATIONS)
def test_extraction_error_rejects_each_field_reassignment(
    field_name: ErrorFieldName,
    replacement: ErrorCode | str,
) -> None:
    # Given: a typed extraction exception with stable application-owned fields.
    error = ExtractionError(
        code=ErrorCode.INVALID_XLSX,
        message="The workbook is invalid.",
        source="[Content_Types].xml",
    )

    # When / Then: every application-owned field rejects reassignment.
    with pytest.raises(FrozenInstanceError):
        setattr(error, field_name, replacement)
    assert error.code is ErrorCode.INVALID_XLSX
    assert error.message == "The workbook is invalid."
    assert error.source == "[Content_Types].xml"


@pytest.mark.parametrize("field_name", ["code", "message", "source"])
def test_extraction_error_rejects_each_field_deletion(
    field_name: ErrorFieldName,
) -> None:
    # Given: a typed extraction exception whose serialized evidence is stable.
    error = ExtractionError(
        code=ErrorCode.INVALID_XLSX,
        message="The workbook is invalid.",
        source="[Content_Types].xml",
    )

    # When: deletion is attempted for each application-owned field.
    with pytest.raises(FrozenInstanceError):
        delattr(error, field_name)

    # Then: the rejected deletion cannot alter the serialized error contract.
    payload = ErrorResponse(error=error).model_dump(mode="json")
    assert payload["error"] == {
        "code": "invalid_excel",
        "message": "The workbook is invalid.",
        "source": "[Content_Types].xml",
    }


def test_extraction_error_declares_exact_field_slots() -> None:
    # Given: the independently decorated typed extraction exception class.

    # When: slots declared by this class itself are observed.
    declared_slots = ExtractionError.__dict__.get("__slots__")

    # Then: only the three typed error fields own dedicated slots.
    assert declared_slots == ("code", "message", "source")


def test_error_response_serializes_with_success_false() -> None:
    # Given: a typed failure wrapped by the stable error response.
    response = ErrorResponse(
        error=ExtractionError(
            code=ErrorCode.INVALID_XLSX,
            message="The workbook is invalid.",
            source="[Content_Types].xml",
        ),
    )

    # When: the response crosses the JSON boundary.
    payload = response.model_dump(mode="json")

    # Then: its literal result and typed error fields serialize exactly.
    assert payload["success"] is False
    assert payload["error"]["code"] == "invalid_excel"
    assert payload["error"]["message"] == "The workbook is invalid."
    assert payload["error"]["source"] == "[Content_Types].xml"


def test_error_code_contract_contains_only_approved_values() -> None:
    # Given: the stable error-code enumeration.
    codes = tuple(member.value for member in ErrorCode)

    # When: the machine-consumed values are enumerated.
    actual = codes

    # Then: every approved code is represented exactly once.
    assert actual == (
        "unsupported_format",
        "invalid_excel",
        "encrypted_excel",
        "corrupt_package",
        "file_too_large",
        "unsafe_package",
        "extraction_failed",
    )


def test_legacy_xlsx_error_names_alias_generic_excel_codes() -> None:
    # Given: low-level XLSX code names remain imported by existing adapters.

    # When / Then: they alias the new serialized Excel-family codes.
    assert ErrorCode.INVALID_XLSX is ErrorCode.INVALID_EXCEL
    assert ErrorCode.ENCRYPTED_XLSX is ErrorCode.ENCRYPTED_EXCEL
