from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

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
    from pathlib import Path

    import pytest


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
