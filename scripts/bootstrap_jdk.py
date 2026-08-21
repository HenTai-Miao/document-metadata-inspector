"""Detect or install a pinned project-local Eclipse Temurin JDK 21."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import tarfile
import urllib.request
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import TYPE_CHECKING, Literal, Protocol, cast
from urllib.parse import urlparse
from zipfile import ZipFile

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from typing import BinaryIO

type ArchiveType = Literal["tar.gz", "zip"]

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_MANIFEST_PATH = _PROJECT_ROOT / "tools/manifest.json"
_DEFAULT_CACHE = _PROJECT_ROOT / "tools/build-cache/temurin"
_HASH_CHUNK_BYTES = 1024 * 1024
_VENDOR_MARKERS = ("Eclipse Adoptium", "Eclipse Temurin")


@dataclass(frozen=True, slots=True)
class _ArchiveConfig:
    version: str
    url: str
    sha256: str
    archive_type: ArchiveType


class _Arguments(Protocol):
    cache: Path
    candidate: list[Path]


def _platform_key() -> str:
    from document_metadata_inspector.resources import platform_key  # noqa: PLC0415

    return platform_key()


def _mapping(value: object, message: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError(message)
    return cast("dict[str, object]", value)


def _configuration(key: str) -> _ArchiveConfig:
    value = cast("object", json.loads(_MANIFEST_PATH.read_text(encoding="utf-8")))
    payload = _mapping(value, "tool manifest root must be an object")
    temurin = _mapping(
        payload.get("temurin_jdk"), "Temurin JDK configuration is missing"
    )
    archives = _mapping(
        temurin.get("archives"), "Temurin JDK archive entries are missing"
    )
    archive = _mapping(
        archives.get(key), "Temurin JDK is not configured for this platform"
    )
    version = temurin.get("version")
    url = archive.get("url")
    expected_hash = archive.get("sha256")
    archive_type = archive.get("archive_type")
    if (
        not isinstance(version, str)
        or not isinstance(url, str)
        or not isinstance(expected_hash, str)
        or archive_type not in ("tar.gz", "zip")
    ):
        msg = "Temurin JDK archive configuration is invalid"
        raise TypeError(msg)
    return _ArchiveConfig(
        version=version,
        url=url,
        sha256=expected_hash,
        archive_type=archive_type,
    )


def _hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


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
        while chunk := response.read(_HASH_CHUNK_BYTES):
            _ = stream.write(chunk)


def _cached_archive(cache: Path, key: str, config: _ArchiveConfig) -> Path:
    downloads = cache / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    name = Path(urlparse(config.url).path).name
    if not name:
        msg = "Temurin JDK archive URL has no filename"
        raise RuntimeError(msg)
    archive = downloads / f"{key}-{name}"
    if archive.is_file():
        if _hash(archive) != config.sha256:
            msg = "the cached Temurin JDK archive failed its integrity check"
            raise RuntimeError(msg)
        return archive
    with NamedTemporaryFile(
        prefix=f".{key}-temurin.", suffix=".download", dir=downloads, delete=False
    ) as stream:
        temporary = Path(stream.name)
    try:
        _download(config.url, temporary)
        if _hash(temporary) != config.sha256:
            msg = "the downloaded Temurin JDK archive failed its integrity check"
            raise RuntimeError(msg)
        _ = temporary.replace(archive)
    finally:
        temporary.unlink(missing_ok=True)
    return archive


def _safe_member_name(name: str) -> bool:
    if not name or "\\" in name:
        return False
    path = PurePosixPath(name)
    return not path.is_absolute() and all(part not in ("", "..") for part in path.parts)


def _extract_zip(archive: Path, destination: Path) -> None:
    """Extract a Windows JDK ZIP only after validating every member."""
    with ZipFile(archive) as package:
        members = package.infolist()
        for member in members:
            mode = (member.external_attr >> 16) & 0xFFFF
            if not _safe_member_name(member.filename) or stat.S_ISLNK(mode):
                msg = "the Temurin JDK ZIP contains an unsafe member"
                raise RuntimeError(msg)
        destination.mkdir(parents=True)
        for member in members:
            relative = PurePosixPath(member.filename)
            target = destination.joinpath(*relative.parts)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with package.open(member) as source, target.open("xb") as output:
                _ = shutil.copyfileobj(source, output)
            mode = (member.external_attr >> 16) & 0o777
            if mode:
                target.chmod(mode)


def _extract_tar(archive: Path, destination: Path) -> None:
    """Extract a Unix JDK archive with Python's data-only safety filter."""
    with tarfile.open(archive, "r:gz") as package:
        members = package.getmembers()
        if any(not _safe_member_name(member.name) for member in members):
            msg = "the Temurin JDK tarball contains an unsafe member name"
            raise RuntimeError(msg)
        if any(
            not (member.isfile() or member.isdir() or member.issym() or member.islnk())
            for member in members
        ):
            msg = "the Temurin JDK tarball contains an unsupported member"
            raise RuntimeError(msg)
        destination.mkdir(parents=True)
        package.extractall(destination, members=members, filter="data")


