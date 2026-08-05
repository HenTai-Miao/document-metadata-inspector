"""Command-line entry point for the offline metadata core."""

from __future__ import annotations

import getpass
import json
import os
import stat
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, cast

import typer
from pydantic import ValidationError

from document_metadata_inspector.comparison import (
    ComparisonRequest,
    compare_documents,
)
from document_metadata_inspector.exporters import (
    ExportError,
    ExportFormat,
    ExportTarget,
    export_report,
)
from document_metadata_inspector.formats import SUPPORTED_SUFFIXES
from document_metadata_inspector.models import (
    ComparisonReport,
    DocumentStatus,
    ScanReport,
)
from document_metadata_inspector.runtime import create_runtime
from document_metadata_inspector.scanner import ScanRequest
from document_metadata_inspector.verification import verify_runtime

if TYPE_CHECKING:
    from collections.abc import Callable

    from document_metadata_inspector.exporters import ExportableReport

EXIT_OK = 0
EXIT_ERROR = 2
EXIT_PARTIAL = 3
EXIT_VERIFY_FAILED = 4
_MAX_REPORT_BYTES = 512 * 1024 * 1024
_MAX_INPUT_MANIFEST_BYTES = 16 * 1024 * 1024
_MAX_INPUT_DOCUMENTS = 50_000
_MAX_INPUT_PATH_CHARS = 32_768
_MAX_GROUP_ID_CHARS = 256
_SHA256_HEX_CHARS = 64

app = typer.Typer(
    name="docmeta",
    help="Inspect and compare PDF, Word and Excel metadata offline.",
    no_args_is_help=True,
)


def _password_provider(*, enabled: bool) -> Callable[[str], str | None] | None:
    if not enabled:
        return None

    def prompt(source_name: str) -> str | None:
        value = getpass.getpass(f"Password for {Path(source_name).name}: ")
        return value or None

    return prompt


def _with_runtime_warnings(
    report: ScanReport,
    warnings: tuple[str, ...],
) -> ScanReport:
    combined = tuple(dict.fromkeys((*report.warnings, *warnings)))
    return report.model_copy(update={"warnings": combined})


def _all_complete(report: ExportableReport) -> bool:
    return bool(report.documents) and all(
        document.status is DocumentStatus.COMPLETE for document in report.documents
    )


def _warning_count(report: ExportableReport) -> int:
    return (
        len(report.warnings)
        + sum(len(document.warnings) for document in report.documents)
        + sum(
            len(run.warnings)
            for document in report.documents
            for run in document.parser_runs
        )
        + sum(
            len(child.warnings)
            for document in report.documents
            for child in document.embedded_documents
        )
    )


