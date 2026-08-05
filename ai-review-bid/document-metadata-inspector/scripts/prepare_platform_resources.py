"""Create one hash-locked Java/ExifTool runtime tree for the current platform."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import TYPE_CHECKING, Protocol, cast

if TYPE_CHECKING:
    from collections.abc import Sequence

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_MANIFEST_PATH = _PROJECT_ROOT / "tools/manifest.json"
_PACKAGED_ROOT = _PROJECT_ROOT / "tools/packaged"
_WORKER_JAR = _PROJECT_ROOT / "java-worker/target/document-metadata-apache-worker.jar"
_HASH_CHUNK_BYTES = 1024 * 1024
_JAVA_MODULES = (
    "java.base",
    "java.compiler",
    "java.desktop",
    "java.naming",
    "java.net.http",
    "java.scripting",
    "java.security.jgss",
    "java.sql",
    "java.xml.crypto",
    "jdk.crypto.ec",
)


class _Arguments(Protocol):
    java_home: Path
    exiftool_runtime: Path
    exiftool_command: list[str]


def _platform_key() -> str:
    from document_metadata_inspector.resources import platform_key  # noqa: PLC0415

    return platform_key()


def _file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _files(root: Path, project_prefix: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            msg = "packaged runtimes must not contain symbolic links"
            raise RuntimeError(msg)
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        result[(project_prefix / relative).as_posix()] = _file_hash(path)
    if not result:
        msg = "a packaged runtime tree is empty"
        raise RuntimeError(msg)
    return result


def _require_source_tree(root: Path) -> None:
    if root.is_symlink() or not root.is_dir():
        msg = "the requested runtime source directory is invalid"
        raise RuntimeError(msg)
    for path in root.rglob("*"):
        if path.is_symlink():
            msg = "runtime source directories must not contain symbolic links"
            raise RuntimeError(msg)


def _copy_tree(source: Path, destination: Path) -> None:
    _require_source_tree(source)
    _ = shutil.copytree(source, destination, copy_function=shutil.copy2)


def _materialize_internal_file_links(root: Path) -> None:
    """Replace safe jlink file aliases with regular, independently hashed files."""
    resolved_root = root.resolve(strict=True)
    links: list[tuple[Path, Path]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_symlink():
            continue
        try:
            target = path.resolve(strict=True)
        except OSError as error:
            msg = "a generated runtime contains a broken symbolic link"
            raise RuntimeError(msg) from error
        if not target.is_relative_to(resolved_root):
            msg = "a generated runtime symbolic link points outside its tree"
            raise RuntimeError(msg)
        if not target.is_file():
            msg = "a generated runtime symbolic link does not target a file"
            raise RuntimeError(msg)
        links.append((path, target))
    for path, target in links:
        path.unlink()
        _ = shutil.copy2(target, path)


def _run(command: Sequence[str], cwd: Path) -> None:
    result = subprocess.run(  # noqa: S603
        tuple(command),
        cwd=cwd,
        env={
            "HOME": str(cwd),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": os.environ.get("PATH", ""),
            "TZ": "UTC",
        },
        check=False,
        capture_output=True,
        timeout=300,
    )
    if result.returncode != 0:
        msg = "a platform runtime build command failed"
        raise RuntimeError(msg)


def _build_jre(java_home: Path, destination: Path, cwd: Path) -> Path:
    executable = "jlink.exe" if os.name == "nt" else "jlink"
    jlink = java_home / "bin" / executable
    if jlink.is_symlink() or not jlink.is_file():
        msg = "Java 21 jlink was not found below --java-home"
        raise RuntimeError(msg)
    _run(
        (
            str(jlink),
            "--add-modules",
            ",".join(_JAVA_MODULES),
            "--strip-debug",
            "--no-header-files",
            "--no-man-pages",
            "--compress=zip-6",
            "--output",
            str(destination),
        ),
        cwd,
    )
    _materialize_internal_file_links(destination)
    java_name = "java.exe" if os.name == "nt" else "java"
    java = destination / "bin" / java_name
    if not java.is_file():
        msg = "jlink did not produce the expected Java runtime"
        raise RuntimeError(msg)
    _run((str(java), "-version"), cwd)
    return java


def _load_manifest() -> dict[str, object]:
    value = cast("object", json.loads(_MANIFEST_PATH.read_text(encoding="utf-8")))
    if not isinstance(value, dict):
        msg = "tool manifest root must be an object"
        raise TypeError(msg)
    return cast("dict[str, object]", value)


def _write_manifest(payload: dict[str, object]) -> None:
    with NamedTemporaryFile(
        prefix=".manifest.",
        suffix=".json.tmp",
        dir=_MANIFEST_PATH.parent,
        delete=False,
        mode="w",
        encoding="utf-8",
        newline="\n",
    ) as stream:
        temporary = Path(stream.name)
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        _ = stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    try:
        _ = temporary.replace(_MANIFEST_PATH)
    finally:
        temporary.unlink(missing_ok=True)


def _mapping(value: object, message: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError(message)
    return cast("dict[str, object]", value)


def _publish_runtime(
    staging: Path,
    destination: Path,
    payload: dict[str, object],
    temporary_root: Path,
) -> None:
    previous = temporary_root / "previous"
    if destination.exists():
        _ = destination.replace(previous)
    try:
        try:
            _ = staging.replace(destination)
            _write_manifest(payload)
        except BaseException:
            if destination.exists():
                _ = destination.replace(staging)
            raise
    except BaseException:
        if previous.exists():
            _ = previous.replace(destination)
        raise


def prepare(
    java_home: Path,
    exiftool_runtime: Path,
    exiftool_command: tuple[str, ...],
    *,
    replace_existing: bool = False,
) -> Path:
    """Build and atomically publish one current-platform runtime tree."""
    if not exiftool_command:
        msg = "at least one --exiftool-command path is required"
        raise ValueError(msg)
    if not _WORKER_JAR.is_file():
        msg = "build the shaded Apache worker JAR before platform resources"
        raise RuntimeError(msg)
    key = _platform_key()
    destination = _PACKAGED_ROOT / key
    if destination.exists() and not replace_existing:
        msg = "the platform resource directory already exists"
        raise FileExistsError(msg)
    _PACKAGED_ROOT.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=f".{key}.", dir=_PACKAGED_ROOT) as temporary_text:
        staging = Path(temporary_text) / key
        apache = staging / "apache"
        exiftool = staging / "exiftool"
        apache.mkdir(parents=True)
        java = _build_jre(java_home.resolve(), apache / "jre", staging.parent)
        _ = shutil.copy2(_WORKER_JAR, apache / "worker.jar")
        _copy_tree(exiftool_runtime.resolve(), exiftool)

        command_paths: list[Path] = []
        for relative_text in exiftool_command:
            relative = Path(relative_text)
            if relative.is_absolute() or ".." in relative.parts:
                msg = "an ExifTool command path is unsafe"
                raise ValueError(msg)
            path = exiftool / relative
            if path.is_symlink() or not path.is_file():
                msg = "an ExifTool command path is missing"
                raise RuntimeError(msg)
            command_paths.append(path)

        prefix = Path("tools/packaged") / key
        apache_files = _files(apache, prefix / "apache")
        exiftool_files = _files(exiftool, prefix / "exiftool")
        payload = _load_manifest()
        apache_manifest = _mapping(
            payload.get("apache_worker"), "Apache manifest configuration is missing"
        )
        apache_packaged = _mapping(
            apache_manifest.get("packaged"), "Apache packaged entries are missing"
        )
        exiftool_manifest = _mapping(
            payload.get("exiftool"), "ExifTool manifest configuration is missing"
        )
        exiftool_packaged = _mapping(
            exiftool_manifest.get("packaged"), "ExifTool packaged entries are missing"
        )
        apache_packaged[key] = {
            "available": True,
            "java": (prefix / "apache" / java.relative_to(apache)).as_posix(),
            "worker_jar": (prefix / "apache/worker.jar").as_posix(),
            "files": apache_files,
        }
        exiftool_packaged[key] = {
            "available": True,
            "command": [
                (prefix / "exiftool" / path.relative_to(exiftool)).as_posix()
                for path in command_paths
            ],
            "files": exiftool_files,
        }
        _publish_runtime(staging, destination, payload, Path(temporary_text))
    return destination


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build hash-locked resources for the current target platform."
    )
    _ = parser.add_argument("--java-home", type=Path, required=True)
    _ = parser.add_argument("--exiftool-runtime", type=Path, required=True)
    _ = parser.add_argument(
        "--exiftool-command",
        action="append",
        required=True,
        help="command path relative to --exiftool-runtime; repeat for Perl + script",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run current-platform resource preparation."""
    arguments = cast("_Arguments", cast("object", _parser().parse_args(argv)))
    result = prepare(
        arguments.java_home,
        arguments.exiftool_runtime,
        tuple(arguments.exiftool_command),
    )
    print(f"Prepared platform resources: {result}")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