def _java_name() -> str:
    return "java.exe" if os.name == "nt" else "java"


def _jdk_home(candidate: Path) -> Path:
    resolved = candidate.expanduser().resolve()
    if resolved.name.casefold() == _java_name().casefold():
        return resolved.parent.parent
    mac_home = resolved / "Contents/Home"
    if mac_home.is_dir():
        return mac_home
    return resolved


def _compatible(home: Path, expected_version: str) -> bool:
    java = home / "bin" / _java_name()
    jlink_name = "jlink.exe" if os.name == "nt" else "jlink"
    jlink = home / "bin" / jlink_name
    if not java.is_file() or not jlink.is_file():
        return False
    try:
        result = subprocess.run(  # noqa: S603
            (str(java), "-XshowSettings:properties", "-version"),
            cwd=home,
            env={
                "HOME": str(home),
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "PATH": os.environ.get("PATH", ""),
                "TZ": "UTC",
            },
            check=False,
            capture_output=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    output = (result.stdout + result.stderr).decode("utf-8", errors="replace")
    return (
        result.returncode == 0
        and f"java.runtime.version = {expected_version}" in output
        and any(f"java.vendor = {marker}" in output for marker in _VENDOR_MARKERS)
    )


def _find_home(root: Path, expected_version: str) -> Path | None:
    direct = _jdk_home(root)
    if _compatible(direct, expected_version):
        return direct
    candidates = sorted(root.rglob(_java_name()), key=lambda path: path.as_posix())
    for executable in candidates:
        home = _jdk_home(executable)
        if _compatible(home, expected_version):
            return home
    return None


def _existing_candidates(explicit: Iterable[Path]) -> tuple[Path, ...]:
    candidates = list(explicit)
    for name in ("DOCMETA_JAVA_HOME", "JAVA_HOME"):
        value = os.environ.get(name)
        if value:
            candidates.append(Path(value))
    java = shutil.which(_java_name())
    if java:
        candidates.append(Path(java))
    return tuple(candidates)


def ensure_jdk(cache: Path, explicit_candidates: Iterable[Path] = ()) -> Path:
    """Return an exact Temurin JDK home, downloading it only when absent."""
    key = _platform_key()
    config = _configuration(key)
    cache = cache.expanduser().resolve()
    destination = cache / config.version.replace("+", "_") / key

    if destination.exists():
        cached_home = _find_home(destination, config.version)
        if cached_home is None:
            msg = "the project-local Temurin JDK cache is invalid"
            raise RuntimeError(msg)
        return cached_home

    for candidate in _existing_candidates(explicit_candidates):
        home = _jdk_home(candidate)
        if _compatible(home, config.version):
            return home

    archive = _cached_archive(cache, key, config)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        prefix=f".{key}-temurin.", dir=destination.parent
    ) as temporary_text:
        extracted = Path(temporary_text) / "extracted"
        if config.archive_type == "zip":
            _extract_zip(archive, extracted)
        else:
            _extract_tar(archive, extracted)
        home = _find_home(extracted, config.version)
        if home is None:
            msg = "the extracted Temurin archive did not contain the expected JDK"
            raise RuntimeError(msg)
        relative_home = home.relative_to(extracted)
        _ = extracted.replace(destination)
    installed_home = destination / relative_home
    if not _compatible(installed_home, config.version):
        msg = "the installed project-local Temurin JDK failed verification"
        raise RuntimeError(msg)
    return installed_home


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Detect or install the pinned project-local Temurin JDK."
    )
    _ = parser.add_argument("--cache", type=Path, default=_DEFAULT_CACHE)
    _ = parser.add_argument(
        "--candidate",
        type=Path,
        action="append",
        default=[],
        help="existing JDK home or java executable to test before downloading",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Print the verified JDK home for build-script composition."""
    arguments = cast("_Arguments", cast("object", _parser().parse_args(argv)))
    home = ensure_jdk(arguments.cache, arguments.candidate)
    print(home)  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
