from __future__ import annotations

import json
import os
from hashlib import sha256
from typing import TYPE_CHECKING, cast

import pytest
from pypdf import PdfWriter
from typer.testing import CliRunner

import document_metadata_inspector.cli as cli_module
from document_metadata_inspector.exporters import (
    ExportFormat,
    ExportTarget,
    export_report,
)
from document_metadata_inspector.models import ComparisonReport, ScanReport
from document_metadata_inspector.runtime import (
    RuntimeComponent,
    RuntimeComponentStatus,
    RuntimeEnvironment,
)
from document_metadata_inspector.scanner import Scanner
from tests.export_factories import make_export_report

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

_DESKTOP_MANIFEST_LINE_BYTES = 128 * 1024


def _write_pdf(path: Path, author: str = "Alice") -> Path:
    writer = PdfWriter()
    _ = writer.add_blank_page(width=72, height=72)
    writer.add_metadata({"/Author": author})
    with path.open("wb") as stream:
        _ = writer.write(stream)
    return path


def _native_only_runtime() -> RuntimeEnvironment:
    components = (
        RuntimeComponent(
            name="apache-tika",
            version="3.3.2",
            status=RuntimeComponentStatus.UNAVAILABLE,
        ),
        RuntimeComponent(
            name="exiftool",
            version="13.55",
            status=RuntimeComponentStatus.UNAVAILABLE,
        ),
    )
    return RuntimeEnvironment(
        scanner=Scanner(apache_worker=None, exiftool_worker=None),
        components=components,
    )


def _source_path_id(path: Path) -> str:
    resolved = str(path.resolve(strict=False)).encode("utf-8", errors="surrogatepass")
    return sha256(resolved).hexdigest()


def _write_desktop_manifest(
    path: Path,
    documents: tuple[tuple[Path, str], ...],
) -> None:
    lines = [json.dumps({"schema_version": "2.0", "type": "manifest"})]
    lines.extend(
        json.dumps(
            {
                "type": "document",
                "path": str(document),
                "source_path_sha256": _source_path_id(document),
                "group_id": group_id,
            }
        )
        for document, group_id in documents
    )
    _ = path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_scan_writes_a_strict_report_and_returns_partial_exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_pdf(tmp_path / "controlled.pdf")
    output = tmp_path / "scan.json"
    monkeypatch.setattr(cli_module, "create_runtime", _native_only_runtime)

    result = CliRunner().invoke(
        cli_module.app,
        ["scan", str(source), "--json", str(output)],
    )

    assert result.exit_code == cli_module.EXIT_PARTIAL
    report = ScanReport.model_validate_json(output.read_text(encoding="utf-8"))
    assert report.documents[0].display_name == source.name
    assert report.documents[0].sha256
    assert "runtime_component:apache-tika:unavailable" in report.warnings
    value = cast("object", json.loads(result.stdout))
    assert isinstance(value, dict)
    summary = cast("dict[str, object]", value)
    assert summary["document_count"] == 1
    assert summary["complete"] is False


def test_scan_summary_counts_report_document_and_parser_warnings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = make_export_report()
    output = tmp_path / "scan.json"

    def scan_inputs(
        paths: list[Path],
        *,
        recursive: bool,
        max_concurrency: int | None,
        prompt_password: bool,
    ) -> ScanReport:
        del paths, recursive, max_concurrency, prompt_password
        return report

    monkeypatch.setattr(cli_module, "_scan_inputs", scan_inputs)

    result = CliRunner().invoke(
        cli_module.app,
        ["scan", str(tmp_path / "controlled.pdf"), "--json", str(output)],
    )

    summary = cast("dict[str, object]", json.loads(result.stdout))
    assert summary["warning_count"] == 4


def test_compare_preserves_scan_evidence_and_exact_matches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _write_pdf(tmp_path / "first.pdf", "  Alice  ")
    second = _write_pdf(tmp_path / "second.pdf", "alice")
    output = tmp_path / "comparison.json"
    monkeypatch.setattr(cli_module, "create_runtime", _native_only_runtime)

    result = CliRunner().invoke(
        cli_module.app,
        ["compare", str(first), str(second), "--json", str(output)],
    )

    assert result.exit_code == cli_module.EXIT_PARTIAL
    report = ComparisonReport.model_validate_json(output.read_text(encoding="utf-8"))
    assert len(report.documents) == 2
    assert any(match.normalized_value == "alice" for match in report.matches)
    assert "runtime_component:exiftool:unavailable" in report.warnings


