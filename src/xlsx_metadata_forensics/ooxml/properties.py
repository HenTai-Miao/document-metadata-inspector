"""Read standard and custom OOXML document properties."""

from dataclasses import dataclass
from typing import Final, Literal
from xml.etree.ElementTree import Element

from xlsx_metadata_forensics.errors import ExtractionError
from xlsx_metadata_forensics.models import (
    CustomProperty,
    DocumentMetadata,
    ExtractionWarning,
    TimestampValue,
)
from xlsx_metadata_forensics.normalization import (
    inspect_timestamp,
    is_sensitive_name,
    redact_sensitive_value,
)
from xlsx_metadata_forensics.ooxml._property_scalars import (
    ConvertedScalar,
    convert_scalar,
    is_known_vt,
    safe_int,
)
from xlsx_metadata_forensics.ooxml.package import PackageView

type PartName = Literal["docProps/core.xml", "docProps/app.xml", "docProps/custom.xml"]
type MetadataValue = str | int | TimestampValue | None

_OPENXML_NS: Final = "http://schemas.openxmlformats.org/"
_CORE_NS: Final = f"{_OPENXML_NS}package/2006/metadata/core-properties"
_EXT_NS: Final = f"{_OPENXML_NS}officeDocument/2006/extended-properties"
_CUSTOM_NS: Final = f"{_OPENXML_NS}officeDocument/2006/custom-properties"
_VT_NS: Final = f"{_OPENXML_NS}officeDocument/2006/docPropsVTypes"
_DC_NS: Final = "http://purl.org/dc/elements/1.1/"
_DCTERMS_NS: Final = "http://purl.org/dc/terms/"
_CORE: Final[PartName] = "docProps/core.xml"
_APP: Final[PartName] = "docProps/app.xml"
_CUSTOM: Final[PartName] = "docProps/custom.xml"
_FIXED_WARNING_MESSAGES: Final = {
    "property_timestamp_invalid": "A document-property timestamp is invalid.",
    "property_total_time_invalid": "The extended TotalTime property is invalid.",
    "property_value_malformed": "A document-property value has malformed content.",
    "custom_property_malformed": "A custom document property is malformed.",
    "custom_property_value_invalid": "A custom document-property scalar is invalid.",
    "property_part_unreadable": "An optional document-property part could not be read.",
    "property_part_invalid": "A document-property part has an invalid root.",
}


def _fields(namespace: str, *spec: str) -> dict[str, str]:
    pairs = (entry.partition(":") for entry in " ".join(spec).split())
    return {f"{{{namespace}}}{xml_name}": field for xml_name, _, field in pairs}


_ROOTS: Final = {
    _CORE: f"{{{_CORE_NS}}}coreProperties",
    _APP: f"{{{_EXT_NS}}}Properties",
    _CUSTOM: f"{{{_CUSTOM_NS}}}Properties",
}
_CORE_TEXT: Final = _fields(
    _DC_NS,
    "creator:author title:title subject:subject",
    "description:description identifier:identifier language:language",
) | _fields(
    _CORE_NS,
    "lastModifiedBy:last_modified_by keywords:keywords category:category",
    "contentStatus:content_status revision:revision version:version",
)
_CORE_TIME: Final = _fields(
    _DCTERMS_NS, "created:created_at modified:modified_at"
) | _fields(_CORE_NS, "lastPrinted:last_printed_at")
_APP_TEXT: Final = _fields(
    _EXT_NS,
    "Application:application AppVersion:application_version Company:company",
    "Manager:manager Template:template",
)
_CUSTOM_PROPERTY: Final = f"{{{_CUSTOM_NS}}}property"
_TOTAL_TIME: Final = f"{{{_EXT_NS}}}TotalTime"
_VT_PREFIX: Final = f"{{{_VT_NS}}}"


@dataclass(frozen=True, slots=True)
class PropertyFacts:
    """Collect immutable facts read from optional document-property parts."""

    metadata: DocumentMetadata
    custom_properties: tuple[CustomProperty, ...]
    warnings: tuple[ExtractionWarning, ...]


@dataclass(frozen=True, slots=True)
class _PartFacts:
    metadata: tuple[tuple[str, MetadataValue], ...] = ()
    custom_properties: tuple[CustomProperty, ...] = ()
    warnings: tuple[ExtractionWarning, ...] = ()


def _fixed_warning(code: str, source: PartName) -> ExtractionWarning:
    message = _FIXED_WARNING_MESSAGES[code]
    return ExtractionWarning(code=code, message=message, source=source)


def _contains_non_whitespace(value: str | None) -> bool:
    return value is not None and bool(value.strip())


def _is_malformed_known_value(element: Element) -> bool:
    return len(element) != 0 or _contains_non_whitespace(element.tail)