def _write_or_print_report(
    report: ExportableReport,
    output: Path | None,
    protected_paths: tuple[Path, ...],
) -> None:
    if output is None:
        typer.echo(report.model_dump_json(indent=2))
        return
    _ = export_report(
        report,
        ExportTarget(
            path=output,
            format=ExportFormat.JSON,
            protected_paths=protected_paths,
        ),
    )
    summary = {
        "complete": _all_complete(report),
        "document_count": len(report.documents),
        "output": str(output),
        "warning_count": _warning_count(report),
    }
    typer.echo(
        json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


def _exit_for_report(report: ExportableReport) -> None:
    if not _all_complete(report):
        raise typer.Exit(code=EXIT_PARTIAL)


def _scan_inputs(
    paths: list[Path],
    *,
    recursive: bool,
    max_concurrency: int | None,
    prompt_password: bool,
) -> ScanReport:
    runtime = create_runtime()
    report = runtime.scanner.scan(
        ScanRequest(
            paths=tuple(paths),
            recursive=recursive,
            max_concurrency=max_concurrency,
        ),
        password_provider=_password_provider(enabled=prompt_password),
    )
    return _with_runtime_warnings(report, runtime.warnings)


def _source_path_id(path: Path) -> str:
    resolved = str(path.resolve(strict=False)).encode("utf-8", errors="surrogatepass")
    return sha256(resolved).hexdigest()


@dataclass(frozen=True, slots=True)
class _ManifestInputs:
    paths: tuple[Path, ...]
    document_groups: tuple[tuple[str, str], ...]


def _read_bounded_regular_bytes(
    path: Path,
    *,
    max_bytes: int,
    label: str,
) -> bytes:
    initial_path_stat = path.lstat()
    if not stat.S_ISREG(initial_path_stat.st_mode):
        msg = f"{label} must be a regular file and cannot be a symbolic link"
        raise ValueError(msg)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as stream:
        initial_stream_stat = os.fstat(stream.fileno())
        path_identity = (initial_path_stat.st_dev, initial_path_stat.st_ino)
        stream_identity = (initial_stream_stat.st_dev, initial_stream_stat.st_ino)
        if (
            not stat.S_ISREG(initial_stream_stat.st_mode)
            or path_identity != stream_identity
        ):
            msg = f"{label} path changed while it was being opened"
            raise ValueError(msg)
        if initial_stream_stat.st_size > max_bytes:
            msg = f"{label} exceeds the safe input size limit"
            raise ValueError(msg)
        raw = stream.read(max_bytes + 1)
        final_stream_stat = os.fstat(stream.fileno())
    if len(raw) > max_bytes:
        msg = f"{label} exceeds the safe input size limit"
        raise ValueError(msg)
    initial_identity = (
        initial_stream_stat.st_dev,
        initial_stream_stat.st_ino,
        initial_stream_stat.st_size,
        initial_stream_stat.st_mtime_ns,
        initial_stream_stat.st_ctime_ns,
    )
    final_identity = (
        final_stream_stat.st_dev,
        final_stream_stat.st_ino,
        final_stream_stat.st_size,
        final_stream_stat.st_mtime_ns,
        final_stream_stat.st_ctime_ns,
    )
    if initial_identity != final_identity or len(raw) != initial_stream_stat.st_size:
        msg = f"{label} changed while it was being read"
        raise ValueError(msg)
    return raw


def _parse_manifest_document(
    item: object,
    seen_ids: set[str],
) -> tuple[Path, tuple[str, str]]:
    if not isinstance(item, dict):
        msg = "input manifest document entry is invalid"
        raise TypeError(msg)
    entry = cast("dict[str, object]", item)
    if set(entry) != {
        "path",
        "source_path_sha256",
        "group_id",
    }:
        msg = "input manifest document entry is invalid"
        raise ValueError(msg)
    path_text = entry["path"]
    source_path_sha256 = entry["source_path_sha256"]
    group_id = entry["group_id"]
    if (
        not isinstance(path_text, str)
        or not 1 <= len(path_text) <= _MAX_INPUT_PATH_CHARS
        or "\0" in path_text
    ):
        msg = "input manifest document path is invalid"
        raise ValueError(msg)
    candidate = Path(path_text)
    if (
        not candidate.is_absolute()
        or candidate.suffix.casefold() not in SUPPORTED_SUFFIXES
    ):
        msg = "input manifest document path is unsupported"
        raise ValueError(msg)
    if (
        not isinstance(source_path_sha256, str)
        or len(source_path_sha256) != _SHA256_HEX_CHARS
        or any(character not in "0123456789abcdef" for character in source_path_sha256)
        or source_path_sha256 != _source_path_id(candidate)
        or source_path_sha256 in seen_ids
    ):
        msg = "input manifest document identity is invalid"
        raise ValueError(msg)
    if (
        not isinstance(group_id, str)
        or not 1 <= len(group_id) <= _MAX_GROUP_ID_CHARS
        or "\0" in group_id
    ):
        msg = "input manifest group is invalid"
        raise ValueError(msg)
    seen_ids.add(source_path_sha256)
    return candidate, (source_path_sha256, group_id)


def _load_input_manifest(path: Path) -> _ManifestInputs:
    try:
        raw = _read_bounded_regular_bytes(
            path,
            max_bytes=_MAX_INPUT_MANIFEST_BYTES,
            label="input manifest",
        )
        value = cast("object", json.loads(raw))
        if not isinstance(value, dict):
            msg = "input manifest root is invalid"
            raise TypeError(msg)
        payload = cast("dict[str, object]", value)
        if set(payload) != {"schema_version", "documents"}:
            msg = "input manifest root is invalid"
            raise ValueError(msg)
        if payload["schema_version"] != "1.0" or not isinstance(
            payload["documents"], list
        ):
            msg = "input manifest schema is invalid"
            raise ValueError(msg)
        documents = cast("list[object]", payload["documents"])
        if not 1 <= len(documents) <= _MAX_INPUT_DOCUMENTS:
            msg = "input manifest document count is invalid"
            raise ValueError(msg)

        paths: list[Path] = []
        document_groups: list[tuple[str, str]] = []
        seen_ids: set[str] = set()
        for item in documents:
            candidate, document_group = _parse_manifest_document(item, seen_ids)
            paths.append(candidate)
            document_groups.append(document_group)
        return _ManifestInputs(
            paths=tuple(paths),
            document_groups=tuple(sorted(document_groups)),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        msg = "the input manifest is missing or invalid"
        raise ValueError(msg) from error


def _manifest_path_for_compare(
    paths: list[Path],
    *,
    recursive: bool,
    group_by_top_level_dir: bool,
) -> Path:
    if len(paths) != 1 or recursive or group_by_top_level_dir:
        msg = (
            "input manifest mode requires exactly one manifest path and "
            "cannot be combined with recursive grouping"
        )
        raise ValueError(msg)
    return paths[0]


def _top_level_document_groups(
    paths: list[Path],
    *,
    recursive: bool,
) -> tuple[tuple[str, str], ...]:
    groups: dict[str, str] = {}
    for input_index, requested in enumerate(paths):
        if requested.is_file():
            if requested.suffix.casefold() in SUPPORTED_SUFFIXES:
                groups[_source_path_id(requested)] = (
                    f"parent:{requested.parent.resolve(strict=False)}"
                )
            continue
        if not requested.is_dir():
            continue
        iterator = requested.rglob("*") if recursive else requested.iterdir()
        for candidate in iterator:
            if not candidate.is_file():
                continue
            if candidate.suffix.casefold() not in SUPPORTED_SUFFIXES:
                continue
            try:
                relative = candidate.relative_to(requested)
            except ValueError:
                continue
            top_level = relative.parts[0] if len(relative.parts) > 1 else "."
            groups[_source_path_id(candidate)] = f"root:{input_index}:{top_level}"
    return tuple(sorted(groups.items()))


@app.command()
def scan(
    paths: Annotated[list[Path], typer.Argument(metavar="FILE...")],
    json_output: Annotated[
        Path | None,
        typer.Option(
            "--json",
            help="Write the authoritative JSON report to this path.",
        ),
    ] = None,
    recursive: Annotated[
        bool,
        typer.Option(
            "--recursive",
            "-r",
            help="Recursively inspect supported files below input directories.",
        ),
    ] = False,
    max_concurrency: Annotated[
        int | None,
        typer.Option(
            min=1,
            max=32,
            help="Maximum number of documents inspected concurrently.",
        ),
    ] = None,
    prompt_password: Annotated[
        bool,
        typer.Option(
            "--prompt-password",
            help="Prompt securely in the terminal when a parser requests a password.",
        ),
    ] = False,
) -> None:
    """Scan documents and preserve every parser's sourced evidence."""
    try:
        report = _scan_inputs(
            paths,
            recursive=recursive,
            max_concurrency=max_concurrency,
            prompt_password=prompt_password,
        )
        _write_or_print_report(report, json_output, tuple(paths))
    except (ExportError, OSError, ValidationError, ValueError) as error:
        typer.echo(f"scan failed: {error}", err=True)
        raise typer.Exit(code=EXIT_ERROR) from None
    _exit_for_report(report)


@app.command()
def compare(  # noqa: PLR0913, PLR0917 - Typer exposes each CLI option as a parameter.
    paths: Annotated[list[Path], typer.Argument(metavar="FILE...")],
    json_output: Annotated[
        Path | None,
        typer.Option(
            "--json",
            help="Write the authoritative comparison JSON to this path.",
        ),
    ] = None,
    recursive: Annotated[
        bool,
        typer.Option("--recursive", "-r"),
    ] = False,
    max_concurrency: Annotated[
        int | None,
        typer.Option(min=1, max=32),
    ] = None,
    prompt_password: Annotated[
        bool,
        typer.Option("--prompt-password"),
    ] = False,
    group_by_top_level_dir: Annotated[
        bool,
        typer.Option(
            "--group-by-top-level-dir",
            help=(
                "Treat each immediate child directory of an input directory "
                "as one comparison group."
            ),
        ),
    ] = False,
    input_manifest: Annotated[
        bool,
        typer.Option(
            "--input-manifest",
            help=(
                "Treat the single FILE argument as a private exact-input manifest "
                "containing document paths and comparison groups."
            ),
        ),
    ] = False,
) -> None:
    """Compare exact normalized identity traces across documents."""
    try:
        if input_manifest:
            manifest_path = _manifest_path_for_compare(
                paths,
                recursive=recursive,
                group_by_top_level_dir=group_by_top_level_dir,
            )
            manifest = _load_input_manifest(manifest_path)
            scan_paths = list(manifest.paths)
            document_groups = manifest.document_groups
            protected_paths = (*manifest.paths, manifest_path)
        else:
            scan_paths = paths
            document_groups = (
                _top_level_document_groups(paths, recursive=recursive)
                if group_by_top_level_dir
                else ()
            )
            protected_paths = tuple(paths)
        scan_report = _scan_inputs(
            scan_paths,
            recursive=recursive if not input_manifest else False,
            max_concurrency=max_concurrency,
            prompt_password=prompt_password,
        )
        report = compare_documents(
            ComparisonRequest(
                documents=scan_report.documents,
                document_groups=document_groups,
            )
        )
        report = report.model_copy(update={"warnings": scan_report.warnings})
        _write_or_print_report(report, json_output, protected_paths)
    except (ExportError, OSError, TypeError, ValidationError, ValueError) as error:
        typer.echo(f"comparison failed: {error}", err=True)
        raise typer.Exit(code=EXIT_ERROR) from None
    _exit_for_report(report)


def _load_report(path: Path) -> ExportableReport:
    try:
        raw = _read_bounded_regular_bytes(
            path,
            max_bytes=_MAX_REPORT_BYTES,
            label="report",
        )
        value = cast("object", json.loads(raw))
        if not isinstance(value, dict):
            msg = "report root must be a JSON object"
            raise TypeError(msg)
        payload = cast("dict[str, object]", value)
        if "matches" in payload:
            return ComparisonReport.model_validate(payload)
        return ScanReport.model_validate(payload)
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValidationError,
    ) as error:
        msg = "the input report is missing or invalid"
        raise ValueError(msg) from error


@app.command(name="export")
def export_report_command(
    report_path: Annotated[Path, typer.Argument(metavar="REPORT.json")],
    output_format: Annotated[ExportFormat, typer.Option("--format")],
    output: Annotated[Path, typer.Option("--output")],
) -> None:
    """Export an authoritative JSON report to JSON, XLSX or standalone HTML."""
    try:
        report = _load_report(report_path)
        target = export_report(
            report,
            ExportTarget(
                path=output,
                format=output_format,
                protected_paths=(report_path,),
            ),
        )
    except (ExportError, OSError, TypeError, ValueError) as error:
        typer.echo(f"export failed: {error}", err=True)
        raise typer.Exit(code=EXIT_ERROR) from None
    typer.echo(
        json.dumps(
            {"format": output_format.value, "output": str(target)},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )


@app.command()
def verify() -> None:
    """Execute all parser engines on controlled samples without network access."""
    report = verify_runtime(create_runtime())
    typer.echo(report.model_dump_json(indent=2))
    if not report.passed:
        raise typer.Exit(code=EXIT_VERIFY_FAILED)


def main() -> None:
    """Run the Typer application."""
    app()


if __name__ == "__main__":
    main()
