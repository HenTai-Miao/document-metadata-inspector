from __future__ import annotations

import sys
from textwrap import dedent
from typing import TYPE_CHECKING

import pytest

from document_metadata_inspector.models import InspectionLimits, ParserStatus
from document_metadata_inspector.source import SourceSnapshot, open_source_snapshot
from document_metadata_inspector.workers.exiftool import ExifToolWorker

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


def test_command_is_fixed_read_only_and_receives_dynamic_data_on_stdin() -> None:
    worker = ExifToolWorker(command_prefix=("/app/tools/exiftool",))

    command = worker.build_command()

    assert command == (
        "/app/tools/exiftool",
        "-json",
        "-a",
        "-u",
        "-U",
        "-G3:1",
        "-struct",
        "-ee3",
        "-api",
        "RequestAll=3",
        "-api",
        "LargeFileSupport=1",
        "--System:all",
        "--MacOS:all",
        "--ExifTool:Now",
        "--ExifTool:NewGUID",
        "--ExifTool:FileSequence",
        "--ExifTool:ProcessingTime",
        "-@",
        "-",
    )
    assert all("source.pdf" not in argument for argument in command)
    assert not any(
        argument in {"-w", "-o", "-overwrite_original"} for argument in command
    )


def test_success_preserves_values_without_requesting_a_password(
    source: SourceSnapshot,
) -> None:
    worker = ExifToolWorker(
        command_prefix=_command(
            """
            import json, sys
            assert "memory-only" not in sys.argv
            arguments = sys.stdin.read().splitlines()
            assert "-password" not in arguments
            print(json.dumps([{
                "SourceFile": arguments[-1],
                "ExifTool:ExifToolVersion": 13.55,
                "File:FileType": "PDF",
                "XMP-dc:Creator": ["Alice", "ALICE"],
                "XMP-xmp:Rating": 5,
                "XMP:Structured": {"Role": "Reviewer", "Active": True},
            }]))
            """
        )
    )

    def unexpected_prompt(_: str) -> str:
        message = "ordinary documents must not request a password"
        raise AssertionError(message)

    run = worker.scan(source, unexpected_prompt, InspectionLimits())

    assert run.status is ParserStatus.SUCCEEDED
    creators = [item for item in run.observations if item.raw_name == "XMP-dc:Creator"]
    assert creators[0].raw_value == ("Alice", "ALICE")
    structured = next(
        item for item in run.observations if item.raw_name == "XMP:Structured"
    )
    assert structured.raw_value == {"Role": "Reviewer", "Active": True}
    assert all("memory-only" not in str(item.raw_value) for item in run.observations)


def test_pdf_creator_is_application_while_xmp_creator_remains_author(
    source: SourceSnapshot,
) -> None:
    worker = ExifToolWorker(
        command_prefix=_command(
            """
            import json, sys
            arguments = sys.stdin.read().splitlines()
            print(json.dumps([{
                "SourceFile": arguments[-1],
                "ExifTool:ExifToolVersion": 13.55,
                "PDF:Creator": "WPS 文字",
                "XMP-dc:Creator": "Alice",
            }]))
            """
        )
    )

    run = worker.scan(source, None, InspectionLimits())

    by_raw_name = {item.raw_name: item for item in run.observations}
    assert by_raw_name["PDF:Creator"].canonical_name == "application"
    assert by_raw_name["XMP-dc:Creator"].canonical_name == "author"


