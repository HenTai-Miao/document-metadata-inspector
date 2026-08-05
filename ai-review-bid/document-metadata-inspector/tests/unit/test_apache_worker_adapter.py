from __future__ import annotations

import sys
from textwrap import dedent
from typing import TYPE_CHECKING

import pytest

import document_metadata_inspector.workers.apache as apache_module
from document_metadata_inspector.models import InspectionLimits, ParserStatus
from document_metadata_inspector.source import SourceSnapshot, open_source_snapshot
from document_metadata_inspector.workers.apache import ApacheWorker

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


def _command(program: str) -> tuple[str, ...]:
    return (sys.executable, "-c", dedent(program))


@pytest.fixture
def source(tmp_path: Path) -> Iterator[SourceSnapshot]:
    path = tmp_path / "source.pdf"
    _ = path.write_bytes(b"%PDF-1.7\ncontrolled")
    with open_source_snapshot(path, InspectionLimits()) as snapshot:
        yield snapshot


def test_success_preserves_duplicate_values_without_requesting_a_password(
    source: SourceSnapshot,
) -> None:
    command = _command(
        """
        import json, sys
        request = json.loads(sys.stdin.readline())
        assert request["password_token"] is None
        print(json.dumps({
            "request_id": request["request_id"],
            "status": "ok",
            "content_type": "application/pdf",
            "metadata": {"dc:creator": ["Alice", "ALICE"]},
            "embedded_resources": [{
                "path": "attachment.txt",
                "content_type": "text/plain",
                "size_bytes": 12,
            }],
            "warnings": [],
        }))
        """
    )
    worker = ApacheWorker(command=command, version="3.3.2")

    def unexpected_prompt(_: str) -> str:
        message = "ordinary documents must not request a password"
        raise AssertionError(message)

    run = worker.scan(source, unexpected_prompt, InspectionLimits())

    assert run.status is ParserStatus.SUCCEEDED
    assert [
        item.raw_value for item in run.observations if item.canonical_name == "author"
    ] == ["Alice", "ALICE"]
    assert all("memory-only" not in str(item) for item in run.observations)
    embedded = [
        item for item in run.observations if item.canonical_name == "embedded_resource"
    ]
    assert embedded[0].raw_value == {
        "path": "attachment.txt",
        "content_type": "text/plain",
        "size_bytes": 12,
    }


def test_embedded_metadata_cannot_override_document_root_fields(
    source: SourceSnapshot,
) -> None:
    worker = ApacheWorker(
        command=_command(
            """
            import json, sys
            request = json.loads(sys.stdin.readline())
            print(json.dumps({
                "request_id": request["request_id"],
                "status": "ok",
                "content_type": (
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
                "metadata": {
                    "dcterms:created": ["2024-07-11T07:07:00Z"],
                    "embedded[0].dcterms:created": ["2024-07-11T15:46:02"],
                },
                "embedded_resources": [],
                "warnings": [],
            }))
            """
        ),
        version="3.3.2",
    )

    run = worker.scan(source, None, InspectionLimits())

    root = next(item for item in run.observations if item.location == "root")
    embedded = next(item for item in run.observations if item.location == "embedded[0]")
    assert root.canonical_name == "created_at"
    assert embedded.canonical_name == "apache_tika.embedded.created_at"
    assert embedded.raw_name == "embedded[0].dcterms:created"


def test_embedded_metadata_is_returned_as_an_independent_hashed_child_report(
    source: SourceSnapshot,
) -> None:
    worker = ApacheWorker(
        command=_command(
            """
            import json, sys
            request = json.loads(sys.stdin.readline())
            print(json.dumps({
                "request_id": request["request_id"],
                "status": "ok",
                "content_type": "application/pdf",
                "metadata": {
                    "dc:creator": ["Root Author"],
                    "embedded[0].dc:creator": ["Child Author"],
                },
                "embedded_resources": [{
                    "resource_id": "a" * 64,
                    "parent_id": request["source_sha256"],
                    "depth": 1,
                    "path": "attachments/child.docx",
                    "content_type": (
                        "application/vnd.openxmlformats-officedocument."
                        "wordprocessingml.document"
                    ),
                    "size_bytes": 123,
                    "sha256": "b" * 64,
                }],
                "warnings": [],
            }))
            """
        ),
        version="3.3.2",
    )

    run = worker.scan(source, None, InspectionLimits())

    assert [
        item.raw_value for item in run.observations if item.canonical_name == "author"
    ] == ["Root Author"]
    child = run.embedded_documents[0]
    assert child.resource_id == "a" * 64
    assert child.parent_id == source.sha256
    assert child.depth == 1
    assert child.path == "attachments/child.docx"
    assert child.size_bytes == 123
    assert child.sha256 == "b" * 64
    assert child.parser_names == ("apache-tika",)
    assert child.observations[0].canonical_name == "author"
    assert child.observations[0].raw_value == "Child Author"


