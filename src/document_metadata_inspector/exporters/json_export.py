"""Deterministic authoritative JSON report writer."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from document_metadata_inspector.exporters.contracts import ExportableReport


def write_json_report(report: ExportableReport, path: Path) -> None:
    """Write UTF-8 JSON with stable object-key ordering and a final newline."""
    payload = report.model_dump(mode="json")
    text = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        separators=(",", ": "),
    )
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        _ = stream.write(text)
        _ = stream.write("\n")


__all__ = ("write_json_report",)
