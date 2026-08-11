"""Atomic JSON, XLSX and standalone HTML report exports."""

from __future__ import annotations

import os
from enum import StrEnum
from functools import partial
from pathlib import Path
from tempfile import mkstemp
from typing import TYPE_CHECKING

from pydantic import Field

from document_metadata_inspector.exporters.contracts import ExportableReport
from document_metadata_inspector.models import FrozenModel

if TYPE_CHECKING:
    from collections.abc import Callable


class ExportFormat(StrEnum):
    """Identify one supported offline report representation."""

    JSON = "json"
    XLSX = "xlsx"
    HTML = "html"


class ExportError(RuntimeError):
    """Report a sanitized export failure."""


class UnsafeExportTargetError(ExportError):
    """Reject export destinations that would overwrite protected inputs."""


class ExportTarget(FrozenModel):
    """Describe one output and every input path it must not replace."""

    path: Path
    format: ExportFormat
    protected_paths: tuple[Path, ...] = Field(default_factory=tuple)


def write_atomic_output(target: Path, writer: Callable[[Path], None]) -> Path:
    """Write a sibling temporary file and replace the target only after success."""
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_text = mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_text)
    temporary.chmod(0o600)
    try:
        writer(temporary)
        with temporary.open("r+b") as stream:
            os.fsync(stream.fileno())
        _ = temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def _validate_target(target: ExportTarget) -> None:
    destination = target.path.resolve(strict=False)
    for protected in target.protected_paths:
        if destination == protected.resolve(strict=False):
            msg = "The export target must not overwrite an input file."
            raise UnsafeExportTargetError(msg)


def export_report(report: ExportableReport, target: ExportTarget) -> Path:
    """Export one immutable report through the selected atomic writer."""
    _validate_target(target)
    if target.format is ExportFormat.JSON:
        from document_metadata_inspector.exporters.json_export import (  # noqa: PLC0415
            write_json_report,
        )

        writer = partial(write_json_report, report)
    elif target.format is ExportFormat.XLSX:
        from document_metadata_inspector.exporters.xlsx_export import (  # noqa: PLC0415
            write_xlsx_report,
        )

        writer = partial(write_xlsx_report, report)
    else:
        from document_metadata_inspector.exporters.html_export import (  # noqa: PLC0415
            write_html_report,
        )

        writer = partial(write_html_report, report)
    try:
        return write_atomic_output(target.path, writer)
    except (OSError, RuntimeError, ValueError) as error:
        msg = "The report could not be exported safely."
        raise ExportError(msg) from error


__all__ = (
    "ExportError",
    "ExportFormat",
    "ExportTarget",
    "ExportableReport",
    "UnsafeExportTargetError",
    "export_report",
    "write_atomic_output",
)