def test_password_is_requested_only_after_the_worker_reports_it_is_required(
    source: SourceSnapshot,
) -> None:
    worker = ApacheWorker(
        command=_command(
            """
            import json, sys
            request = json.loads(sys.stdin.readline())
            if request["password_token"] is None:
                print(json.dumps({
                    "request_id": request["request_id"],
                    "status": "failed",
                    "metadata": {}, "embedded_resources": [], "warnings": [],
                    "error": {"code": "password_required", "message": "required"},
                }))
            else:
                assert request["password_token"] == "memory-only"
                print(json.dumps({
                    "request_id": request["request_id"],
                    "status": "ok", "content_type": "application/pdf",
                    "metadata": {"dc:creator": ["Alice"]},
                    "embedded_resources": [], "warnings": [],
                }))
            """
        ),
        version="3.3.2",
    )
    prompts: list[str] = []

    def password(source_name: str) -> str:
        prompts.append(source_name)
        return "memory-only"

    run = worker.scan(source, password, InspectionLimits())

    assert run.status is ParserStatus.SUCCEEDED
    assert prompts == ["source.pdf"]


@pytest.mark.parametrize(
    ("program", "expected_code"),
    [
        ("import sys; sys.exit(7)", "parser_crashed"),
        ("print('not-json')", "parser_output_invalid"),
        (
            """
            import json, sys
            json.loads(sys.stdin.readline())
            print(json.dumps({
                "request_id": "wrong-id", "status": "ok",
                "content_type": "application/pdf", "metadata": {},
                "embedded_resources": [], "warnings": [],
            }))
            """,
            "parser_output_invalid",
        ),
    ],
)
def test_worker_process_failures_are_sanitized(
    source: SourceSnapshot,
    program: str,
    expected_code: str,
) -> None:
    worker = ApacheWorker(command=_command(program), version="3.3.2")

    run = worker.scan(source, None, InspectionLimits())

    assert run.status is ParserStatus.FAILED
    assert run.error_code == expected_code
    assert all("source.pdf" not in warning for warning in run.warnings)


def test_timeout_kills_the_worker(source: SourceSnapshot) -> None:
    worker = ApacheWorker(
        command=_command("import time; time.sleep(5)"),
        version="3.3.2",
    )
    limits = InspectionLimits(parser_timeout_seconds=0.05)

    run = worker.scan(source, None, limits)

    assert run.status is ParserStatus.TIMED_OUT
    assert run.error_code == "parser_timeout"


def test_excess_output_is_rejected_without_buffering_it_all(
    source: SourceSnapshot,
) -> None:
    worker = ApacheWorker(
        command=_command("print('x' * 1000000)"),
        version="3.3.2",
    )
    limits = InspectionLimits(max_worker_output_bytes=1024)

    run = worker.scan(source, None, limits)

    assert run.status is ParserStatus.FAILED
    assert run.error_code == "resource_limit_exceeded"


def test_worker_process_is_killed_when_its_memory_budget_is_exceeded(
    source: SourceSnapshot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = ApacheWorker(
        command=_command("import time; time.sleep(5)"),
        version="3.3.2",
    )

    def controlled_rss(process_id: int) -> int:
        del process_id
        return 10_000

    monkeypatch.setattr(
        apache_module,
        "_process_tree_rss",
        controlled_rss,
        raising=False,
    )

    run = worker.scan(
        source,
        None,
        InspectionLimits(
            parser_timeout_seconds=2,
            max_worker_memory_bytes=1024,
        ),
    )

    assert run.status is ParserStatus.FAILED
    assert run.error_code == "resource_limit_exceeded"


def test_missing_worker_is_explicitly_unavailable(source: SourceSnapshot) -> None:
    worker = ApacheWorker(
        command=("/definitely/missing/document-metadata-java",),
        version="3.3.2",
    )

    run = worker.scan(source, None, InspectionLimits())

    assert run.status is ParserStatus.SKIPPED
    assert run.error_code == "parser_unavailable"
