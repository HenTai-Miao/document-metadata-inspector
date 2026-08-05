"""Build and self-test a current-platform zero-dependency executable."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol, cast

from document_metadata_inspector.resources import (
    platform_key,
    resolve_apache_worker,
    resolve_exiftool,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

type BuildMode = Literal["onefile", "onedir"]

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SPEC_FILE = _PROJECT_ROOT / "scripts/docmeta.spec"


class _Arguments(Protocol):
    mode: BuildMode


def _run(
    command: Sequence[str],
    cwd: Path,
    timeout: float,
    *,
    build_environment: dict[str, str] | None = None,
) -> None:
    result = subprocess.run(  # noqa: S603
        tuple(command),
        cwd=cwd,
        env={
            **os.environ,
            "PYTHONPATH": "",
            "PYTHONHOME": "",
            **(build_environment or {}),
        },
        check=False,
        timeout=timeout,
    )
    if result.returncode != 0:
        msg = "the executable build or offline self-test failed"
        raise RuntimeError(msg)


def _hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def build(mode: BuildMode) -> Path:
    """Build one PyInstaller executable after strict bundled-resource checks."""
    key = platform_key()
    _ = resolve_apache_worker(root=_PROJECT_ROOT, development=False)
    _ = resolve_exiftool(root=_PROJECT_ROOT, development=False)
    notices = _PROJECT_ROOT / "THIRD_PARTY_NOTICES.md"
    if not notices.is_file():
        msg = "THIRD_PARTY_NOTICES.md is required for release builds"
        raise RuntimeError(msg)

    dist = _PROJECT_ROOT / "dist" / key / mode
    work = _PROJECT_ROOT / "build/pyinstaller" / key / mode
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(dist),
        "--workpath",
        str(work),
        str(_SPEC_FILE),
    ]
    _run(
        command,
        _PROJECT_ROOT,
        timeout=900,
        build_environment={
            "DOCMETA_BUILD_MODE": mode,
            "DOCMETA_BUILD_PLATFORM_KEY": key,
            "DOCMETA_BUILD_PROJECT_ROOT": str(_PROJECT_ROOT),
        },
    )

    executable_name = "docmeta.exe" if os.name == "nt" else "docmeta"
    executable = (
        dist / executable_name
        if mode == "onefile"
        else dist / "docmeta" / executable_name
    )
    if not executable.is_file():
        msg = "PyInstaller did not create the expected executable"
        raise RuntimeError(msg)
    _run((str(executable), "verify"), executable.parent, timeout=180)
    checksum = executable.parent / "SHA256SUMS"
    _ = checksum.write_text(
        f"{_hash(executable)}  {executable.name}\n",
        encoding="utf-8",
        newline="\n",
    )
    return executable


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a current-platform offline docmeta executable."
    )
    _ = parser.add_argument(
        "--mode",
        choices=("onefile", "onedir"),
        default="onefile",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Build and report the verified executable path."""
    arguments = cast("_Arguments", cast("object", _parser().parse_args(argv)))
    executable = build(arguments.mode)
    print(f"Verified offline executable: {executable}")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
