"""Regression tests for the portable ExifTool runtime builder."""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

import pytest
from scripts.build_portable_exiftool import (
    _copy_exiftool_runtime,  # pyright: ignore[reportPrivateUsage]
    _install_archive_zip,  # pyright: ignore[reportPrivateUsage]
    _run,  # pyright: ignore[reportPrivateUsage]
)

if TYPE_CHECKING:
    from pathlib import Path


def test_failed_build_command_reports_bounded_output_tail(tmp_path: Path) -> None:
    """A failed toolchain command should retain its useful diagnostic tail."""
    command = (
        sys.executable,
        "-c",
        (
            "import sys; print('out-marker'); "
            "print('err-marker', file=sys.stderr); sys.exit(7)"
        ),
    )

    with pytest.raises(RuntimeError) as caught:
        _ = _run(command, tmp_path, dict(os.environ), timeout=5, capture=True)

    message = str(caught.value)
    assert "out-marker" in message
    assert "err-marker" in message
    assert "exit 7" in message


def test_release_runtime_excludes_upstream_tests_and_examples(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "lib/Image").mkdir(parents=True)
    (source / "t/images").mkdir(parents=True)
    _ = (source / "exiftool").write_text("#!/usr/bin/env perl", encoding="utf-8")
    _ = (source / "lib/Image/ExifTool.pm").write_text("controlled", encoding="utf-8")
    _ = (source / "t/images/EXE.macho").write_bytes(b"unsafe test fixture")
    destination = tmp_path / "runtime"

    _copy_exiftool_runtime(source, destination)

    assert (destination / "exiftool").is_file()
    assert (destination / "lib/Image/ExifTool.pm").is_file()
    assert not (destination / "t").exists()


def test_installs_archive_zip_into_relocatable_site_library(tmp_path: Path) -> None:
    source = tmp_path / "Archive-Zip-1.68"
    module = source / "lib/Archive/Zip.pm"
    module.parent.mkdir(parents=True)
    _ = module.write_text("package Archive::Zip;", encoding="utf-8")
    install = tmp_path / "perl"

    _install_archive_zip(source, install, "5.44.0")

    installed = install / "lib/site_perl/5.44.0/Archive/Zip.pm"
    assert installed.read_text(encoding="utf-8") == "package Archive::Zip;"
