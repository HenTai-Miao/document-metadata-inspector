"""Real shaded-JAR checks enabled explicitly by the build environment."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from pypdf import PdfWriter

from document_metadata_inspector.models import InspectionLimits, ParserRun, ParserStatus
from document_metadata_inspector.source import open_source_snapshot
from document_metadata_inspector.workers.apache import ApacheWorker
from tests.factories import make_workbook, rewrite_package

if TYPE_CHECKING:
    from collections.abc import Callable

_JAVA = os.environ.get("DOCMETA_JAVA")
_JAR_TEXT = os.environ.get("DOCMETA_APACHE_WORKER_JAR")
_JAR = Path(_JAR_TEXT) if _JAR_TEXT else None
_RUNTIME_AVAILABLE = bool(_JAVA and _JAR is not None and _JAR.is_file())

pytestmark = pytest.mark.skipif(
    not _RUNTIME_AVAILABLE,
    reason="set DOCMETA_JAVA and DOCMETA_APACHE_WORKER_JAR for real worker checks",
)

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels"
    ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml"
    ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/docProps/core.xml"
    ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>
"""
_ROOT_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
    Target="word/document.xml"/>
  <Relationship Id="rId2"
    Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties"
    Target="docProps/core.xml"/>
</Relationships>
"""
_CORE = """<?xml version="1.0" encoding="UTF-8"?>
<cp:coreProperties
 xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/">
  <dc:creator>Alice Word</dc:creator>
  <dc:title>Controlled Word fixture</dc:title>
</cp:coreProperties>
"""
_DOCUMENT = """<?xml version="1.0" encoding="UTF-8"?>
<w:document
 xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body><w:p><w:r><w:t>body must not be returned</w:t></w:r></w:p></w:body>
</w:document>
"""


def _worker() -> ApacheWorker:
    assert _JAVA is not None
    assert _JAR is not None
    return ApacheWorker.from_runtime(Path(_JAVA), _JAR)


def _scan(path: Path) -> ParserRun:
    with open_source_snapshot(path, InspectionLimits()) as snapshot:
        return _worker().scan(snapshot, None, InspectionLimits())


def _write_pdf(path: Path) -> None:
    writer = PdfWriter()
    _ = writer.add_blank_page(width=100, height=100)
    writer.add_metadata({"/Author": "Alice PDF", "/Title": "Controlled PDF"})
    with path.open("wb") as output:
        _ = writer.write(output)


def _write_docx(path: Path) -> None:
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _CONTENT_TYPES)
        archive.writestr("_rels/.rels", _ROOT_RELS)
        archive.writestr("docProps/core.xml", _CORE)
        archive.writestr("word/document.xml", _DOCUMENT)


def _write_xlsx(path: Path) -> None:
    _ = make_workbook(path)
    core = _CORE.replace("Alice Word", "Alice Excel").replace(
        "Controlled Word fixture",
        "Controlled Excel fixture",
    )
    rewrite_package(path, {"docProps/core.xml": core}, {})


@pytest.mark.parametrize(
    ("name", "writer", "expected_author"),
    [
        ("controlled.pdf", _write_pdf, "Alice PDF"),
        ("controlled.docx", _write_docx, "Alice Word"),
        ("controlled.xlsx", _write_xlsx, "Alice Excel"),
    ],
)
def test_real_worker_extracts_each_major_family(
    tmp_path: Path,
    name: str,
    writer: Callable[[Path], None],
    expected_author: str,
) -> None:
    path = tmp_path / name
    writer(path)

    run = _scan(path)

    assert run.status in {ParserStatus.SUCCEEDED, ParserStatus.PARTIAL}
    authors = tuple(
        item.raw_value for item in run.observations if item.canonical_name == "author"
    )
    assert expected_author in authors
    assert all(
        "body must not be returned" not in str(item.raw_value)
        for item in run.observations
    )


def test_real_worker_extracts_legacy_xls_fixture() -> None:
    path = Path(__file__).resolve().parent.parent / "fixtures" / "metadata.xls"

    run = _scan(path)

    assert run.status in {ParserStatus.SUCCEEDED, ParserStatus.PARTIAL}
    authors = tuple(
        item.raw_value for item in run.observations if item.canonical_name == "author"
    )
    assert "Alice Analyst" in authors
