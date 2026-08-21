"""Smoke tests for the new offline command-line entry point."""

from typer.testing import CliRunner

from document_metadata_inspector.cli import app


def test_docmeta_help_lists_the_core_workflows() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "scan" in result.stdout
    assert "compare" in result.stdout
    assert "export" in result.stdout
    assert "verify" in result.stdout
