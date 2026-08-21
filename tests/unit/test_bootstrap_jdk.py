"""Security regressions for project-local Temurin JDK bootstrap."""

from __future__ import annotations

from typing import TYPE_CHECKING
from zipfile import ZipFile

import pytest
from scripts.bootstrap_jdk import _extract_zip  # pyright: ignore[reportPrivateUsage]

if TYPE_CHECKING:
    from pathlib import Path


def test_extracts_regular_jdk_zip_members(tmp_path: Path) -> None:
    archive = tmp_path / "jdk.zip"
    with ZipFile(archive, "w") as package:
        package.writestr("jdk-21/bin/java.exe", b"controlled")

    destination = tmp_path / "output"
    _extract_zip(archive, destination)

    assert (destination / "jdk-21/bin/java.exe").read_bytes() == b"controlled"


def test_rejects_jdk_zip_path_traversal_before_extraction(tmp_path: Path) -> None:
    archive = tmp_path / "jdk.zip"
    with ZipFile(archive, "w") as package:
        package.writestr("jdk-21/bin/java.exe", b"controlled")
        package.writestr("../outside.txt", b"unsafe")

    destination = tmp_path / "output"
    with pytest.raises(RuntimeError, match="unsafe"):
        _extract_zip(archive, destination)

    assert not destination.exists()
    assert not (tmp_path / "outside.txt").exists()
