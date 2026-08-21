from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

import pytest

from document_metadata_inspector.desktop_bundle import (
    DesktopBundleError,
    DesktopBundleWriter,
)
from document_metadata_inspector.formats import identify_declared_format
from document_metadata_inspector.models import (
    DocumentReport,
    DocumentStatus,
    EmbeddedDocumentReport,
    EvidenceObservation,
    ParserRun,
    ParserStatus,
)

if TYPE_CHECKING:
    from pathlib import Path


def _observation(
    name: str,
    *,
    value: str | bool,
    parser: str = "native-pdf",
) -> EvidenceObservation:
    return EvidenceObservation(
        canonical_name=name,
        raw_name=name,
        raw_value=value,
        normalized_value=value.casefold() if isinstance(value, str) else value,
        value_type="string" if isinstance(value, str) else "boolean",
        source_kind="controlled",
        location="root",
        parser_name=parser,
        parser_version="test",
    )


def _document(
    document_id: str | None,
    *,
    name: str = "bid.pdf",
    status: DocumentStatus = DocumentStatus.COMPLETE,
) -> DocumentReport:
    observations = (
        _observation("author", value="Alice"),
        _observation("author", value="Alice", parser="exiftool"),
        _observation("digital_signature_present", value=True),
    )
    parser_run = ParserRun(
        parser_name="native-pdf",
        parser_version="test",
        status=ParserStatus.SUCCEEDED,
        observations=observations,
        warnings=("controlled_parser_warning",),
    )
    embedded = EmbeddedDocumentReport(
        resource_id="e" * 64,
        parent_id="f" * 64,
        depth=1,
        path="attachments/child.pdf",
        content_type="application/pdf",
        size_bytes=10,
        sha256="d" * 64,
        warnings=("controlled_embedded_warning",),
    )
    return DocumentReport(
        display_name=name,
        source_path_sha256=document_id,
        size_bytes=123,
        sha256="a" * 64,
        identity=identify_declared_format(name),
        status=status,
        observations=observations if status is DocumentStatus.COMPLETE else (),
        parser_runs=(parser_run,),
        warnings=("controlled_document_warning",),
        embedded_documents=(embedded,),
    )


def test_bundle_publishes_full_evidence_and_compact_deduplicated_details(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bundle"
    complete_id = "1" * 64
    failed_id = "2" * 64
    writer = DesktopBundleWriter(root)

    writer.add(_document(complete_id))
    assert not (root / "summary.json").exists()
    writer.add(
        _document(
            failed_id,
            name="broken.pdf",
            status=DocumentStatus.FAILED,
        )
    )
    summary = writer.finish(matches=(), warnings=("runtime_component:missing",))

    assert summary.document_count == 2
    assert summary.complete_document_count == 1
    assert summary.observation_count == 3
    assert summary.parser_run_count == 2
    assert [document.source_path_sha256 for document in summary.documents] == [
        complete_id,
        failed_id,
    ]
    complete = summary.documents[0]
    assert complete.observation_count == 3
    assert complete.warning_count == 3
    assert complete.parser_runs[0].warning_count == 1
    assert complete.key_fields.author == "Alice"

    detail_value = cast(
        "dict[str, object]",
        json.loads((root / "details" / f"{complete_id}.json").read_text("utf-8")),
    )
    observations = cast("list[dict[str, str]]", detail_value["observations"])
    assert observations == [
        {"label": "author", "value": "Alice"},
        {"label": "digital_signature_present", "value": "true"},
    ]

    evidence = DocumentReport.model_validate_json(
        (root / "evidence" / f"{complete_id}.json").read_text("utf-8")
    )
    assert evidence == _document(complete_id)
    published = type(summary).model_validate_json(
        (root / "summary.json").read_text("utf-8")
    )
    assert published == summary


@pytest.mark.parametrize("document_id", [None, "A" * 64, "../outside", "1" * 63])
def test_bundle_rejects_an_unsafe_document_identity(
    tmp_path: Path,
    document_id: str | None,
) -> None:
    writer = DesktopBundleWriter(tmp_path / "bundle")

    with pytest.raises(DesktopBundleError, match="identity"):
        writer.add(_document(document_id))

    assert not (tmp_path / "outside.json").exists()
    assert not (tmp_path / "bundle" / "summary.json").exists()


def test_bundle_refuses_to_overwrite_an_existing_result_root(tmp_path: Path) -> None:
    root = tmp_path / "bundle"
    root.mkdir()
    canary = root / "canary.txt"
    _ = canary.write_text("preserve", encoding="utf-8")

    with pytest.raises(DesktopBundleError, match="already exists"):
        _ = DesktopBundleWriter(root)

    assert canary.read_text(encoding="utf-8") == "preserve"


def test_bundle_rejects_a_duplicate_document_identity(tmp_path: Path) -> None:
    document_id = "3" * 64
    writer = DesktopBundleWriter(tmp_path / "bundle")
    writer.add(_document(document_id))

    with pytest.raises(DesktopBundleError, match="identity"):
        writer.add(_document(document_id, name="duplicate.pdf"))

    assert not (tmp_path / "bundle" / "summary.json").exists()
