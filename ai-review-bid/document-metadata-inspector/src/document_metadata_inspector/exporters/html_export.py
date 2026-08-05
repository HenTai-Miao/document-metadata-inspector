"""Escaped, script-free standalone HTML report projection."""

from __future__ import annotations

import json
from html import escape
from typing import TYPE_CHECKING

from document_metadata_inspector.models import ComparisonReport

if TYPE_CHECKING:
    from pathlib import Path

    from document_metadata_inspector.exporters.contracts import ExportableReport
    from document_metadata_inspector.models import JsonValue


def _json(value: JsonValue) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _cell(value: object) -> str:
    return f"<td>{escape(str(value), quote=True)}</td>"


def _table(
    title: str,
    headers: tuple[str, ...],
    rows: list[tuple[object, ...]],
) -> str:
    header = "".join(f"<th>{escape(item)}</th>" for item in headers)
    body = "".join(
        "<tr>" + "".join(_cell(value) for value in row) + "</tr>" for row in rows
    )
    return (
        f"<section><h2>{escape(title)}</h2>"
        f"<p>Rows: {len(rows)}</p>"
        f"<div class=table-wrap><table><thead><tr>{header}</tr></thead>"
        f"<tbody>{body}</tbody></table></div></section>"
    )


def write_html_report(report: ExportableReport, path: Path) -> None:
    """Write a local-only HTML document with all report values escaped."""
    document_count = len(report.documents)
    observation_count = sum(
        len(item.observations)
        + sum(len(child.observations) for child in item.embedded_documents)
        for item in report.documents
    )
    embedded_count = sum(len(item.embedded_documents) for item in report.documents)
    parser_count = sum(len(item.parser_runs) for item in report.documents)
    match_count = len(report.matches) if isinstance(report, ComparisonReport) else 0

    file_rows: list[tuple[object, ...]] = []
    observation_rows: list[tuple[object, ...]] = []
    parser_rows: list[tuple[object, ...]] = []
    warning_rows: list[tuple[object, ...]] = [
        ("report", "", "", warning) for warning in report.warnings
    ]
    match_rows: list[tuple[object, ...]] = []
    embedded_rows: list[tuple[object, ...]] = []
    embedded_observation_rows: list[tuple[object, ...]] = []
    for document in report.documents:
        file_rows.append(
            (
                document.display_name,
                document.sha256,
                document.size_bytes,
                document.identity.declared_format.value,
                document.status.value,
                document.encrypted,
                len(document.observations)
                + sum(len(child.observations) for child in document.embedded_documents),
            )
        )
        observation_rows.extend(
            (
                document.display_name,
                item.canonical_name,
                item.raw_name,
                _json(item.raw_value),
                _json(item.normalized_value),
                item.source_kind,
                item.location,
                item.parser_name,
                item.status.value,
            )
            for item in document.observations
        )
        for parser_run in document.parser_runs:
            parser_rows.append(
                (
                    document.display_name,
                    parser_run.parser_name,
                    parser_run.parser_version,
                    parser_run.status.value,
                    len(parser_run.observations),
                    parser_run.duration_ms or "",
                    parser_run.error_code or "",
                )
            )
            warning_rows.extend(
                (
                    "parser",
                    document.display_name,
                    parser_run.parser_name,
                    warning,
                )
                for warning in parser_run.warnings
            )
            if parser_run.error_code:
                warning_rows.append(
                    (
                        "parser_error",
                        document.display_name,
                        parser_run.parser_name,
                        parser_run.error_code,
                    )
                )
        warning_rows.extend(
            ("document", document.display_name, "", warning)
            for warning in document.warnings
        )
        for child in document.embedded_documents:
            embedded_rows.append(
                (
                    document.display_name,
                    child.resource_id,
                    child.parent_id,
                    child.depth,
                    child.path,
                    child.content_type,
                    child.size_bytes,
                    child.sha256,
                    " | ".join(child.parser_names),
                    len(child.observations),
                )
            )
            embedded_observation_rows.extend(
                (
                    document.display_name,
                    child.resource_id,
                    child.path,
                    item.canonical_name,
                    item.raw_name,
                    _json(item.raw_value),
                    _json(item.normalized_value),
                    item.source_kind,
                    item.location,
                    item.parser_name,
                    item.status.value,
                )
                for item in child.observations
            )
            warning_rows.extend(
                ("embedded", document.display_name, "", warning)
                for warning in child.warnings
            )

    if isinstance(report, ComparisonReport):
        match_rows.extend(
            (
                item.trace_kind.value,
                item.canonical_name,
                _json(item.normalized_value),
                " | ".join(item.document_names),
                " | ".join(item.document_ids),
                " | ".join(item.field_names),
                item.evidence_count,
                _json(item.raw_values),
            )
            for item in report.matches
        )

    sections = (
        _table(
            "Files",
            (
                "Name",
                "SHA-256",
                "Bytes",
                "Format",
                "Status",
                "Encrypted",
                "Observations",
            ),
            file_rows,
        )
        + _table(
            "Raw observations",
            (
                "Document",
                "Canonical name",
                "Raw name",
                "Raw value",
                "Normalized value",
                "Source kind",
                "Location",
                "Parser",
                "Status",
            ),
            observation_rows,
        )
        + _table(
            "Embedded documents",
            (
                "Document",
                "Resource ID",
                "Parent ID",
                "Depth",
                "Path",
                "Content type",
                "Bytes",
                "SHA-256",
                "Parsers",
                "Observations",
            ),
            embedded_rows,
        )
        + _table(
            "Embedded metadata",
            (
                "Document",
                "Resource ID",
                "Path",
                "Canonical name",
                "Raw name",
                "Raw value",
                "Normalized value",
                "Source kind",
                "Location",
                "Parser",
                "Status",
            ),
            embedded_observation_rows,
        )
        + _table(
            "Identity matches",
            (
                "Trace kind",
                "Name",
                "Normalized value",
                "Documents",
                "Document IDs",
                "Fields",
                "Evidence",
                "Raw values",
            ),
            match_rows,
        )
        + _table(
            "Parser coverage",
            (
                "Document",
                "Parser",
                "Version",
                "Status",
                "Observations",
                "Duration ms",
                "Error",
            ),
            parser_rows,
        )
        + _table(
            "Warnings and errors",
            ("Scope", "Document", "Parser", "Value"),
            warning_rows,
        )
    )
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy"
 content="default-src 'none'; style-src 'unsafe-inline'">
