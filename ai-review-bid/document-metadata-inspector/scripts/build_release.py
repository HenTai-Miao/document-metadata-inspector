"""Orchestrate one native, self-contained offline application build."""

from __future__ import annotations

import argparse
import json
import os
import stat
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import TYPE_CHECKING, Literal, Protocol, cast

from document_metadata_inspector.resources import (
    ToolResourceError,
    platform_key,
    resolve_apache_worker,
    resolve_exiftool,
    tree_sha256,
)

if __package__:
    from scripts.bootstrap_jdk import ensure_jdk
    from scripts.bootstrap_tools import bootstrap as bootstrap_exiftool
    from scripts.build_apache_worker import build_worker
    from scripts.build_app import build as build_app
    from scripts.build_portable_exiftool import build as build_portable_exiftool
    from scripts.build_windows_exiftool import build as build_windows_exiftool
    from scripts.prepare_platform_resources import prepare
else:
    from bootstrap_jdk import ensure_jdk
    from bootstrap_tools import bootstrap as bootstrap_exiftool
    from build_apache_worker import build_worker
    from build_app import build as build_app
    from build_portable_exiftool import build as build_portable_exiftool
    from build_windows_exiftool import build as build_windows_exiftool
    from prepare_platform_resources import prepare

if TYPE_CHECKING:
    from collections.abc import Sequence

type BuildMode = Literal["onefile", "onedir"]

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_BUILD_CACHE = _PROJECT_ROOT / "tools/build-cache"


class _Arguments(Protocol):
    mode: BuildMode


def _exiftool_runtime(key: str) -> tuple[Path, tuple[str, ...]]:
    output = _BUILD_CACHE / "release-exiftool" / key
    command = (
        ("exiftool.exe",)
        if key.startswith("windows-")
        else ("perl/bin/perl", "exiftool-source/exiftool")
    )
    if _cached_runtime_is_valid(output, key):
        return output, command

    parent = output.parent
    parent.mkdir(parents=True, exist_ok=True)
    integrity = output.with_name(f"{output.name}.integrity.json")
    with TemporaryDirectory(prefix=f".{key}.", dir=parent) as temporary_text:
        temporary = Path(temporary_text)
        staging = temporary / key
        if key.startswith("windows-"):
            _ = build_windows_exiftool(staging, _BUILD_CACHE / "downloads")
        else:
            _ = build_portable_exiftool(
                staging,
                _BUILD_CACHE / "downloads",
                jobs=8,
            )
        record = temporary / integrity.name
        _ = record.write_text(
            json.dumps(
                {
                    "schema_version": "1",
                    "platform": key,
                    "provenance": _runtime_provenance(key),
                    "tree_sha256": tree_sha256(staging),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        previous_runtime = temporary / "previous-runtime"
        previous_integrity = temporary / "previous-integrity.json"
        if output.exists():
            _ = output.replace(previous_runtime)
        if integrity.exists():
            _ = integrity.replace(previous_integrity)
        try:
            _ = staging.replace(output)
            _ = record.replace(integrity)
        except BaseException:
            if output.exists():
                _ = output.replace(temporary / "failed-runtime")
            if integrity.exists():
                _ = integrity.replace(temporary / "failed-integrity.json")
            if previous_runtime.exists():
                _ = previous_runtime.replace(output)
            if previous_integrity.exists():
                _ = previous_integrity.replace(integrity)
            raise
    return output, command


def _runtime_provenance(key: str) -> str:
    digest = sha256()
    builder = (
        _PROJECT_ROOT / "scripts/build_windows_exiftool.py"
        if key.startswith("windows-")
        else _PROJECT_ROOT / "scripts/build_portable_exiftool.py"
    )
    for path in (
        _PROJECT_ROOT / "tools/manifest.json",
        Path(__file__).resolve(),
        builder,
    ):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    digest.update(key.encode("ascii"))
    return digest.hexdigest()


def _cached_runtime_is_valid(output: Path, key: str) -> bool:
    integrity = output.with_name(f"{output.name}.integrity.json")
    if output.is_symlink() or not output.is_dir() or not integrity.is_file():
        return False
    try:
        value = json.loads(integrity.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            return False
        return (
            value.get("schema_version") == "1"
            and value.get("platform") == key
            and value.get("provenance") == _runtime_provenance(key)
            and value.get("tree_sha256") == tree_sha256(output)
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ToolResourceError):
        return False


def _restore_manifest(path: Path, contents: bytes, mode: int) -> None:
    if path.is_file() and path.read_bytes() == contents:
        return
    with NamedTemporaryFile(
        prefix=".manifest.",
        suffix=".json.tmp",
        dir=path.parent,
        delete=False,
        mode="wb",
    ) as stream:
        temporary = Path(stream.name)
        _ = stream.write(contents)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        temporary.chmod(stat.S_IMODE(mode))
        _ = temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def build_release(mode: BuildMode) -> Path:
    """Detect build tools, assemble resources, freeze and verify one target."""
    _ = bootstrap_exiftool(check_only=False, allow_system_development=False)
    java_home = ensure_jdk(_BUILD_CACHE / "temurin")
    _ = build_worker(java_home)

    key = platform_key()
    packaged = _PROJECT_ROOT / "tools/packaged" / key
    replace_existing = packaged.exists()
    exiftool_runtime, command = _exiftool_runtime(key)
    manifest = _PROJECT_ROOT / "tools/manifest.json"
    source_manifest = manifest.read_bytes()
    manifest_mode = manifest.stat().st_mode
    try:
        _ = prepare(
            java_home,
            exiftool_runtime,
            command,
            replace_existing=replace_existing,
        )
        _ = resolve_apache_worker(root=_PROJECT_ROOT, development=False)
        _ = resolve_exiftool(root=_PROJECT_ROOT, development=False)
        return build_app(mode)
    finally:
        _restore_manifest(manifest, source_manifest, manifest_mode)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Detect or install build-only dependencies and create one verified "
            "offline application."
        )
    )
    _ = parser.add_argument(
        "--mode",
        choices=("onefile", "onedir"),
        default="onefile",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Build and print the verified native executable path."""
    arguments = cast("_Arguments", cast("object", _parser().parse_args(argv)))
    executable = build_release(arguments.mode)
    print(f"Native offline release is ready: {executable}")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
