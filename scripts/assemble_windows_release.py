"""Command-line facade for Windows x64 release assembly."""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

if __package__:
    from scripts.windows_release import assemble_windows_release
else:
    from windows_release import (  # pyright: ignore[reportImplicitRelativeImport]
        assemble_windows_release,
    )

if TYPE_CHECKING:
    from collections.abc import Sequence

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class _Arguments(Protocol):
    forge_output: Path
    cli_release_directory: Path
    output_directory: Path


def _require_windows_x64() -> None:
    if platform.system() != "Windows" or platform.machine().casefold() not in {
        "amd64",
        "x86_64",
    }:
        message = "Windows release assembly requires native Windows x64"
        raise RuntimeError(message)


def _git_commit() -> str:
    git = shutil.which("git")
    if git is None:
        message = "git is required to record the release commit"
        raise RuntimeError(message)
    result = subprocess.run(  # noqa: S603
        (git, "rev-parse", "HEAD"),
        cwd=_PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout.strip()


def main(argv: Sequence[str] | None = None) -> int:
    """Assemble the release from command-line arguments."""
    parser = argparse.ArgumentParser(description="Assemble the Windows x64 release")
    _ = parser.add_argument(
        "--forge-output",
        type=Path,
        default=_PROJECT_ROOT / "desktop/out/make",
    )
    _ = parser.add_argument(
        "--cli-release-directory",
        type=Path,
        default=_PROJECT_ROOT / "release",
    )
    _ = parser.add_argument(
        "--output-directory",
        type=Path,
        default=_PROJECT_ROOT / "release/windows-x64",
    )
    arguments = cast("_Arguments", cast("object", parser.parse_args(argv)))
    _require_windows_x64()
    output = assemble_windows_release(
        _PROJECT_ROOT,
        arguments.forge_output,
        arguments.cli_release_directory,
        arguments.output_directory,
        git_commit=_git_commit(),
        built_at_utc=datetime.now(UTC),
    )
    print(f"Windows x64 release is ready: {output}")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