def test_embedded_exiftool_groups_cannot_become_root_identity_fields(
    source: SourceSnapshot,
) -> None:
    worker = ExifToolWorker(
        command_prefix=_command(
            """
            import json, sys
            arguments = sys.stdin.read().splitlines()
            print(json.dumps([{
                "SourceFile": arguments[-1],
                "ExifTool:ExifToolVersion": 13.55,
                "Main:XMP-dc:Creator": "Root Main",
                "Doc1:ZIP:ZipFileName": "docProps/core.xml",
                "Doc1:XMP-dc:Creator": "Root Core",
                "Doc2:ZIP:ZipFileName": "word/embeddings/object1.bin",
                "Doc2:XMP-dc:Creator": "Embedded Author",
                "Doc3:ZIP:ZipFileName": "xl/worksheets/sheet1.xml",
                "Doc3:XMP-dc:Creator": "Internal Part Author",
            }]))
            """
        )
    )

    run = worker.scan(source, None, InspectionLimits())

    root_authors = {
        str(item.raw_value)
        for item in run.observations
        if item.canonical_name == "author"
    }
    assert all(item.source_kind != "exiftool_embedded_tag" for item in run.observations)
    assert len(run.embedded_documents) == 1
    child = run.embedded_documents[0]
    embedded = next(
        item for item in child.observations if item.raw_name == "Doc2:XMP-dc:Creator"
    )
    assert root_authors == {"Root Main", "Root Core"}
    assert child.parent_id == source.sha256
    assert child.path == "word/embeddings/object1.bin"
    assert child.parser_names == ("exiftool",)
    assert child.sha256 == ""
    assert child.warnings == ("embedded_descriptor_unresolved",)
    assert embedded.canonical_name == "exiftool.embedded.author"
    assert embedded.location == "word/embeddings/object1.bin"
    internal = next(
        item for item in run.observations if item.raw_name == "Doc3:XMP-dc:Creator"
    )
    assert internal.canonical_name == "exiftool.internal_part.author"
    assert internal.source_kind == "exiftool_internal_part_tag"
    assert internal.location == "xl/worksheets/sheet1.xml"


def test_password_is_requested_only_after_exiftool_reports_it_is_required(
    source: SourceSnapshot,
) -> None:
    worker = ExifToolWorker(
        command_prefix=_command(
            """
            import json, sys
            arguments = sys.stdin.read().splitlines()
            if "-password" not in arguments:
                print(json.dumps([{
                    "SourceFile": arguments[-1],
                    "ExifTool:ExifToolVersion": 13.55,
                    "ExifTool:Error": "File is encrypted; use the -password option",
                }]))
            else:
                assert arguments[0:2] == ["-password", "memory-only"]
                print(json.dumps([{
                    "SourceFile": arguments[-1],
                    "ExifTool:ExifToolVersion": 13.55,
                    "PDF:Author": "Alice",
                }]))
            """
        )
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
        ("import sys; sys.exit(1)", "parser_crashed"),
        ("print('not-json')", "parser_output_invalid"),
        ("print('[]')", "parser_output_invalid"),
    ],
)
def test_process_failures_are_sanitized(
    source: SourceSnapshot,
    program: str,
    expected_code: str,
) -> None:
    worker = ExifToolWorker(command_prefix=_command(program))

    run = worker.scan(source, None, InspectionLimits())

    assert run.status is ParserStatus.FAILED
    assert run.error_code == expected_code
    assert all("source.pdf" not in warning for warning in run.warnings)


def test_timeout_and_excess_output_are_bounded(source: SourceSnapshot) -> None:
    timeout_worker = ExifToolWorker(
        command_prefix=_command("import time; time.sleep(5)"),
    )
    output_worker = ExifToolWorker(
        command_prefix=_command("print('x' * 1000000)"),
    )

    timed_out = timeout_worker.scan(
        source,
        None,
        InspectionLimits(parser_timeout_seconds=0.05),
    )
    excessive = output_worker.scan(
        source,
        None,
        InspectionLimits(max_worker_output_bytes=1024),
    )

    assert timed_out.status is ParserStatus.TIMED_OUT
    assert timed_out.error_code == "parser_timeout"
    assert excessive.error_code == "resource_limit_exceeded"


def test_staged_source_mutation_is_detected(source: SourceSnapshot) -> None:
    worker = ExifToolWorker(
        command_prefix=_command(
            """
            import json, pathlib, sys
            arguments = sys.stdin.read().splitlines()
            path = pathlib.Path(arguments[-1])
            path.write_bytes(path.read_bytes() + b"changed")
            print(json.dumps([{
                "SourceFile": str(path),
                "ExifTool:ExifToolVersion": 13.55,
                "File:FileType": "PDF",
            }]))
            """
        )
    )

    run = worker.scan(source, None, InspectionLimits())

    assert run.status is ParserStatus.FAILED
    assert run.error_code == "source_changed"


def test_missing_exiftool_is_explicitly_unavailable(source: SourceSnapshot) -> None:
    worker = ExifToolWorker(
        command_prefix=("/definitely/missing/document-metadata-exiftool",),
    )

    run = worker.scan(source, None, InspectionLimits())

    assert run.status is ParserStatus.SKIPPED
    assert run.error_code == "parser_unavailable"
