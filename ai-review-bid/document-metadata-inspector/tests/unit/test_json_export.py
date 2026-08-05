from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

import pytest

from document_metadata_inspector.exporters import (
    ExportFormat,
    ExportTarget,
    UnsafeExportTargetError,
    export_report,
    write_atomic_output,
)
from tests.export_factories import make_export_report

if TYPE_CHECKING:
    from pathlib import Path


def test_json_export_is_deterministic_utf8_and_authoritative(tmp_path: Path) -> None:
    report = make_export_report()
    target = tmp_path / "report.json"

    result = export_report(
        report,
        ExportTarget(path=target, format=ExportFormat.JSON),
    )

    assert result == target
    payload = cast(
        "object",
        json.loads(target.read_text(encoding="utf-8")),
    )
    assert payload == report.model_dump(mode="json")
    first = target.read_bytes()
    _ = export_report(report, ExportTarget(path=target, format=ExportFormat.JSON))
    assert target.read_bytes() == first


def test_export_rejects_a_target_equal_to_any_protected_input(tmp_path: Path) -> None:
    report = make_export_report()
    source = tmp_path / "input.json"
    _ = source.write_text("original", encoding="utf-8")

    with pytest.raises(UnsafeExportTargetError):
        _ = export_report(
            report,
            ExportTarget(
                path=source,
                format=ExportFormat.JSON,
                protected_paths=(source,),
            ),
        )

    assert source.read_text(encoding="utf-8") == "original"


def test_atomic_writer_failure_leaves_no_partial_or_temp_file(tmp_path: Path) -> None:
    target = tmp_path / "report.json"
    _ = target.write_text("previous", encoding="utf-8")

    def fail_after_partial_write(temporary: Path) -> None:
        _ = temporary.write_text("partial", encoding="utf-8")
        message = "controlled failure"
        raise RuntimeError(message)

    with pytest.raises(RuntimeError, match="controlled failure"):
        _ = write_atomic_output(target, fail_after_partial_write)

    assert target.read_text(encoding="utf-8") == "previous"
    assert list(tmp_path.glob(".report.json.*.tmp")) == []
