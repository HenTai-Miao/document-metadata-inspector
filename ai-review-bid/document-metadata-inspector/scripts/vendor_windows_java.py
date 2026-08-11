"""Transactionally vendor the verified Windows x64 JRE and Apache worker."""

from __future__ import annotations

import argparse
import json
import os
import stat
import urllib.request
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Protocol, cast
from urllib.parse import urlparse

if __package__:
    from scripts.bootstrap_jdk import ensure_jdk
    from scripts.build_apache_worker import build_worker
    from scripts.windows_vendored_java import (
        VendoredWindowsJavaFiles,
        verify_vendored_windows_java_files,
        worker_inputs_sha256,
    )
else:
    from bootstrap_jdk import (  # pyright: ignore[reportImplicitRelativeImport]
        ensure_jdk,
    )
    from build_apache_worker import (  # pyright: ignore[reportImplicitRelativeImport]
        build_worker,
    )
    from windows_vendored_java import (  # pyright: ignore[reportImplicitRelativeImport]
        VendoredWindowsJavaFiles,
        verify_vendored_windows_java_files,
        worker_inputs_sha256,
    )

if TYPE_CHECKING:
    from typing import BinaryIO

_TARGET_KEY = "windows-x86_64"
_HASH_CHUNK_BYTES = 1024 * 1024
_SHA256_HEX_LENGTH = 64
_EXPECTED_JRE_URL = (
    "https://github.com/adoptium/temurin21-binaries/releases/"
    "download/jdk-21.0.12%2B8/"
    "OpenJDK21U-jre_x64_windows_hotspot_21.0.12_8.zip"
)
_EXPECTED_JRE_SHA256 = (
    "b8aa18fef5edb69bee8618f99677d66d0873d22cb40d974c15ac9ffcdecf73ba"
)
_EXPECTED_JRE_ARCHIVE_TYPE = "zip"
_JRE_RELATIVE_PATH = Path("tools/prebuilt/windows-x86_64") / (
    "OpenJDK21U-jre_x64_windows_hotspot_21.0.12_8.zip"
)
_WORKER_RELATIVE_PATH = Path(
    "tools/prebuilt/windows-x86_64/document-metadata-apache-worker.jar"
)
_WORKER_ARTIFACT_VERSION = "0.1.0"
_WORKER_RUNTIME_VERSION = "21.0.12+8"
_WORKER_BUILD_COMMAND = ("mvnw", "--batch-mode", "--no-transfer-progress", "verify")


class _Arguments(Protocol):
    cache: Path


@dataclass(frozen=True, slots=True)
class _OfficialJre:
    url: str
    sha256: str


@dataclass(frozen=True, slots=True)
class _StagedArtifact:
    path: Path
    size: int
    sha256: str


