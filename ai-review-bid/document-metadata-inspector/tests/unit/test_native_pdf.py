"""Native PDF metadata, forensic structure and encryption adapter tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pypdf import PdfWriter
from pypdf.annotations import Text
from pypdf.generic import (
    ArrayObject,
    ByteStringObject,
    DictionaryObject,
    NameObject,
    NumberObject,
    RectangleObject,
    TextStringObject,
)

from document_metadata_inspector.formats import identify_format
from document_metadata_inspector.models import (
    InspectionLimits,
    JsonValue,
    ParserRun,
    ParserStatus,
)
from document_metadata_inspector.native.pdf import extract_native_pdf
from document_metadata_inspector.source import open_source_snapshot

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

_XMP = b"""<?xpacket begin=""?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
          xmlns:dc="http://purl.org/dc/elements/1.1/"
          xmlns:xmp="http://ns.adobe.com/xap/1.0/"
          xmlns:case="https://example.test/case/">
  <rdf:Description rdf:about="" case:CaseId="BID-2026-08">
   <dc:creator><rdf:Seq><rdf:li>Alice XMP</rdf:li></rdf:Seq></dc:creator>
   <xmp:CreatorTool>Metadata Fixture</xmp:CreatorTool>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>
"""


def _add_form_and_signature(writer: PdfWriter) -> None:
    text_widget = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Widget"),
            NameObject("/FT"): NameObject("/Tx"),
            NameObject("/T"): TextStringObject("BidderName"),
            NameObject("/V"): TextStringObject("Sensitive form content"),
            NameObject("/Rect"): RectangleObject((5, 5, 40, 15)),
        }
    )
    _ = writer.add_annotation(0, text_widget)

    signature = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Sig"),
            NameObject("/Filter"): NameObject("/Adobe.PPKLite"),
            NameObject("/SubFilter"): NameObject("/adbe.pkcs7.detached"),
            NameObject("/ByteRange"): ArrayObject(
                [NumberObject(0), NumberObject(10), NumberObject(20), NumberObject(30)]
            ),
            NameObject("/Contents"): ByteStringObject(b"not-a-valid-signature"),
            NameObject("/Name"): TextStringObject("CN=Example Signer"),
            NameObject("/Reason"): TextStringObject("Approval"),
        }
    )
    signature_widget = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Widget"),
            NameObject("/FT"): NameObject("/Sig"),
            NameObject("/T"): TextStringObject("ApprovalSignature"),
            NameObject("/V"): signature,
            NameObject("/Rect"): RectangleObject((5, 20, 40, 30)),
        }
    )
    _ = writer.add_annotation(0, signature_widget)
    _ = writer.reattach_fields()


def _write_pdf(path: Path, *, password: str | None = None) -> Path:
    writer = PdfWriter()
    _ = writer.add_blank_page(width=72, height=72)
    writer.add_metadata(
        {
            "/Author": "  Alice PDF  ",
            "/Creator": "Fixture Creator",
            "/Producer": "Fixture Producer",
            "/CreationDate": "D:20260805010203+08'00'",
            "/CaseCode": "BID-42",
        }
    )
    writer.xmp_metadata = _XMP
    writer.generate_file_identifiers()
    _ = writer.add_attachment("evidence.txt", b"embedded payload")
    annotation = Text(
        rect=(5, 35, 20, 50),
        text="Private annotation body",
        title_bar="Comment Author",
    )
    _ = writer.add_annotation(0, annotation)
    _add_form_and_signature(writer)
    if password is not None:
        writer.encrypt(password, algorithm="AES-256")
    with path.open("wb") as output:
        _ = writer.write(output)
    return path


def _extract(
    path: Path,
    password_provider: Callable[[str], str | None] | None = None,
) -> ParserRun:
    with open_source_snapshot(path, InspectionLimits()) as snapshot:
        header = snapshot.stream.read(1024)
        _ = snapshot.stream.seek(0)
        identity = identify_format(path, header)
        return extract_native_pdf(snapshot, identity, password_provider)


def _values(run: ParserRun, canonical_name: str) -> tuple[JsonValue, ...]:
    return tuple(
        observation.raw_value
        for observation in run.observations
        if observation.canonical_name == canonical_name
    )


def test_pdf_extracts_info_xmp_ids_annotations_forms_attachments_and_signature(
    tmp_path: Path,
) -> None:
    run = _extract(_write_pdf(tmp_path / "evidence.pdf"))

    assert all(item.parser_name == "native-pdf" for item in run.observations)

    assert run.status is ParserStatus.SUCCEEDED
    assert _values(run, "author") == ("  Alice PDF  ", "Alice XMP")
    assert _values(run, "creator_application") == (
        "Fixture Creator",
        "Metadata Fixture",
    )
    assert _values(run, "pdf_trailer_id")
    assert _values(run, "annotation_author") == ("Comment Author",)
    assert _values(run, "annotation_body_sha256")
    assert _values(run, "form_field_name") == (
        "ApprovalSignature",
        "BidderName",
    )
    assert _values(run, "form_field_value_sha256")
    assert _values(run, "embedded_file_name") == ("evidence.txt",)
    assert _values(run, "digital_signature_present") == (True,)
    assert _values(run, "signature_crypto_valid") == (False,)
    assert _values(run, "signature_signer_name") == ("CN=Example Signer",)
    assert _values(run, "xmp.caseid") == ("BID-2026-08",)

    annotation_hash = _values(run, "annotation_body_sha256")[0]
    assert isinstance(annotation_hash, str)
    serialized = run.model_dump_json()
    assert "Private annotation body" not in serialized
    assert annotation_hash in serialized
    assert "Sensitive form content" not in serialized


def test_encrypted_pdf_requires_an_in_memory_password(tmp_path: Path) -> None:
    password = "correct horse"  # noqa: S105
    path = _write_pdf(tmp_path / "encrypted.pdf", password=password)

    missing = _extract(path)
    wrong = _extract(path, lambda _: "wrong password")
    correct = _extract(path, lambda _: password)

    assert missing.status is ParserStatus.FAILED
    assert missing.error_code == "password_required"
    assert wrong.status is ParserStatus.FAILED
    assert wrong.error_code == "wrong_password"
    assert correct.status is ParserStatus.SUCCEEDED
    assert _values(correct, "pdf_encrypted") == (True,)
    assert _values(correct, "pdf_permissions")
    assert _values(correct, "pdf_permissions_integrity_valid") == (True,)
    assert "correct horse" not in correct.model_dump_json()


def test_invalid_pdf_returns_a_stable_failure(tmp_path: Path) -> None:
    path = tmp_path / "broken.pdf"
    _ = path.write_bytes(b"%PDF-1.7\nnot a real object graph")

    run = _extract(path)

    assert run.status is ParserStatus.FAILED
    assert run.error_code == "corrupt_container"
