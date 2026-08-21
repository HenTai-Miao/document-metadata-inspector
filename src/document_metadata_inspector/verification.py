"""Offline self-test that executes every parser against controlled documents."""

from __future__ import annotations

from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Literal, cast
from zipfile import ZIP_DEFLATED, ZipFile

from openpyxl import Workbook
from pydantic import Field
from pypdf import PdfWriter

from document_metadata_inspector.models import (
    DocumentReport,
    DocumentStatus,
    FrozenModel,
    ParserStatus,
)
from document_metadata_inspector.normalization import normalize_identity_text
from document_metadata_inspector.runtime import (
    RuntimeComponentStatus,
    RuntimeEnvironment,
)
from document_metadata_inspector.scanner import ScanRequest

if TYPE_CHECKING:
    from openpyxl.packaging.core import DocumentProperties


class VerificationStatus(StrEnum):
    """Describe one deterministic offline self-test outcome."""

    PASS = "pass"  # noqa: S105 - verification outcome, not a password
    FAIL = "fail"


class VerificationCheck(FrozenModel):
    """Expose one sanitized resource or sample verification result."""

    name: str
    status: VerificationStatus
    message: str


class VerificationReport(FrozenModel):
    """Contain versioned offline self-test evidence."""

    schema_version: Literal["1.0"] = "1.0"
    passed: bool
    checks: tuple[VerificationCheck, ...] = Field(default_factory=tuple)


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
_WORD_CORE = """<?xml version="1.0" encoding="UTF-8"?>
<cp:coreProperties
 xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/">
  <dc:creator>Verification Word</dc:creator>
  <dc:title>Offline verification document</dc:title>
</cp:coreProperties>
"""
_WORD_DOCUMENT = """<?xml version="1.0" encoding="UTF-8"?>
<w:document
 xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body><w:p/></w:body>
</w:document>
"""
_EXPECTED_AUTHORS = {
    "verification.pdf": "Verification PDF",
    "verification.docx": "Verification Word",
    "verification.xlsx": "Verification Excel",
}


def _write_pdf(path: Path) -> None:
    writer = PdfWriter()
    _ = writer.add_blank_page(width=72, height=72)
    writer.add_metadata(
        {
            "/Author": _EXPECTED_AUTHORS[path.name],
            "/Title": "Offline verification document",
        }
    )
    with path.open("wb") as stream:
        _ = writer.write(stream)


def _write_docx(path: Path) -> None:
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _CONTENT_TYPES)
        archive.writestr("_rels/.rels", _ROOT_RELS)
        archive.writestr("docProps/core.xml", _WORD_CORE)
        archive.writestr("word/document.xml", _WORD_DOCUMENT)


def _write_xlsx(path: Path) -> None:
    workbook = Workbook()
    try:
        properties = cast("DocumentProperties", workbook.properties)
        properties.creator = _EXPECTED_AUTHORS[path.name]
        properties.title = "Offline verification document"
        workbook.save(path)
    finally:
        workbook.close()


def _file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _component_checks(runtime: RuntimeEnvironment) -> list[VerificationCheck]:
    return [
        VerificationCheck(
            name=f"component:{component.name}",
            status=(
                VerificationStatus.PASS
                if component.status is RuntimeComponentStatus.READY
                else VerificationStatus.FAIL
            ),
            message=(
                f"{component.name} {component.version} is ready."
                if component.status is RuntimeComponentStatus.READY
                else f"{component.name} {component.version} is unavailable or invalid."
            ),
        )
        for component in runtime.components
    ]


def _sample_check(
    document: DocumentReport | None,
    expected_author: str,
    family: str,
) -> VerificationCheck:
    if document is None:
        return VerificationCheck(
            name=f"sample:{family}",
            status=VerificationStatus.FAIL,
            message="The controlled document did not produce a report.",
        )
    successful = {
        run.parser_name
        for run in document.parser_runs
        if run.status is ParserStatus.SUCCEEDED
    }
    expected_native = "native-pdf" if family == "pdf" else "native-office"
    required = {expected_native, "apache-tika", "exiftool"}
    author_parsers = {
        item.parser_name
        for item in document.observations
        if item.canonical_name == "author"
        and item.normalized_value == normalize_identity_text(expected_author)
    }
    passed = (
        document.status is DocumentStatus.COMPLETE
        and required <= successful
        and required <= author_parsers
    )
    return VerificationCheck(
        name=f"sample:{family}",
        status=VerificationStatus.PASS if passed else VerificationStatus.FAIL,
        message=(
            "All three parsers returned the controlled author trace."
            if passed
            else "One or more parsers failed the controlled metadata probe."
        ),
    )


def _sample_checks(runtime: RuntimeEnvironment) -> tuple[VerificationCheck, ...]:
    try:
        with TemporaryDirectory(prefix="docmeta-verify-") as directory_text:
            directory = Path(directory_text)
            paths = (
                directory / "verification.pdf",
                directory / "verification.docx",
                directory / "verification.xlsx",
            )
            _write_pdf(paths[0])
            _write_docx(paths[1])
            _write_xlsx(paths[2])
            initial_hashes = {path.name: _file_hash(path) for path in paths}
            scan = runtime.scanner.scan(
                ScanRequest(paths=paths, max_concurrency=1),
            )
            unchanged = all(
                _file_hash(path) == initial_hashes[path.name] for path in paths
            )
            documents = {item.display_name: item for item in scan.documents}
            checks = tuple(
                _sample_check(
                    documents.get(path.name),
                    _EXPECTED_AUTHORS[path.name],
                    path.suffix.removeprefix(".")
                    .replace("docx", "word")
                    .replace("xlsx", "excel"),
                )
                for path in paths
            )
            integrity = VerificationCheck(
                name="sample:source-integrity",
                status=(
                    VerificationStatus.PASS if unchanged else VerificationStatus.FAIL
                ),
                message=(
                    "Controlled source hashes were unchanged."
                    if unchanged
                    else "A controlled source changed during verification."
                ),
            )
            return (*checks, integrity)
    except (OSError, RuntimeError, ValueError):
        return (
            VerificationCheck(
                name="sample:execution",
                status=VerificationStatus.FAIL,
                message="The controlled offline verification could not be completed.",
            ),
        )


def verify_runtime(runtime: RuntimeEnvironment) -> VerificationReport:
    """Execute deterministic resource and three-family parser checks offline."""
    checks = (*_component_checks(runtime), *_sample_checks(runtime))
    return VerificationReport(
        passed=bool(checks)
        and all(check.status is VerificationStatus.PASS for check in checks),
        checks=checks,
    )


__all__ = (
    "VerificationCheck",
    "VerificationReport",
    "VerificationStatus",
    "verify_runtime",
)
