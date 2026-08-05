"""Convert hostile OOXML custom-property scalar text."""

import re
from dataclasses import dataclass
from math import isfinite
from typing import Final, Literal, TypeGuard, assert_never

from xlsx_metadata_forensics.models import JsonScalar
from xlsx_metadata_forensics.normalization import inspect_timestamp

type IntegerVt = Literal[
    "i1", "i2", "i4", "i8", "int", "ui1", "ui2", "ui4", "ui8", "uint"
]
type NumberVt = IntegerVt | Literal["r4", "r8", "decimal"]
type VtName = NumberVt | Literal["lpwstr", "bstr", "bool", "filetime", "date", "empty"]

_INTEGER: Final[re.Pattern[str]] = re.compile(r"[+-]?[0-9]+")
_FLOAT: Final[re.Pattern[str]] = re.compile(
    r"[+-]?(?:(?:[0-9]+(?:\.[0-9]*)?)|(?:\.[0-9]+))(?:[eE][+-]?[0-9]+)?"
)
_DECIMAL: Final[re.Pattern[str]] = re.compile(
    r"[+-]?(?:(?:[0-9]+(?:\.[0-9]*)?)|(?:\.[0-9]+))"
)
_SIGNED_VTS: Final = ("i1", "i2", "i4", "i8", "int")
_INTEGER_VTS: Final = (*_SIGNED_VTS, "ui1", "ui2", "ui4", "ui8", "uint")
_FLOAT_VTS: Final = ("r4", "r8")
_OTHER_VTS: Final = (
    "lpwstr",
    "bstr",
    "decimal",
    "bool",
    "filetime",
    "date",
    "empty",
)
_KNOWN_VTS: Final = _INTEGER_VTS + _FLOAT_VTS + _OTHER_VTS
_BOOLEAN_VALUES: Final = {"true": True, "1": True, "false": False, "0": False}


@dataclass(frozen=True, slots=True)
class ConvertedScalar:
    """Carry one converted scalar and its independent validity state."""

    value: JsonScalar
    valid: bool


def is_known_vt(value: str) -> TypeGuard[VtName]:
    """Narrow a local VT name to the explicitly supported scalar family."""
    return value in _KNOWN_VTS


def safe_int(raw: str | None) -> int | None:
    """Convert only an exact ASCII integer without leaking runtime limits."""
    if raw is None or _INTEGER.fullmatch(raw) is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _integer(value_type: IntegerVt, raw: str) -> ConvertedScalar:
    value = safe_int(raw)
    if value is None:
        return ConvertedScalar(value=raw, valid=False)
    kind = value_type.removeprefix("u")
    bits = 32 if kind == "int" else int(kind[1:]) * 8
    signed = value_type in _SIGNED_VTS
    lower: int = -(1 << (bits - 1)) if signed else 0
    upper: int = (1 << (bits - int(signed))) - 1
    valid = lower <= value <= upper
    return ConvertedScalar(value=value if valid else raw, valid=valid)


def _number(value_type: NumberVt, raw: str) -> ConvertedScalar:
    match value_type:
        case "i1" | "i2" | "i4" | "i8" | "int" | "ui1" | "ui2" | "ui4" | "ui8" | "uint":
            return _integer(value_type, raw)
        case "r4" | "r8":
            if _FLOAT.fullmatch(raw) is None:
                return ConvertedScalar(value=raw, valid=False)
            value = float(raw)
            finite = isfinite(value)
            return ConvertedScalar(value=value if finite else raw, valid=finite)
        case "decimal":
            return ConvertedScalar(
                value=raw,
                valid=_DECIMAL.fullmatch(raw) is not None,
            )
        case _:
            assert_never(value_type)


def convert_scalar(value_type: VtName, raw: str) -> ConvertedScalar:
    """Convert one supported scalar while preserving invalid raw evidence."""
    match value_type:
        case "lpwstr" | "bstr":
            return ConvertedScalar(value=raw, valid=True)
        case (
            "i1"
            | "i2"
            | "i4"
            | "i8"
            | "int"
            | "ui1"
            | "ui2"
            | "ui4"
            | "ui8"
            | "uint"
            | "r4"
            | "r8"
            | "decimal"
        ):
            return _number(value_type, raw)
        case "bool":
            value = _BOOLEAN_VALUES.get(raw)
            if value is None:
                return ConvertedScalar(value=raw, valid=False)
            return ConvertedScalar(value=value, valid=True)
        case "filetime" | "date":
            inspected = inspect_timestamp(raw)
            return ConvertedScalar(
                value=inspected.value.normalized,
                valid=inspected.valid,
            )
        case "empty":
            valid = raw == ""
            return ConvertedScalar(value=None if valid else raw, valid=valid)
        case _:
            assert_never(value_type)
