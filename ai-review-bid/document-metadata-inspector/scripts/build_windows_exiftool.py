"""Download and verify the locked standalone Windows ExifTool runtime."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import urllib.request
from hashlib import sha256
from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import TYPE_CHECKING, Protocol, cast
from zipfile import ZipFile

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import BinaryIO

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_MANIFEST_PATH = _PROJECT_ROOT / "tools/manifest.json"
_EXIFTOOL_README = _PROJECT_ROOT / "tools/vendor/exiftool/13.55/source/README"
_DEFAULT_CACHE = _PROJECT_ROOT / "tools/build-cache/downloads"
_CHUNK_BYTES = 1024 * 1024
_FILE_TYPE_MASK = 0o170000
_SYMLINK_TYPE = 0o120000


class _Arguments(Protocol):
    output: Path
    cache: Path


def _hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _config() -> tuple[str, str, str]:
    value = cast("object", json.loads(_MANIFEST_PATH.read_text(encoding="utf-8")))
    if not isinstance(value, dict):
        msg = "tool manifest root must be an object"
        raise TypeError(msg)
    payload = cast("dict[str, object]", value)
    runtime = payload.get("windows_exiftool")
    if not isinstance(runtime, dict):
        msg = "Windows ExifTool configuration is missing"
        raise TypeError(msg)
    runtime_map = cast("dict[str, object]", runtime)
    archive = runtime_map.get("official_archive")
    version = runtime_map.get("version")
    if not isinstance(archive, dict) or not isinstance(version, str):
        msg = "Windows ExifTool configuration is invalid"
        raise TypeError(msg)
    archive_map = cast("dict[str, object]", archive)
    url = archive_map.get("url")
    expected_hash = archive_map.get("sha256")
    if not isinstance(url, str) or not isinstance(expected_hash, str):
        msg = "Windows ExifTool archive configuration is invalid"
        raise TypeError(msg)
    return version, url, expected_hash


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(  # noqa: S310
        url,
        headers={"User-Agent": "document-metadata-inspector-build/0.1"},
    )
    response = cast(
        "BinaryIO",
        urllib.request.urlopen(request, timeout=120),  # noqa: S310
    )
    with response, destination.open("wb") as stream:
        while chunk := response.read(_CHUNK_BYTES):
            _ = stream.write(chunk)


def _archive(cache: Path, version: str, url: str, expected_hash: str) -> Path:
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / f"exiftool-{version}_64.zip"
    if archive.is_file():
        if _hash(archive) != expected_hash:
            msg = "the cached Windows ExifTool archive failed its integrity check"
            raise RuntimeError(msg)
        return archive
    with NamedTemporaryFile(
        prefix=f".exiftool-{version}.", suffix=".download", dir=cache, delete=False
    ) as stream:
        temporary = Path(stream.name)
    try:
        _download(url, temporary)
        if _hash(temporary) != expected_hash:
            msg = "the Windows ExifTool download failed its integrity check"
            raise RuntimeError(msg)
        _ = temporary.replace(archive)
    finally:
        temporary.unlink(missing_ok=True)
    return archive


def _safe_extract(archive: Path, destination: Path) -> Path:
    with ZipFile(archive) as source:
        infos = source.infolist()
        for info in infos:
            name = PurePosixPath(info.filename)
            if name.is_absolute() or ".." in name.parts or "\\" in info.filename:
                msg = "the Windows ExifTool archive contains an unsafe path"
                raise RuntimeError(msg)
            if (info.external_attr >> 16) & _FILE_TYPE_MASK == _SYMLINK_TYPE:
                msg = "the Windows ExifTool archive contains a symbolic link"
                raise RuntimeError(msg)
            target = destination.joinpath(*name.parts)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with source.open(info) as input_stream, target.open("xb") as output_stream:
                _ = shutil.copyfileobj(input_stream, output_stream)
    roots = tuple(path for path in destination.iterdir() if path.is_dir())
    if len(roots) != 1:
        msg = "the Windows ExifTool archive layout is invalid"
        raise RuntimeError(msg)
    return roots[0]


def build(output: Path, cache: Path) -> Path:
    """Create one standalone Windows ExifTool tree with bundled Perl."""
    if output.exists():
        msg = "the Windows ExifTool output already exists"
        raise FileExistsError(msg)
    version, url, expected_hash = _config()
    archive = _archive(cache, version, url, expected_hash)
    with TemporaryDirectory(prefix="docmeta-windows-exiftool-") as temporary_text:
        extracted = _safe_extract(archive, Path(temporary_text))
        executable = extracted / "exiftool(-k).exe"
        support = extracted / "exiftool_files"
        if not executable.is_file() or not support.is_dir():
            msg = "the Windows ExifTool archive is incomplete"
            raise RuntimeError(msg)
        staging = output.parent / f".{output.name}.staging"
        if staging.exists():
            msg = "a stale Windows ExifTool staging directory exists"
            raise FileExistsError(msg)
        staging.parent.mkdir(parents=True, exist_ok=True)
        _ = shutil.copytree(extracted, staging)
        try:
            _ = (staging / "exiftool(-k).exe").rename(staging / "exiftool.exe")
            licenses = staging / "licenses/exiftool"
            licenses.mkdir(parents=True)
            _ = shutil.copy2(_EXIFTOOL_README, licenses / "README")
            if os.name == "nt":
                result = subprocess.run(  # noqa: S603
                    (str(staging / "exiftool.exe"), "-ver"),
                    cwd=staging,
                    check=False,
                    capture_output=True,
                    timeout=30,
                )
                observed = result.stdout.decode("ascii", errors="strict").strip()
                if result.returncode != 0 or observed != version:
                    msg = "the Windows ExifTool runtime failed verification"
                    raise RuntimeError(msg)
            _ = staging.replace(output)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    return output


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build the locked standalone Windows ExifTool runtime."
    )
    _ = parser.add_argument("--output", type=Path, required=True)
    _ = parser.add_argument("--cache", type=Path, default=_DEFAULT_CACHE)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Build and report the Windows ExifTool runtime tree."""
    arguments = cast("_Arguments", cast("object", _parser().parse_args(argv)))
    runtime = build(arguments.output, arguments.cache)
    print(f"Windows ExifTool runtime is ready: {runtime}")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
