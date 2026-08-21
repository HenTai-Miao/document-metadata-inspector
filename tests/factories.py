"""Controlled XLSX package factories for tests."""

import warnings
from collections.abc import Mapping
from pathlib import Path
from tempfile import NamedTemporaryFile
from zipfile import ZipFile

from openpyxl import Workbook

type ZipPayload = bytes | str


def make_workbook(path: Path) -> Path:
    """Create a minimal genuine XLSX workbook at ``path``."""
    workbook = Workbook()
    try:
        workbook.save(path)
    finally:
        workbook.close()
    return path


def rewrite_package(
    path: Path,
    replacements: Mapping[str, ZipPayload | None],
    additions: Mapping[str, ZipPayload],
) -> None:
    """Rewrite a fixture through a closed sibling ZIP and atomically replace it."""
    with NamedTemporaryFile(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, delete=False
    ) as temporary_file:
        temporary_path = Path(temporary_file.name)
    try:
        with ZipFile(path, "r") as source, ZipFile(temporary_path, "w") as target:
            for info in source.infolist():
                if info.filename in replacements:
                    replacement = replacements[info.filename]
                    if replacement is not None:
                        target.writestr(info, replacement)
                else:
                    target.writestr(info, source.read(info))
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="Duplicate name:",
                    category=UserWarning,
                    module="zipfile",
                )
                for name, payload in additions.items():
                    target.writestr(name, payload)
        _ = temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)
