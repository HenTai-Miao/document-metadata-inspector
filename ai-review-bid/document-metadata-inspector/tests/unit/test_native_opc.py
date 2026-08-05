"""Native OPC metadata and forensic-inventory adapter tests."""

from hashlib import sha256
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from document_metadata_inspector.formats import identify_format
from document_metadata_inspector.models import (
    InspectionLimits,
    JsonValue,
    ParserRun,
    ParserStatus,
)
from document_metadata_inspector.native import extract_native_office
from document_metadata_inspector.source import open_source_snapshot
from tests.opc_factories import make_opc_workbook
from xlsx_metadata_forensics.formats import ExcelFormat

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels"
    ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/{target}" ContentType="{content_type}"/>
</Types>
"""
_ROOT_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
    Target="{target}"/>
</Relationships>
"""
_CORE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<cp:coreProperties
 xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:dcterms="http://purl.org/dc/terms/">
  <dc:creator>  Alice Analyst  </dc:creator>
  <cp:lastModifiedBy>Bob Reviewer</cp:lastModifiedBy>
  <dcterms:created>2026-08-05T01:02:03Z</dcterms:created>
</cp:coreProperties>
"""
_APP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">
  <Application>Microsoft Office Word</Application>
  <AppVersion>16.0000</AppVersion>
  <Company>Example Bid Co.</Company>
  <Manager>Carol Manager</Manager>
  <TotalTime>42</TotalTime>
</Properties>
"""
_CUSTOM_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/custom-properties"
 xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <property fmtid="{D5CDD505-2E9C-101B-9397-08002B2CF9AE}" pid="2" name="Tender Team">
    <vt:lpwstr>North Group</vt:lpwstr>
  </property>
</Properties>
"""
_EXTERNAL_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId9"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"
    Target="https://invalid.example.test/private" TargetMode="External"/>
</Relationships>
"""
_DOCX_MAIN_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
)


def _write_word_package(
    path: Path,
    *,
    main_content_type: str = _DOCX_MAIN_CONTENT_TYPE,
) -> Path:
    target = "word/document.xml"
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            _CONTENT_TYPES.format(target=target, content_type=main_content_type),
        )
        archive.writestr("_rels/.rels", _ROOT_RELS.format(target=target))
        archive.writestr(
            target,
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body/></w:document>',
        )
        archive.writestr("docProps/core.xml", _CORE_XML)
        archive.writestr("docProps/app.xml", _APP_XML)
        archive.writestr("docProps/custom.xml", _CUSTOM_XML)
        archive.writestr("word/_rels/document.xml.rels", _EXTERNAL_RELS)
        archive.writestr("word/vbaProject.bin", b"inactive macro evidence")
        archive.writestr("word/embeddings/object1.bin", b"embedded evidence")
        archive.writestr("_xmlsignatures/sig1.xml", b"<Signature/>")
    return path


def _extract(path: Path) -> ParserRun:
    with open_source_snapshot(path, InspectionLimits()) as snapshot:
        header = snapshot.stream.read(1024)
        _ = snapshot.stream.seek(0)
        identity = identify_format(path, header)
        return extract_native_office(snapshot, identity)


def _values(run: ParserRun, canonical_name: str) -> tuple[JsonValue, ...]:
    return tuple(
        observation.raw_value
        for observation in run.observations
        if observation.canonical_name == canonical_name
    )


def test_word_opc_extracts_standard_custom_and_inventory_evidence(
    tmp_path: Path,
) -> None:
    path = _write_word_package(tmp_path / "bid.docx")

    run = _extract(path)

    assert run.status is ParserStatus.SUCCEEDED
    assert _values(run, "author") == ("  Alice Analyst  ",)
    assert _values(run, "last_modified_by") == ("Bob Reviewer",)
    assert _values(run, "application") == ("Microsoft Office Word",)
    assert _values(run, "company") == ("Example Bid Co.",)
    assert _values(run, "total_editing_minutes") == (42,)
    assert _values(run, "custom_property.tender team") == ("North Group",)
    assert len(_values(run, "external_relationship")) == 1
    assert _values(run, "active_content") == ("word/vbaProject.bin",)
    embedded_payload = b"embedded evidence"
    assert _values(run, "embedded_object") == (
        {
            "path": "word/embeddings/object1.bin",
            "content_type": "application/octet-stream",
            "size_bytes": len(embedded_payload),
            "sha256": sha256(embedded_payload).hexdigest(),
        },
    )
    assert _values(run, "digital_signature_part") == ("_xmlsignatures/sig1.xml",)
    child = run.embedded_documents[0]
    assert child.parent_id == sha256(path.read_bytes()).hexdigest()
    assert child.path == "word/embeddings/object1.bin"
    assert child.sha256 == sha256(embedded_payload).hexdigest()
    assert child.parser_names == ("native-office",)

    author = next(item for item in run.observations if item.canonical_name == "author")
    assert author.normalized_value == "alice analyst"
    assert author.location == "docProps/core.xml"


@pytest.mark.parametrize(
    ("suffix", "content_type"),
    [
        (
            "docm",
            "application/vnd.ms-word.document.macroEnabled.main+xml",
        ),
        (
            "dotx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml",
        ),
        (
            "dotm",
            "application/vnd.ms-word.template.macroEnabledTemplate.main+xml",
        ),
    ],
)
def test_word_opc_main_mime_must_match_declared_format(
    tmp_path: Path,
    suffix: str,
    content_type: str,
) -> None:
    path = _write_word_package(
        tmp_path / f"bid.{suffix}",
        main_content_type=content_type,
    )

    run = _extract(path)

    assert run.status is ParserStatus.SUCCEEDED


def test_opc_main_mime_mismatch_is_a_stable_parser_failure(tmp_path: Path) -> None:
    path = _write_word_package(
        tmp_path / "bid.docx",
        main_content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
    )

    run = _extract(path)

    assert run.status is ParserStatus.FAILED
    assert run.error_code == "format_mismatch"


@pytest.mark.parametrize(
    "excel_format",
    [
        ExcelFormat.XLSX,
        ExcelFormat.XLSM,
        ExcelFormat.XLSB,
        ExcelFormat.XLTX,
        ExcelFormat.XLTM,
    ],
)
def test_excel_opc_formats_pass_exact_main_part_validation(
    tmp_path: Path,
    excel_format: ExcelFormat,
) -> None:
    path = tmp_path / f"book.{excel_format.value}"
    _ = make_opc_workbook(path, excel_format)

    run = _extract(path)

    assert run.status is ParserStatus.SUCCEEDED