<title>Document metadata inspection report</title>
<style>
:root {{ color-scheme: light; font-family: ui-sans-serif, system-ui, sans-serif; }}
body {{ margin: 2rem; color: #17202a; background: #f8fafc; }}
h1, h2 {{ color: #17324d; }}
.summary {{ display: flex; gap: 1rem; flex-wrap: wrap; }}
.metric {{
  padding: .7rem 1rem;
  border: 1px solid #ccd6e0;
  border-radius: .5rem;
  background: white;
}}
section {{ margin-top: 2rem; }}
.table-wrap {{ overflow-x: auto; border: 1px solid #ccd6e0; background: white; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{
  padding: .55rem .7rem;
  border-bottom: 1px solid #e3e8ee;
  text-align: left;
  vertical-align: top;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}}
th {{ background: #edf3f8; position: sticky; top: 0; }}
</style>
</head>
<body>
<h1>Document metadata inspection report</h1>
<div class="summary">
<div class="metric">Documents: {document_count}</div>
<div class="metric">Observations: {observation_count}</div>
<div class="metric">Embedded documents: {embedded_count}</div>
<div class="metric">Parser runs: {parser_count}</div>
<div class="metric">Identity matches: {match_count}</div>
</div>
{sections}
</body>
</html>
"""
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        _ = stream.write(html)


__all__ = ("write_html_report",)
