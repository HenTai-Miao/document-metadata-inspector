from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pypdf import PdfWriter

from document_metadata_inspector.models import (
    DocumentStatus,
    EmbeddedDocumentReport,
    EvidenceObservation,
    EvidenceStatus,
    InspectionLimits,
    ParserRun,
    ParserStatus,
)
from document_metadata_inspector.scanner import Scanner, ScanRequest

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from document_metadata_inspector.source import SourceSnapshot

    type PasswordProvider = Callable[[str], str | None]


def _write_pdf(path: Path, author: str = "Alice") -> Path:
    writer = PdfWriter()
    _ = writer.add_blank_page(width=100, height=100)
    writer.add_metadata({"/Author": author, "/Title": path.stem})
    with path.open("wb") as output:
        _ = writer.write(output)
    return path


@dataclass(slots=True)
class _FakeWorker:
    parser_name: str
    value: str = "Alice"
    request_password: bool = False
    mutate_path: Path | None = None
    embedded: bool = False

    def scan(
        self,
        snapshot: SourceSnapshot,
        password_provider: PasswordProvider | None,
        limits: InspectionLimits,
    ) -> ParserRun:
        del limits
        if self.request_password and password_provider is not None:
            _ = password_provider(snapshot.name)
        if self.mutate_path is not None:
            _ = self.mutate_path.write_bytes(b"%PDF-1.7\nchanged")
        observation = EvidenceObservation(
            canonical_name="author",
            raw_name=f"{self.parser_name}:author",
            raw_value=self.value,
            normalized_value=self.value.casefold(),
            value_type="string",
            source_kind=f"{self.parser_name}_metadata",
            location="root",
            parser_name=self.parser_name,
            parser_version="test",
        )
        return ParserRun(
            parser_name=self.parser_name,
            parser_version="test",
            status=ParserStatus.SUCCEEDED,
            observations=(observation,),
            embedded_documents=(
                EmbeddedDocumentReport(
                    resource_id=(
                        "c" * 64 if self.parser_name == "exiftool" else "a" * 64
                    ),
                    parent_id=snapshot.sha256,
                    depth=1,
                    path=(
                        "office/media/child.pdf"
                        if self.parser_name == "exiftool"
                        else "attachments/child.pdf"
                    ),
                    content_type="application/pdf",
                    size_bytes=0 if self.parser_name == "exiftool" else 10,
                    sha256="" if self.parser_name == "exiftool" else "b" * 64,
                    parser_names=(self.parser_name,),
                    warnings=(
                        ("embedded_descriptor_unresolved",)
                        if self.parser_name == "exiftool"
                        else ()
                    ),
                ),
            )
            if self.embedded
            else (),
        )


def _complete_scanner() -> Scanner:
    return Scanner(
        apache_worker=_FakeWorker("apache-tika"),
        exiftool_worker=_FakeWorker("exiftool"),
    )


def test_multi_file_scan_is_stable_and_merges_independent_engines(
    tmp_path: Path,
) -> None:
    second = _write_pdf(tmp_path / "b.pdf")
    first = _write_pdf(tmp_path / "A.pdf")

    report = _complete_scanner().scan(ScanRequest(paths=(second, first)))

    assert [document.display_name for document in report.documents] == [
        "A.pdf",
        "b.pdf",
    ]
    assert all(
        document.status is DocumentStatus.COMPLETE for document in report.documents
    )
    assert all(document.source_path_sha256 for document in report.documents)
    assert any(
        item.status is EvidenceStatus.CORROBORATED
        for item in report.documents[0].observations
        if item.canonical_name == "author"
    )


def test_one_corrupt_file_does_not_discard_a_successful_file(tmp_path: Path) -> None:
    good = _write_pdf(tmp_path / "good.pdf")
    bad = tmp_path / "bad.pdf"
    _ = bad.write_bytes(b"%PDF-1.7\nnot a valid object graph")
    scanner = Scanner(apache_worker=None, exiftool_worker=None)

    report = scanner.scan(ScanRequest(paths=(bad, good)))

    statuses = {document.display_name: document.status for document in report.documents}
    assert statuses["bad.pdf"] is DocumentStatus.FAILED
    assert statuses["good.pdf"] is DocumentStatus.PARTIAL


def test_directory_expansion_is_non_recursive_by_default(tmp_path: Path) -> None:
    direct = _write_pdf(tmp_path / "direct.pdf")
    nested_directory = tmp_path / "nested"
    nested_directory.mkdir()
    nested = _write_pdf(nested_directory / "nested.pdf")
    _ = (tmp_path / "ignored.txt").write_text("not a target", encoding="utf-8")
    scanner = _complete_scanner()

    shallow = scanner.scan(ScanRequest(paths=(tmp_path,)))
    recursive = scanner.scan(ScanRequest(paths=(tmp_path,), recursive=True))

    assert [item.display_name for item in shallow.documents] == [direct.name]
    assert [item.display_name for item in recursive.documents] == [
        direct.name,
        nested.name,
    ]


def test_password_provider_is_called_once_per_file_and_shared_in_memory(
    tmp_path: Path,
) -> None:
    path = _write_pdf(tmp_path / "password-routing.pdf")
    calls: list[str] = []
    scanner = Scanner(
        apache_worker=_FakeWorker("apache-tika", request_password=True),
        exiftool_worker=_FakeWorker("exiftool", request_password=True),
    )

    report = scanner.scan(
        ScanRequest(paths=(path,)),
        password_provider=lambda name: calls.append(name) or "memory-only",
    )

    assert report.documents[0].status is DocumentStatus.COMPLETE
    assert calls == [path.name]
    assert "memory-only" not in report.model_dump_json()


def test_source_change_invalidates_all_parser_success(tmp_path: Path) -> None:
    path = _write_pdf(tmp_path / "mutable.pdf")
    scanner = Scanner(
        apache_worker=_FakeWorker("apache-tika", mutate_path=path),
        exiftool_worker=_FakeWorker("exiftool"),
    )

    report = scanner.scan(ScanRequest(paths=(path,)))

    document = report.documents[0]
    assert document.status is DocumentStatus.FAILED
    assert any(run.error_code == "source_changed" for run in document.parser_runs)


def test_missing_required_engine_makes_coverage_partial(tmp_path: Path) -> None:
    path = _write_pdf(tmp_path / "partial.pdf")
    scanner = Scanner(
        apache_worker=_FakeWorker("apache-tika"),
        exiftool_worker=None,
    )

    report = scanner.scan(ScanRequest(paths=(path,)))

    document = report.documents[0]
    assert document.status is DocumentStatus.PARTIAL
    exiftool = next(
        run for run in document.parser_runs if run.parser_name == "exiftool"
    )
    assert exiftool.status is ParserStatus.SKIPPED
    assert exiftool.error_code == "parser_unavailable"


def test_document_report_keeps_worker_embedded_child_reports(tmp_path: Path) -> None:
    path = _write_pdf(tmp_path / "embedded.pdf")
    scanner = Scanner(
        apache_worker=_FakeWorker("apache-tika", embedded=True),
        exiftool_worker=_FakeWorker("exiftool", embedded=True),
    )

    report = scanner.scan(ScanRequest(paths=(path,)))

    child = report.documents[0].embedded_documents[0]
    assert len(report.documents[0].embedded_documents) == 1
    assert child.path == "attachments/child.pdf"
    assert child.parent_id == report.documents[0].sha256
    assert child.parser_names == ("apache-tika", "exiftool")
    assert child.resource_id == "a" * 64
    assert child.size_bytes == 10
    assert child.sha256 == "b" * 64
    assert child.warnings == ()
