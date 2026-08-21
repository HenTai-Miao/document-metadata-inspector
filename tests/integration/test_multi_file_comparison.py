"""Native scan-to-comparison integration for exact author traces."""

from pathlib import Path

from pypdf import PdfWriter

from document_metadata_inspector.comparison import ComparisonRequest, compare_documents
from document_metadata_inspector.models import TraceKind
from document_metadata_inspector.scanner import Scanner, ScanRequest


def _write_pdf(path: Path, author: str) -> None:
    writer = PdfWriter()
    _ = writer.add_blank_page(width=100, height=100)
    writer.add_metadata({"/Author": author, "/Title": "Shared title is ignored"})
    with path.open("wb") as output:
        _ = writer.write(output)


def test_scanned_pdf_authors_form_only_exact_cross_file_trace(tmp_path: Path) -> None:
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"
    unrelated = tmp_path / "unrelated.pdf"
    _write_pdf(first, "  \uff21lice  Zhang ")
    _write_pdf(second, "alice\tzhang")
    _write_pdf(unrelated, "Alice")
    scanner = Scanner(apache_worker=None, exiftool_worker=None)
    scanned = scanner.scan(ScanRequest(paths=(unrelated, second, first)))

    compared = compare_documents(ComparisonRequest(documents=scanned.documents))

    person_matches = tuple(
        match for match in compared.matches if match.trace_kind is TraceKind.PERSON
    )
    assert len(person_matches) == 1
    match = person_matches[0]
    assert match.normalized_value == "alice zhang"
    assert match.document_names == ("first.pdf", "second.pdf")
    assert match.trace_kind is TraceKind.PERSON
    assert match.field_names == ("author",)