def _mapping(value: object, message: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError(message)
    return cast("dict[str, object]", value)


def _text(value: object, message: str) -> str:
    if not isinstance(value, str) or not value:
        raise TypeError(message)
    return value


def _sha256(value: object, message: str) -> str:
    digest = _text(value, message)
    if len(digest) != _SHA256_HEX_LENGTH or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise TypeError(message)
    return digest


def _read_manifest(path: Path) -> dict[str, object]:
    try:
        value = cast("object", json.loads(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        msg = "the tool manifest is invalid"
        raise RuntimeError(msg) from error
    return _mapping(value, "the tool manifest root must be an object")


def _official_jre(manifest: dict[str, object]) -> _OfficialJre:
    """Return only the immutable official Windows x64 JRE identity."""
    temurin = _mapping(
        manifest.get("temurin_jre"), "Temurin JRE configuration is missing"
    )
    archives = _mapping(
        temurin.get("archives"), "Temurin JRE archive configuration is missing"
    )
    archive = _mapping(
        archives.get(_TARGET_KEY), "Windows Temurin JRE configuration is missing"
    )
    url = _text(archive.get("url"), "official Temurin JRE configuration is invalid")
    digest = _sha256(
        archive.get("sha256"), "official Temurin JRE configuration is invalid"
    )
    archive_type = _text(
        archive.get("archive_type"), "official Temurin JRE configuration is invalid"
    )
    if (
        url != _EXPECTED_JRE_URL
        or digest != _EXPECTED_JRE_SHA256
        or archive_type != _EXPECTED_JRE_ARCHIVE_TYPE
    ):
        msg = "official Temurin JRE configuration has the wrong target identity"
        raise RuntimeError(msg)
    return _OfficialJre(url=url, sha256=digest)


def _hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, destination: Path) -> None:
    """Stream the official JRE into one private cache download file."""
    request = urllib.request.Request(  # noqa: S310
        url,
        headers={"User-Agent": "document-metadata-inspector-build/0.1"},
    )
    response = cast(
        "BinaryIO",
        urllib.request.urlopen(request, timeout=120),  # noqa: S310
    )
    with response, destination.open("xb") as output:
        while chunk := response.read(_HASH_CHUNK_BYTES):
            _ = output.write(chunk)
        output.flush()
        os.fsync(output.fileno())


def _downloaded_jre(cache: Path, official: _OfficialJre) -> Path:
    downloads = cache / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    filename = Path(urlparse(official.url).path).name
    if not filename:
        msg = "official Temurin JRE URL has no filename"
        raise RuntimeError(msg)
    archive = downloads / filename
    if archive.exists():
        _ = _require_regular(archive, "the cached Temurin JRE archive")
        if _hash(archive) != official.sha256:
            msg = "the cached Temurin JRE archive failed its integrity check"
            raise RuntimeError(msg)
        return archive

    temporary = downloads / f".{filename}.download"
    try:
        if temporary.exists():
            _ = _require_regular(temporary, "the incomplete Temurin JRE download")
            temporary.unlink()
        _download(official.url, temporary)
    except OSError as error:
        temporary.unlink(missing_ok=True)
        msg = "the official Temurin JRE download failed"
        raise RuntimeError(msg) from error
    if _hash(temporary) != official.sha256:
        temporary.unlink(missing_ok=True)
        msg = "the downloaded Temurin JRE failed its integrity check"
        raise RuntimeError(msg)
    try:
        _replace(temporary, archive)
    except OSError as error:
        temporary.unlink(missing_ok=True)
        msg = "the verified Temurin JRE cache could not be published"
        raise RuntimeError(msg) from error
    return archive


def _require_regular(path: Path, description: str) -> os.stat_result:
    try:
        metadata = path.lstat()
    except OSError as error:
        msg = f"{description} is missing"
        raise RuntimeError(msg) from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        msg = f"{description} must be a regular file"
        raise RuntimeError(msg)
    if metadata.st_size <= 0:
        msg = f"{description} is empty"
        raise RuntimeError(msg)
    return metadata


def _stage_regular_file(
    source: Path,
    destination: Path,
    description: str,
) -> _StagedArtifact:
    """Snapshot a regular file and fsync the exact bytes that will publish."""
    _ = _require_regular(source, description)
    digest = sha256()
    size = 0
    try:
        with source.open("rb") as input_stream, destination.open("xb") as output:
            source_metadata = os.fstat(input_stream.fileno())
            if not stat.S_ISREG(source_metadata.st_mode):
                msg = f"{description} must be a regular file"
                raise RuntimeError(msg)
            while chunk := input_stream.read(_HASH_CHUNK_BYTES):
                size += len(chunk)
                digest.update(chunk)
                _ = output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
    except OSError as error:
        msg = f"{description} could not be staged"
        raise RuntimeError(msg) from error
    if size <= 0:
        msg = f"{description} is empty"
        raise RuntimeError(msg)
    return _StagedArtifact(destination, size, digest.hexdigest())


def _staged_manifest(
    manifest: dict[str, object],
    jre: _StagedArtifact,
    worker: _StagedArtifact,
    source_tree_sha256: str,
    destination: Path,
) -> None:
    apache = _mapping(
        manifest.get("apache_worker"), "Apache worker configuration is missing"
    )
    vendored_value = apache.get("vendored")
    if vendored_value is None:
        vendored: dict[str, object] = {}
        apache["vendored"] = vendored
    else:
        vendored = _mapping(
            vendored_value,
            "Apache worker vendored configuration is invalid",
        )
    vendored[_TARGET_KEY] = {
        "path": _WORKER_RELATIVE_PATH.as_posix(),
        "size": worker.size,
        "sha256": worker.sha256,
        "source_tree_sha256": source_tree_sha256,
        "artifact_version": _WORKER_ARTIFACT_VERSION,
        "build_java_runtime_version": _WORKER_RUNTIME_VERSION,
        "build_command": list(_WORKER_BUILD_COMMAND),
    }

    temurin = _mapping(
        manifest.get("temurin_jre"), "Temurin JRE configuration is missing"
    )
    archives = _mapping(
        temurin.get("archives"), "Temurin JRE archive configuration is missing"
    )
    archive = _mapping(
        archives.get(_TARGET_KEY), "Windows Temurin JRE configuration is missing"
    )
    archive["vendored_path"] = _JRE_RELATIVE_PATH.as_posix()
    archive["size"] = jre.size
    archive["sha256"] = jre.sha256

    encoded = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8"
    )
    try:
        with destination.open("xb") as output:
            _ = output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
    except OSError as error:
        msg = "the vendored Windows Java manifest could not be staged"
        raise RuntimeError(msg) from error


def _replace(source: Path, destination: Path) -> None:
    """Rename a same-filesystem transaction member into place."""
    _ = source.replace(destination)


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        msg = "the vendored Windows Java destination directory is unavailable"
        raise RuntimeError(msg) from error
    try:
        os.fsync(descriptor)
    except OSError as error:
        msg = "the vendored Windows Java destination directory could not be synced"
        raise RuntimeError(msg) from error
    finally:
        os.close(descriptor)


def _target_exists(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    except OSError as error:
        msg = "a vendored Windows Java target is unavailable"
        raise RuntimeError(msg) from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        msg = "a vendored Windows Java target must be a regular file"
        raise RuntimeError(msg)
    return True


def _backup_existing_targets(
    staged: tuple[tuple[Path, Path], ...],
    transaction: Path,
) -> list[tuple[Path, Path]]:
    backups: list[tuple[Path, Path]] = []
    for index, (_source, target) in enumerate(staged):
        if _target_exists(target):
            backup = transaction / f"previous-{index}"
            _replace(target, backup)
            backups.append((target, backup))
    return backups


def _publish_staged_targets(
    staged: tuple[tuple[Path, Path], ...],
) -> list[Path]:
    published: list[Path] = []
    for source, target in staged:
        _replace(source, target)
        published.append(target)
    return published


def _sync_target_directories(staged: tuple[tuple[Path, Path], ...]) -> None:
    for _source, target in staged:
        _fsync_directory(target.parent)


def _rollback_publication(
    published: list[Path],
    backups: list[tuple[Path, Path]],
    staged: tuple[tuple[Path, Path], ...],
    transaction: Path,
) -> None:
    rollback_error: Exception | None = None
    for index, target in enumerate(reversed(published)):
        try:
            if target.exists():
                _replace(target, transaction / f"failed-{index}")
        except (OSError, RuntimeError) as error:
            rollback_error = rollback_error or error
    for target, backup in reversed(backups):
        try:
            if backup.exists():
                _replace(backup, target)
        except (OSError, RuntimeError) as error:
            rollback_error = rollback_error or error
    for _source, target in staged:
        try:
            _fsync_directory(target.parent)
        except RuntimeError as error:
            rollback_error = rollback_error or error
    if rollback_error is not None:
        msg = "vendored Windows Java publication failed and rollback was incomplete"
        raise RuntimeError(msg) from rollback_error


def _publish(
    staged: tuple[tuple[Path, Path], ...],
    transaction: Path,
) -> None:
    """Publish every target or restore every prior target after one failure."""
    for _source, target in staged:
        target.parent.mkdir(parents=True, exist_ok=True)
        _ = _target_exists(target)

    backups: list[tuple[Path, Path]] = []
    published: list[Path] = []
    try:
        backups = _backup_existing_targets(staged, transaction)
        published = _publish_staged_targets(staged)
        _sync_target_directories(staged)
    except (OSError, RuntimeError):
        _rollback_publication(published, backups, staged, transaction)
        raise


def vendor_windows_java(project_root: Path, cache: Path) -> VendoredWindowsJavaFiles:
    """Build and atomically publish the pinned Windows x64 JRE and Worker JAR."""
    project_root = project_root.resolve()
    cache = cache.resolve()
    manifest_path = project_root / "tools/manifest.json"
    manifest = _read_manifest(manifest_path)
    official = _official_jre(manifest)
    downloaded = _downloaded_jre(cache, official)
    java_home = ensure_jdk(cache / "temurin")
    built_worker = build_worker(java_home)

    with TemporaryDirectory(prefix=".windows-java-vendor.", dir=project_root) as text:
        transaction = Path(text)
        staged_jre = _stage_regular_file(
            downloaded,
            transaction / _JRE_RELATIVE_PATH.name,
            "Temurin JRE archive",
        )
        if staged_jre.sha256 != official.sha256:
            msg = "the staged Temurin JRE failed its integrity check"
            raise RuntimeError(msg)
        staged_worker = _stage_regular_file(
            built_worker,
            transaction / _WORKER_RELATIVE_PATH.name,
            "Apache worker JAR",
        )
        source_tree_sha256 = _sha256(
            worker_inputs_sha256(project_root),
            "Apache worker source hash is invalid",
        )
        _staged_manifest(
            manifest,
            staged_jre,
            staged_worker,
            source_tree_sha256,
            transaction / "manifest.json",
        )
        _publish(
            (
                (staged_jre.path, project_root / _JRE_RELATIVE_PATH),
                (staged_worker.path, project_root / _WORKER_RELATIVE_PATH),
                (transaction / "manifest.json", manifest_path),
            ),
            transaction,
        )
    return verify_vendored_windows_java_files(project_root)


def _repository_relative(project_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError as error:
        msg = "vendored Windows Java output left the repository"
        raise RuntimeError(msg) from error


def _cli() -> int:
    parser = argparse.ArgumentParser(
        description="Vendor the pinned Windows x64 Temurin JRE and Apache worker."
    )
    _ = parser.add_argument("--cache", required=True, type=Path)
    arguments = cast("_Arguments", cast("object", parser.parse_args()))
    project_root = Path(__file__).resolve().parents[1]
    cache = arguments.cache
    if not cache.is_absolute():
        cache = project_root / cache
    verified = vendor_windows_java(project_root, cache)
    manifest = project_root / "tools/manifest.json"
    for path in (verified.jre_archive, verified.worker_jar, manifest):
        relative_path = _repository_relative(project_root, path)
        size = path.stat().st_size
        digest = _hash(path)
        _ = print(  # noqa: T201
            f"{relative_path} size={size} sha256={digest}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