def _parse_core(root: Element) -> _PartFacts:
    metadata: list[tuple[str, MetadataValue]] = []
    warnings: list[ExtractionWarning] = []
    for child in root:
        text_field = _CORE_TEXT.get(child.tag)
        time_field = _CORE_TIME.get(child.tag)
        if (
            text_field is not None or time_field is not None
        ) and _is_malformed_known_value(child):
            warnings.append(_fixed_warning("property_value_malformed", _CORE))
            continue
        if text_field is not None:
            metadata.append((text_field, child.text))
        if time_field is not None and child.text is not None:
            inspected = inspect_timestamp(child.text)
            metadata.append((time_field, inspected.value))
            if not inspected.valid:
                warnings.append(_fixed_warning("property_timestamp_invalid", _CORE))
    return _PartFacts(tuple(metadata), warnings=tuple(warnings))


def _parse_app(root: Element) -> _PartFacts:
    metadata: list[tuple[str, MetadataValue]] = []
    warnings: list[ExtractionWarning] = []
    for child in root:
        text_field = _APP_TEXT.get(child.tag)
        if (
            text_field is not None or child.tag == _TOTAL_TIME
        ) and _is_malformed_known_value(child):
            warnings.append(_fixed_warning("property_value_malformed", _APP))
            continue
        if text_field is not None:
            metadata.append((text_field, child.text))
        if child.tag == _TOTAL_TIME:
            value = safe_int(child.text)
            if value is not None:
                metadata.append(("total_editing_minutes", value))
            else:
                warnings.append(_fixed_warning("property_total_time_invalid", _APP))
    return _PartFacts(tuple(metadata), warnings=tuple(warnings))


def _parse_custom(root: Element) -> _PartFacts:
    properties: list[CustomProperty] = []
    warnings: list[ExtractionWarning] = []
    malformed = _fixed_warning("custom_property_malformed", _CUSTOM)
    for element in root:
        name = element.get("name")
        if (
            element.tag != _CUSTOM_PROPERTY
            or not name
            or len(element) != 1
            or _contains_non_whitespace(element.text)
        ):
            warnings.append(malformed)
            continue
        value_element = element[0]
        if (
            not value_element.tag.startswith(_VT_PREFIX)
            or len(value_element) != 0
            or _contains_non_whitespace(value_element.tail)
        ):
            warnings.append(malformed)
            continue
        value_type = value_element.tag.removeprefix(_VT_PREFIX)
        raw = "".join(value_element.itertext())
        if is_known_vt(value_type):
            converted = convert_scalar(value_type, raw)
            if not converted.valid:
                warnings.append(
                    _fixed_warning("custom_property_value_invalid", _CUSTOM)
                )
        else:
            converted = ConvertedScalar(value=raw, valid=True)
            warnings.append(
                ExtractionWarning(
                    code="custom_property_type_unknown",
                    message=f"Custom property type '{value_type}' is unsupported.",
                    source=_CUSTOM,
                )
            )
        value = converted.value
        if value is not None and is_sensitive_name(name):
            value = redact_sensitive_value(name, str(value))
        properties.append(
            CustomProperty(
                name=name,
                value_type=value_type,
                value=value,
                source=_CUSTOM,
            )
        )
    return _PartFacts(custom_properties=tuple(properties), warnings=tuple(warnings))


_PART_PARSERS: Final = {_CORE: _parse_core, _APP: _parse_app, _CUSTOM: _parse_custom}


def _ordered(warnings: list[ExtractionWarning]) -> tuple[ExtractionWarning, ...]:
    unique = {
        (warning.source or "", warning.code, warning.message): warning
        for warning in warnings
    }
    return tuple(unique[key] for key in sorted(unique))


def read_properties(package: PackageView) -> PropertyFacts:
    """Read only verified Transitional property parts through the package view."""
    metadata: dict[str, MetadataValue] = {}
    properties: list[CustomProperty] = []
    warnings: list[ExtractionWarning] = []
    for source in (_CORE, _APP, _CUSTOM):
        try:
            root = package.read_xml(source)
        except ExtractionError as error:
            if error.source != source:
                raise
            warnings.append(_fixed_warning("property_part_unreadable", source))
            continue
        if root is None:
            continue
        if root.tag != _ROOTS[source]:
            warnings.append(_fixed_warning("property_part_invalid", source))
            continue
        part = _PART_PARSERS[source](root)
        metadata.update(part.metadata)
        properties.extend(part.custom_properties)
        warnings.extend(part.warnings)
    properties.sort(
        key=lambda item: (item.name.casefold(), item.name, item.value_type, item.source)
    )
    return PropertyFacts(
        metadata=DocumentMetadata.model_validate(metadata),
        custom_properties=tuple(properties),
        warnings=_ordered(warnings),
    )