def test_compare_can_treat_each_top_level_directory_as_one_group(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bidder_a = tmp_path / "bidder-a"
    bidder_b = tmp_path / "bidder-b"
    bidder_a.mkdir()
    bidder_b.mkdir()
    _ = _write_pdf(bidder_a / "technical.pdf", "Alice")
    _ = _write_pdf(bidder_a / "pricing.pdf", "alice")
    _ = _write_pdf(bidder_b / "technical.pdf", "Bob")
    output = tmp_path / "comparison.json"
    monkeypatch.setattr(cli_module, "create_runtime", _native_only_runtime)

    result = CliRunner().invoke(
        cli_module.app,
        [
            "compare",
            str(tmp_path),
            "--recursive",
            "--group-by-top-level-dir",
            "--json",
            str(output),
        ],
    )

    assert result.exit_code == cli_module.EXIT_PARTIAL
    report = ComparisonReport.model_validate_json(output.read_text(encoding="utf-8"))
    assert not any(match.normalized_value == "alice" for match in report.matches)


def test_compare_manifest_keeps_nested_files_in_the_same_bidder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bidder_a = tmp_path / "bidder-a"
    nested = bidder_a / "technical"
    bidder_b = tmp_path / "bidder-b"
    nested.mkdir(parents=True)
    bidder_b.mkdir()
    direct = _write_pdf(bidder_a / "pricing.pdf", "Alice")
    technical = _write_pdf(nested / "technical.pdf", "alice")
    other = _write_pdf(bidder_b / "technical.pdf", "Bob")
    manifest = tmp_path / "input-manifest.json"
    output = tmp_path / "comparison.json"
    _ = manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "documents": [
                    {
                        "path": str(path),
                        "source_path_sha256": _source_path_id(path),
                        "group_id": group_id,
                    }
                    for path, group_id in (
                        (direct, "bidder-a"),
                        (technical, "bidder-a"),
                        (other, "bidder-b"),
                    )
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli_module, "create_runtime", _native_only_runtime)

    result = CliRunner().invoke(
        cli_module.app,
        [
            "compare",
            "--input-manifest",
            str(manifest),
            "--json",
            str(output),
        ],
    )

    assert result.exit_code == cli_module.EXIT_PARTIAL
    report = ComparisonReport.model_validate_json(output.read_text(encoding="utf-8"))
    assert not any(match.normalized_value == "alice" for match in report.matches)


def test_desktop_compare_streams_a_private_bundle_and_progress(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _write_pdf(tmp_path / "first.pdf", "Alice")
    second = _write_pdf(tmp_path / "second.pdf", "alice")
    manifest = tmp_path / "input-manifest.jsonl"
    output = tmp_path / "result"
    _write_desktop_manifest(
        manifest,
        ((first, "bidder-a"), (second, "bidder-b")),
    )
    monkeypatch.setattr(cli_module, "create_runtime", _native_only_runtime)

    result = CliRunner().invoke(
        cli_module.app,
        [
            "desktop-compare",
            str(manifest),
            "--output",
            str(output),
            "--max-concurrency",
            "2",
        ],
    )

    assert result.exit_code == cli_module.EXIT_PARTIAL
    messages = [json.loads(line) for line in result.stdout.splitlines()]
    assert messages[:2] == [
        {"completed": 1, "total": 2, "type": "progress"},
        {"completed": 2, "total": 2, "type": "progress"},
    ]
    assert messages[-1]["type"] == "result"
    summary = cast(
        "dict[str, object]",
        json.loads((output / "summary.json").read_text(encoding="utf-8")),
    )
    assert summary["document_count"] == 2
    assert summary["complete_document_count"] == 0
    assert len(cast("list[object]", summary["matches"])) == 1
    assert len(list((output / "details").glob("*.json"))) == 2
    assert len(list((output / "evidence").glob("*.json"))) == 2


def test_desktop_compare_has_no_total_manifest_document_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    documents = tuple(
        (_write_pdf(tmp_path / f"{index}.pdf"), f"bidder-{index}") for index in range(3)
    )
    manifest = tmp_path / "input-manifest.jsonl"
    _write_desktop_manifest(manifest, documents)
    monkeypatch.setattr(cli_module, "_MAX_INPUT_DOCUMENTS", 1)
    monkeypatch.setattr(cli_module, "create_runtime", _native_only_runtime)

    result = CliRunner().invoke(
        cli_module.app,
        ["desktop-compare", str(manifest), "--output", str(tmp_path / "result")],
    )

    assert result.exit_code == cli_module.EXIT_PARTIAL
    progress = [
        json.loads(line)
        for line in result.stdout.splitlines()
        if json.loads(line)["type"] == "progress"
    ]
    assert len(progress) == 3


@pytest.mark.parametrize(
    "contents",
    [
        "{}\n",
        '{"schema_version":"2.0","type":"manifest"}\nnot-json\n',
        (
            '{"schema_version":"2.0","type":"manifest"}\n'
            '{"type":"document","path":"relative.pdf",'
            '"source_path_sha256":"invalid","group_id":"bidder"}\n'
        ),
    ],
)
def test_desktop_compare_rejects_a_malformed_streaming_manifest(
    tmp_path: Path,
    contents: str,
) -> None:
    manifest = tmp_path / "input-manifest.jsonl"
    _ = manifest.write_text(contents, encoding="utf-8")

    result = CliRunner().invoke(
        cli_module.app,
        ["desktop-compare", str(manifest), "--output", str(tmp_path / "result")],
    )

    assert result.exit_code == cli_module.EXIT_ERROR
    assert "manifest" in result.stderr.casefold()
    assert "traceback" not in result.stderr.casefold()
    assert not (tmp_path / "result" / "summary.json").exists()


def test_desktop_compare_rejects_duplicate_and_unsupported_documents(
    tmp_path: Path,
) -> None:
    source = _write_pdf(tmp_path / "controlled.pdf")
    duplicate = tmp_path / "duplicate.jsonl"
    unsupported = tmp_path / "unsupported.txt"
    _ = unsupported.write_text("controlled", encoding="utf-8")
    _write_desktop_manifest(
        duplicate,
        ((source, "bidder-a"), (source, "bidder-b")),
    )
    unsupported_manifest = tmp_path / "unsupported.jsonl"
    _write_desktop_manifest(
        unsupported_manifest,
        ((unsupported, "bidder-a"),),
    )

    for manifest in (duplicate, unsupported_manifest):
        result = CliRunner().invoke(
            cli_module.app,
            [
                "desktop-compare",
                str(manifest),
                "--output",
                str(tmp_path / manifest.stem),
            ],
        )

        assert result.exit_code == cli_module.EXIT_ERROR
        assert "manifest" in result.stderr.casefold()
        assert "traceback" not in result.stderr.casefold()


def test_desktop_compare_rejects_a_symlinked_or_overlong_manifest(
    tmp_path: Path,
) -> None:
    source = _write_pdf(tmp_path / "controlled.pdf")
    target = tmp_path / "target.jsonl"
    _write_desktop_manifest(target, ((source, "bidder-a"),))
    link = tmp_path / "linked.jsonl"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symbolic links are unavailable in this test environment")
    overlong = tmp_path / "overlong.jsonl"
    _ = overlong.write_bytes(
        b'{"schema_version":"2.0","type":"manifest"}\n'
        + b"x" * (_DESKTOP_MANIFEST_LINE_BYTES + 1)
    )

    for manifest in (link, overlong):
        result = CliRunner().invoke(
            cli_module.app,
            [
                "desktop-compare",
                str(manifest),
                "--output",
                str(tmp_path / manifest.stem),
            ],
        )

        assert result.exit_code == cli_module.EXIT_ERROR
        assert "manifest" in result.stderr.casefold()
        assert "traceback" not in result.stderr.casefold()


def test_desktop_compare_rejects_manifest_metadata_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_pdf(tmp_path / "controlled.pdf")
    manifest = tmp_path / "input.jsonl"
    _write_desktop_manifest(manifest, ((source, "bidder-a"),))
    original_parser = cast(
        "Callable[[bytes, int], object]",
        vars(cli_module)["_parse_streaming_manifest_line"],
    )

    def parse_and_mutate(raw: bytes, line_number: int) -> object:
        value = original_parser(raw, line_number)
        if line_number == 2:
            file_stat = manifest.stat()
            os.utime(
                manifest,
                ns=(file_stat.st_atime_ns, file_stat.st_mtime_ns + 1_000_000_000),
            )
        return value

    monkeypatch.setattr(cli_module, "_parse_streaming_manifest_line", parse_and_mutate)

    result = CliRunner().invoke(
        cli_module.app,
        ["desktop-compare", str(manifest), "--output", str(tmp_path / "result")],
    )

    assert result.exit_code == cli_module.EXIT_ERROR
    assert "manifest" in result.stderr.casefold()
    assert "traceback" not in result.stderr.casefold()
    assert not (tmp_path / "result" / "summary.json").exists()


def test_export_reads_authoritative_json_and_writes_standalone_html(
    tmp_path: Path,
) -> None:
    source = tmp_path / "report.json"
    target = tmp_path / "report.html"
    _ = export_report(
        make_export_report(),
        ExportTarget(path=source, format=ExportFormat.JSON),
    )

    result = CliRunner().invoke(
        cli_module.app,
        [
            "export",
            str(source),
            "--format",
            "html",
            "--output",
            str(target),
        ],
    )

    assert result.exit_code == 0
    assert target.read_text(encoding="utf-8").startswith("<!doctype html>")
    assert "<script" not in target.read_text(encoding="utf-8").casefold()


def test_export_rejects_malformed_report_without_a_traceback(tmp_path: Path) -> None:
    source = tmp_path / "invalid.json"
    _ = source.write_text('{"documents": [}', encoding="utf-8")

    result = CliRunner().invoke(
        cli_module.app,
        [
            "export",
            str(source),
            "--format",
            "xlsx",
            "--output",
            str(tmp_path / "invalid.xlsx"),
        ],
    )

    assert result.exit_code == cli_module.EXIT_ERROR
    assert "invalid" in result.stderr.casefold()
    assert "traceback" not in result.stderr.casefold()


def test_export_rejects_a_symbolic_link_report(tmp_path: Path) -> None:
    source = tmp_path / "report.json"
    link = tmp_path / "linked-report.json"
    target = tmp_path / "report.xlsx"
    _ = export_report(
        make_export_report(),
        ExportTarget(path=source, format=ExportFormat.JSON),
    )
    link.symlink_to(source)

    result = CliRunner().invoke(
        cli_module.app,
        ["export", str(link), "--format", "xlsx", "--output", str(target)],
    )

    assert result.exit_code == cli_module.EXIT_ERROR
    assert not target.exists()
