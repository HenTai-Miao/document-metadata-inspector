"""Install locked build-time parser sources after integrity verification."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tarfile
import urllib.request
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Protocol, cast

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import BinaryIO

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_MANIFEST_PATH = _PROJECT_ROOT / "tools/manifest.json"
_CHUNK_BYTES = 1024 * 1024


class _Arguments(Protocol):
    check: bool
    allow_system_development: bool


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_sha256(root: Path) -> str:
    digest = sha256()
    files = sorted(
        (path for path in root.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    if not files or any(path.is_symlink() for path in root.rglob("*")):
        msg = "invalid or empty ExifTool source tree"
        raise RuntimeError(msg)
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(_file_sha256(path)))
        digest.update(b"\0")
    return digest.hexdigest()


def _manifest() -> dict[str, object]:
    value = cast("object", json.loads(_MANIFEST_PATH.read_text(encoding="utf-8")))
    if not isinstance(value, dict):
        msg = "tool manifest root must be an object"
        raise TypeError(msg)
    return cast("dict[str, object]", value)


def _source_config(manifest: dict[str, object]) -> tuple[str, str, Path, str, str]:
    exiftool = manifest.get("exiftool")
    if not isinstance(exiftool, dict):
        msg = "tool manifest has no ExifTool configuration"
        raise TypeError(msg)
    exiftool_map = cast("dict[str, object]", exiftool)
    source = exiftool_map.get("official_source")
    version = exiftool_map.get("version")
    if not isinstance(source, dict) or not isinstance(version, str):
        msg = "tool manifest ExifTool configuration is invalid"
        raise TypeError(msg)
    source_map = cast("dict[str, object]", source)
    field_names = ("url", "sha256", "directory", "tree_sha256")
    fields = tuple(source_map.get(name) for name in field_names)
    if not all(isinstance(item, str) and item for item in fields):
        msg = "tool manifest official source configuration is invalid"
        raise RuntimeError(msg)
    url, artifact_hash, directory, tree_hash = cast("tuple[str, str, str, str]", fields)
    return version, url, _PROJECT_ROOT / directory, artifact_hash, tree_hash


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(  # noqa: S310
        url,
        headers={"User-Agent": "document-metadata-inspector-build/0.1"},
    )
    response = cast(
        "BinaryIO",
        urllib.request.urlopen(request, timeout=60),  # noqa: S310
    )
    with (
        response,
        destination.open("xb") as output,
    ):
        while chunk := response.read(_CHUNK_BYTES):
            _ = output.write(chunk)


def _extract(archive_path: Path, destination: Path, version: str) -> None:
    extract_root = destination.parent / ".extracting"
    if extract_root.exists():
        msg = "stale ExifTool extraction directory exists"
        raise RuntimeError(msg)
    extract_root.mkdir(parents=True)
    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            members = archive.getmembers()
            if any(not (member.isfile() or member.isdir()) for member in members):
                msg = "official ExifTool archive contains unsupported entries"
                raise RuntimeError(msg)
            archive.extractall(extract_root, members=members, filter="data")
        source_root = extract_root / f"Image-ExifTool-{version}"
        if not source_root.is_dir():
            msg = "official ExifTool archive layout is invalid"
            raise RuntimeError(msg)
        destination.parent.mkdir(parents=True, exist_ok=True)
        _ = shutil.copytree(source_root, destination)
    finally:
        shutil.rmtree(extract_root, ignore_errors=True)


def _system_version() -> str | None:
    executable = shutil.which("exiftool")
    if executable is None:
        return None
    result = subprocess.run(  # noqa: S603
        (executable, "-ver"),
        check=False,
        capture_output=True,
        timeout=5,
    )
    if result.returncode != 0:
        return None
    return result.stdout.decode("ascii", errors="replace").strip()


def bootstrap(*, check_only: bool, allow_system_development: bool) -> int:
    """Verify or install the locked project-local ExifTool source tree."""
    version, url, destination, artifact_hash, expected_tree_hash = _source_config(
        _manifest()
    )
    if destination.is_dir():
        observed = _tree_sha256(destination)
        if observed != expected_tree_hash:
            msg = "existing ExifTool source tree failed its integrity check"
            raise RuntimeError(msg)
        print(f"ExifTool {version} source is ready: {destination}")  # noqa: T201
        return 0

    if allow_system_development and _system_version() == version:
        print(  # noqa: T201
            f"System ExifTool {version} is usable for explicit development only."
        )
        return 0
    if check_only:
        print(f"ExifTool {version} source is missing.")  # noqa: T201
        return 1

    with TemporaryDirectory(prefix="docmeta-exiftool-download-") as temporary:
        archive_path = Path(temporary) / f"Image-ExifTool-{version}.tar.gz"
        _download(url, archive_path)
        if _file_sha256(archive_path) != artifact_hash:
            msg = "downloaded ExifTool artifact failed its SHA-256 check"
            raise RuntimeError(msg)
        _extract(archive_path, destination, version)
    if _tree_sha256(destination) != expected_tree_hash:
        msg = "installed ExifTool source tree failed its integrity check"
        raise RuntimeError(msg)
    print(f"Installed ExifTool {version} source: {destination}")  # noqa: T201
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify or install locked build-time parser tools.",
    )
    _ = parser.add_argument(
        "--check",
        action="store_true",
        help="check only; do not download a missing source artifact",
    )
    _ = parser.add_argument(
        "--allow-system-development",
        action="store_true",
        help="accept an exact system ExifTool only for local development",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the build-machine bootstrap without changing system packages."""
    arguments = cast("_Arguments", cast("object", _parser().parse_args(argv)))
    return bootstrap(
        check_only=arguments.check,
        allow_system_development=arguments.allow_system_development,
    )


if __name__ == "__main__":
    raise SystemExit(main())
