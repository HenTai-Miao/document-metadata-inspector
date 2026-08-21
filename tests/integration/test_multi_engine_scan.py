"""Conditional end-to-end checks across all three metadata engines."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from pypdf import PdfWriter

from document_metadata_inspector.models import (
    DocumentStatus,
    EvidenceStatus,
    ParserStatus,
)
from document_metadata_inspector.resources import resolve_exiftool
from document_metadata_inspector.scanner import Scanner, ScanRequest
from document_metadata_inspector.workers.apache import ApacheWorker
from document_metadata_inspector.workers.exiftool import ExifToolWorker

_JAVA = os.environ.get("DOCMETA_JAVA")
_JAR = os.environ.get("DOCMETA_APACHE_WORKER_JAR")
_EXIFTOOL = os.environ.get("DOCMETA_EXIFTOOL")


def _write_pdf(path: Path) -> None:
    writer = PdfWriter()
    _ = writer.add_blank_page(width=100, height=100)
    writer.add_metadata(
        {
            "/Author": "Alice Multi Engine",
            "/Title": "Controlled end-to-end fixture",
        }
    )
    with path.open("wb") as output:
        _ = writer.write(output)


def _apache() -> ApacheWorker:
    assert _JAVA is not None
    assert _JAR is not None
    return ApacheWorker.from_runtime(Path(_JAVA), Path(_JAR))


def _exiftool() -> ExifToolWorker:
    root = Path(__file__).resolve().parents[2]
    resource = resolve_exiftool(
        root=root,
        development=True,
        environment=os.environ,
    )
    return ExifToolWorker(
        command_prefix=resource.command_prefix,
        version=resource.version,
    )


@pytest.mark.skipif(
    not (_JAVA and _JAR and _EXIFTOOL),
    reason="real multi-engine scan requires Java worker and ExifTool overrides",
)
def test_three_engines_corroborate_the_same_author(tmp_path: Path) -> None:
    path = tmp_path / "controlled.pdf"
    _write_pdf(path)
    scanner = Scanner(apache_worker=_apache(), exiftool_worker=_exiftool())

    report = scanner.scan(ScanRequest(paths=(path,)))

    document = report.documents[0]
    assert document.status is DocumentStatus.COMPLETE
    assert all(run.status is ParserStatus.SUCCEEDED for run in document.parser_runs)
    authors = tuple(
        item
        for item in document.observations
        if item.canonical_name == "author"
        and item.normalized_value == "alice multi engine"
    )
    assert len({item.parser_name for item in authors}) == 3
    assert all(item.status is EvidenceStatus.CORROBORATED for item in authors)


@pytest.mark.skipif(
    not (_JAVA and _JAR),
    reason="partial-coverage integration check requires the Java worker",
)
def test_missing_exiftool_prevents_a_complete_claim(tmp_path: Path) -> None:
    path = tmp_path / "controlled.pdf"
    _write_pdf(path)
    scanner = Scanner(apache_worker=_apache(), exiftool_worker=None)

    report = scanner.scan(ScanRequest(paths=(path,)))

    document = report.documents[0]
    assert document.status is DocumentStatus.PARTIAL
    exiftool = next(
        run for run in document.parser_runs if run.parser_name == "exiftool"
    )
    assert exiftool.status is ParserStatus.SKIPPED
    assert exiftool.error_code == "parser_unavailable"
