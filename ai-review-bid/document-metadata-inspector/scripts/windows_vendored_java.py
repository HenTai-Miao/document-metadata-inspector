"""Validate pinned Windows Java artifacts before they enter a release build."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import zipfile
from contextlib import suppress
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import BinaryIO, cast

_HASH_CHUNK_BYTES = 1024 * 1024
_TARGET_KEY = "windows-x86_64"
_EXPECTED_BUILD_COMMAND = (
    "mvnw",
    "--batch-mode",
    "--no-transfer-progress",
    "verify",
)
_EXPECTED_JRE_RELATIVE_PATH = (
    "tools/prebuilt/windows-x86_64/OpenJDK21U-jre_x64_windows_hotspot_21.0.12_8.zip"
)
_EXPECTED_JRE_URL = (
    "https://github.com/adoptium/temurin21-binaries/releases/"
    "download/jdk-21.0.12%2B8/"
    "OpenJDK21U-jre_x64_windows_hotspot_21.0.12_8.zip"
)
_EXPECTED_JAVA_RUNTIME_VERSION = "21.0.12+8"
_EXPECTED_WORKER_ARTIFACT_VERSION = "0.1.0"
_EXPECTED_WORKER_RELATIVE_PATH = (
    "tools/prebuilt/windows-x86_64/document-metadata-apache-worker.jar"
)
_SHA256_LENGTH = 64
_MAX_ZIP_ENTRIES = 50_000
_MAX_ZIP_EXPANDED_BYTES = 4 * 1024 * 1024 * 1024
_MAX_RELEASE_BYTES = 64 * 1024
_MAX_INTEGRITY_BYTES = 16 * 1024 * 1024
_MAX_NATIVE_OUTPUT_BYTES = 64 * 1024
_NATIVE_PROBE_TIMEOUT_SECONDS = 15
_DOS_HEADER_BYTES = 0x40
_ASCII_CONTROL_END = 32
_WINDOWS_RESERVED_NAMES = frozenset(
    {
        "con",
        "prn",
        "aux",
        "nul",
        "com¹",
        "com²",
        "com³",
        "lpt¹",
        "lpt²",
        "lpt³",
        *(f"com{number}" for number in range(1, 10)),
        *(f"lpt{number}" for number in range(1, 10)),
    }
)
_WINDOWS_INVALID_COMPONENT_CHARACTERS = frozenset('<>:"|?*')
_WORKER_INPUTS = (
    Path("java-worker/pom.xml"),
    Path("java-worker/mvnw"),
    Path("java-worker/mvnw.cmd"),
    Path("java-worker/.mvn"),
    Path("java-worker/src/main"),
    Path("java-worker/src/test"),
)


@dataclass(frozen=True, slots=True)
class VendoredWindowsJavaFiles:
    """Hold verified Windows x64 Java artifacts and their runtime version."""

    jre_archive: Path
    worker_jar: Path
    java_runtime_version: str
    jre_archive_size: int | None = None
    jre_archive_sha256: str | None = None
    worker_jar_size: int | None = None
    worker_jar_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class PreparedWindowsJava:
    """Hold the materialized JRE and the verified Apache worker JAR."""

    java_home: Path
    worker_jar: Path


def _mapping(value: object, message: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError(message)
    return cast("dict[str, object]", value)


def _text(value: object, message: str) -> str:
    if not isinstance(value, str) or not value:
        raise TypeError(message)
    return value


def _positive_size(value: object, message: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise TypeError(message)
    return value


def _sha256(value: object, message: str) -> str:
    digest = _text(value, message)
    if len(digest) != _SHA256_LENGTH or any(
        char not in "0123456789abcdef" for char in digest
    ):
        raise TypeError(message)
    return digest


def _build_command(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        msg = "Apache worker build command is invalid"
        raise TypeError(msg)
    values = cast("list[object]", value)
    if any(not isinstance(item, str) for item in values):
        msg = "Apache worker build command is invalid"
        raise TypeError(msg)
    command = tuple(cast("list[str]", values))
    if command != _EXPECTED_BUILD_COMMAND:
        msg = "Apache worker build command is invalid"
        raise RuntimeError(msg)
    return command


def _manifest(project_root: Path) -> dict[str, object]:
    manifest = project_root / "tools/manifest.json"
    try:
        value = cast("object", json.loads(manifest.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        msg = "vendored Windows Java manifest is invalid"
        raise TypeError(msg) from error
    return _mapping(value, "vendored Windows Java manifest must be an object")


def _safe_project_file(project_root: Path, value: object, description: str) -> Path:
    if not isinstance(value, str):
        msg = f"{description} path is invalid"
        raise TypeError(msg)
    path_text = value
    if not path_text or "\\" in path_text:
        msg = f"{description} path is unsafe"
        raise RuntimeError(msg)
    relative = PurePosixPath(path_text)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in ("", ".", "..") or ":" in part for part in relative.parts)
    ):
        msg = f"{description} path is unsafe"
        raise RuntimeError(msg)
    target = project_root.joinpath(*relative.parts)
    try:
        _ = target.relative_to(project_root)
    except ValueError as error:
        msg = f"{description} path is unsafe"
        raise RuntimeError(msg) from error
    return target


def _require_regular_non_sparse(path: Path, description: str) -> os.stat_result:
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
    sparse_flag = getattr(stat, "FILE_ATTRIBUTE_SPARSE_FILE", 0)
    is_sparse = (
        bool(getattr(metadata, "st_file_attributes", 0) & sparse_flag)
        if os.name == "nt"
        else hasattr(metadata, "st_blocks")
        and metadata.st_blocks * 512 < metadata.st_size
    )
    if is_sparse:
        msg = f"{description} is sparse"
        raise RuntimeError(msg)
    return metadata


def _require_safe_parent_chain(
    project_root: Path, path: Path, description: str
) -> None:
    current = project_root
    for part in path.relative_to(project_root).parts[:-1]:
        current /= part
        try:
            metadata = current.lstat()
        except OSError as error:
            msg = f"{description} is missing"
            raise RuntimeError(msg) from error
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            msg = f"{description} path is unsafe"
            raise RuntimeError(msg)


def _hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _input_files(project_root: Path) -> list[Path]:
    inputs: list[Path] = []
    for relative in _WORKER_INPUTS:
        path = project_root / relative
        metadata = _require_worker_input_chain(project_root, path)
        if relative.suffix or relative.name in {"mvnw", "mvnw.cmd"}:
            if not stat.S_ISREG(metadata.st_mode):
                msg = "Apache worker source input must be a regular file"
                raise RuntimeError(msg)
            inputs.append(path)
            continue
        if not stat.S_ISDIR(metadata.st_mode):
            msg = "Apache worker source input must be a regular directory"
            raise RuntimeError(msg)
        inputs.extend(_files_in_tree(path))
    return sorted(inputs, key=lambda path: path.relative_to(project_root).as_posix())


def _require_worker_input_chain(project_root: Path, path: Path) -> os.stat_result:
    current = project_root
    metadata = _worker_input_metadata(current)
    for part in path.relative_to(project_root).parts:
        if not stat.S_ISDIR(metadata.st_mode):
            msg = "Apache worker source input has an invalid ancestor"
            raise RuntimeError(msg)
        current /= part
        metadata = _worker_input_metadata(current)
    return metadata


def _worker_input_metadata(path: Path) -> os.stat_result:
    try:
        metadata = path.lstat()
    except OSError as error:
        msg = "Apache worker source input is missing"
        raise RuntimeError(msg) from error
    if stat.S_ISLNK(metadata.st_mode):
        msg = "Apache worker source input contains a symbolic link"
        raise RuntimeError(msg)
    return metadata


def _files_in_tree(root: Path) -> list[Path]:
    files: list[Path] = []
    for child in root.rglob("*"):
        metadata = child.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            msg = "Apache worker source input contains a symbolic link"
            raise RuntimeError(msg)
        if stat.S_ISREG(metadata.st_mode):
            files.append(child)
        elif not stat.S_ISDIR(metadata.st_mode):
            msg = "Apache worker source input contains a non-regular entry"
            raise RuntimeError(msg)
    return files


def worker_inputs_sha256(project_root: Path) -> str:
    """Hash the bounded Maven inputs without considering generated output."""
    digest = sha256()
    for path in _input_files(project_root):
        digest.update(path.relative_to(project_root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as stream:
            while chunk := stream.read(_HASH_CHUNK_BYTES):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def verify_vendored_windows_java_files(project_root: Path) -> VendoredWindowsJavaFiles:
    """Fail closed unless Windows Java artifacts match manifest and source inputs."""
    manifest = _manifest(project_root)
    apache = _mapping(
        manifest.get("apache_worker"), "Apache worker configuration is missing"
    )
    vendored = _mapping(
        apache.get("vendored"), "Apache worker vendored configuration is missing"
    )
    worker = _mapping(
        vendored.get(_TARGET_KEY), "Windows Apache worker configuration is missing"
    )
    temurin = _mapping(
        manifest.get("temurin_jre"), "Temurin JRE configuration is missing"
    )
    archives = _mapping(temurin.get("archives"), "Temurin JRE archives are missing")
    jre = _mapping(
        archives.get(_TARGET_KEY), "Windows Temurin JRE configuration is missing"
    )

    worker_path = _safe_project_file(project_root, worker.get("path"), "Apache worker")
    jre_path = _safe_project_file(project_root, jre.get("vendored_path"), "Temurin JRE")
    if worker.get("path") != _EXPECTED_WORKER_RELATIVE_PATH:
        msg = "Apache worker path has the wrong target identity"
        raise RuntimeError(msg)
    if jre.get("vendored_path") != _EXPECTED_JRE_RELATIVE_PATH:
        msg = "Temurin JRE path has the wrong target identity"
        raise RuntimeError(msg)
    worker_size = _positive_size(worker.get("size"), "Apache worker size is invalid")
    jre_size = _positive_size(jre.get("size"), "Temurin JRE size is invalid")
    worker_hash = _sha256(worker.get("sha256"), "Apache worker SHA-256 is invalid")
    jre_hash = _sha256(jre.get("sha256"), "Temurin JRE SHA-256 is invalid")
    source_hash = _sha256(
        worker.get("source_tree_sha256"), "Apache worker source hash is invalid"
    )
    artifact_version = _text(
        worker.get("artifact_version"), "Apache worker artifact version is invalid"
    )
    if artifact_version != _EXPECTED_WORKER_ARTIFACT_VERSION:
        msg = "Apache worker artifact version is invalid"
        raise RuntimeError(msg)
    runtime_version = _text(
        worker.get("build_java_runtime_version"),
        "Apache worker Java version is invalid",
    )
    if runtime_version != _EXPECTED_JAVA_RUNTIME_VERSION:
        msg = "Apache worker Java version is invalid"
        raise RuntimeError(msg)
    _ = _build_command(worker.get("build_command"))
    jre_url = _text(jre.get("url"), "Temurin JRE URL is invalid")
    if jre_url != _EXPECTED_JRE_URL:
        msg = "Temurin JRE URL has the wrong target identity"
        raise RuntimeError(msg)
    if _text(jre.get("archive_type"), "Temurin JRE archive type is invalid") != "zip":
        msg = "Temurin JRE archive type is invalid"
        raise RuntimeError(msg)

    _require_safe_parent_chain(project_root, worker_path, "Apache worker")
    _require_safe_parent_chain(project_root, jre_path, "Temurin JRE")
    worker_metadata = _require_regular_non_sparse(worker_path, "Apache worker")
    jre_metadata = _require_regular_non_sparse(jre_path, "Temurin JRE")
    if worker_metadata.st_size != worker_size or _hash_file(worker_path) != worker_hash:
        msg = "Apache worker failed its integrity check"
        raise RuntimeError(msg)
    if jre_metadata.st_size != jre_size or _hash_file(jre_path) != jre_hash:
        msg = "Temurin JRE failed its integrity check"
        raise RuntimeError(msg)
    if worker_inputs_sha256(project_root) != source_hash:
        msg = "Apache worker source inputs are stale"
        raise RuntimeError(msg)
    return VendoredWindowsJavaFiles(
        jre_archive=jre_path,
        worker_jar=worker_path,
        java_runtime_version=runtime_version,
        jre_archive_size=jre_size,
        jre_archive_sha256=jre_hash,
        worker_jar_size=worker_size,
        worker_jar_sha256=worker_hash,
    )


def _safe_windows_component(component: str) -> str:
    """Return a Windows-safe canonical member component."""
    if (
        not component
        or component.rstrip(". ") != component
        or any(
            ord(character) < _ASCII_CONTROL_END
            or character in _WINDOWS_INVALID_COMPONENT_CHARACTERS
            for character in component
        )
    ):
        msg = "Temurin JRE archive contains an unsafe member path"
        raise RuntimeError(msg)
    if component.split(".", 1)[0].casefold() in _WINDOWS_RESERVED_NAMES:
        msg = "Temurin JRE archive contains a reserved Windows member path"
        raise RuntimeError(msg)
    return component.casefold()


def _archive_member_path(info: zipfile.ZipInfo) -> tuple[PurePosixPath, bool]:
    """Return one safe, Windows-portable ZIP member path."""
    raw_name = info.orig_filename
    if not raw_name or "\\" in raw_name or "\x00" in raw_name:
        msg = "Temurin JRE archive contains an unsafe member path"
        raise RuntimeError(msg)
    name = info.filename
    is_directory = name.endswith("/")
    if not name or "\\" in name or "\x00" in name:
        msg = "Temurin JRE archive contains an unsafe member path"
        raise RuntimeError(msg)
    trimmed = name[:-1] if is_directory else name
    parts = trimmed.split("/")
    if not trimmed or any(part in ("", ".", "..") or ":" in part for part in parts):
        msg = "Temurin JRE archive contains an unsafe member path"
        raise RuntimeError(msg)
    _ = tuple(_safe_windows_component(part) for part in parts)
    relative = PurePosixPath(*parts)
    if relative.is_absolute() or not relative.parts:
        msg = "Temurin JRE archive contains an unsafe member path"
        raise RuntimeError(msg)
    return relative, is_directory


def _validated_archive_member(
    info: zipfile.ZipInfo,
) -> tuple[PurePosixPath, bool]:
    """Validate the type and path metadata for a single ZIP member."""
    relative, is_directory = _archive_member_path(info)
    mode = info.external_attr >> 16
    file_type = stat.S_IFMT(mode)
    if stat.S_ISLNK(mode):
        msg = "Temurin JRE archive contains a symbolic link"
        raise RuntimeError(msg)
    if info.flag_bits & 0x1:
        msg = "Temurin JRE archive contains an encrypted member"
        raise RuntimeError(msg)
    if is_directory and (info.file_size != 0 or file_type not in (0, stat.S_IFDIR)):
        msg = "Temurin JRE archive contains an invalid directory"
        raise RuntimeError(msg)
    if not is_directory and file_type not in (0, stat.S_IFREG):
        msg = "Temurin JRE archive contains a non-regular member"
        raise RuntimeError(msg)
    return relative, is_directory


def _validated_archive_members(
    archive: zipfile.ZipFile,
) -> list[tuple[zipfile.ZipInfo, PurePosixPath, bool]]:
    """Validate every ZIP member before any filesystem output is created."""
    try:
        members = archive.infolist()
    except (OSError, zipfile.BadZipFile) as error:
        msg = "Temurin JRE archive is unreadable"
        raise RuntimeError(msg) from error
    if len(members) > _MAX_ZIP_ENTRIES:
        msg = "Temurin JRE archive exceeds the member-count budget"
        raise RuntimeError(msg)

    validated: list[tuple[zipfile.ZipInfo, PurePosixPath, bool]] = []
    seen: set[str] = set()
    expanded_bytes = 0
    for info in members:
        relative, is_directory = _validated_archive_member(info)
        member_key = relative.as_posix().casefold()
        if member_key in seen:
            msg = "Temurin JRE archive contains duplicate member paths"
            raise RuntimeError(msg)
        seen.add(member_key)
        expanded_bytes += info.file_size
        if expanded_bytes > _MAX_ZIP_EXPANDED_BYTES:
            msg = "Temurin JRE archive exceeds the expansion budget"
            raise RuntimeError(msg)
        validated.append((info, relative, is_directory))
    return validated


def _archive_member_sha256(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> str:
    """Hash one validated member while checking its declared expanded size."""
    digest = sha256()
    member_bytes = 0
    try:
        with archive.open(info, "r") as stream:
            while chunk := stream.read(_HASH_CHUNK_BYTES):
                member_bytes += len(chunk)
                if member_bytes > info.file_size:
                    msg = "Temurin JRE archive member size is invalid"
                    raise RuntimeError(msg)
                digest.update(chunk)
    except (OSError, zipfile.BadZipFile) as error:
        msg = "Temurin JRE archive member could not be read"
        raise RuntimeError(msg) from error
    if member_bytes != info.file_size:
        msg = "Temurin JRE archive member size is invalid"
        raise RuntimeError(msg)
    return digest.hexdigest()


def _add_cache_parent_directories(path: PurePosixPath, directories: set[str]) -> None:
    parent = path.parent
    while parent != PurePosixPath("."):
        directories.add(parent.as_posix())
        parent = parent.parent


def _archive_cache_inventory(
    archive_path: Path,
) -> tuple[list[dict[str, object]], set[str]]:
    """Derive the expected cache tree directly from the verified JRE ZIP."""
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = _validated_archive_members(archive)
            directories = {"jre"}
            files: list[dict[str, object]] = []
            for info, relative, is_directory in members:
                cache_relative = PurePosixPath("jre", *relative.parts)
                if is_directory:
                    directories.add(cache_relative.as_posix())
                    _add_cache_parent_directories(cache_relative, directories)
                    continue
                _add_cache_parent_directories(cache_relative, directories)
                files.append(
                    {
                        "path": cache_relative.as_posix(),
                        "sha256": _archive_member_sha256(archive, info),
                        "size": info.file_size,
                    }
                )
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as error:
        msg = "Temurin JRE archive is invalid"
        raise RuntimeError(msg) from error
    return sorted(files, key=lambda record: cast("str", record["path"])), directories


def _verified_cache_inventory(
    files: VendoredWindowsJavaFiles,
) -> tuple[list[dict[str, object]], set[str]]:
    """Derive every expected cache byte from verifier-bound input snapshots."""
    expected_files, expected_directories = _archive_cache_inventory(files.jre_archive)
    expected_files.append(
        {
            "path": "worker.jar",
            "sha256": _trusted_artifact_hash(files.worker_jar_sha256, "Apache worker"),
            "size": _trusted_artifact_size(files.worker_jar_size, "Apache worker"),
        }
    )
    return (
        sorted(expected_files, key=lambda record: cast("str", record["path"])),
        expected_directories,
    )


def _require_directory(path: Path, description: str) -> None:
    try:
        metadata = path.lstat()
    except OSError as error:
        msg = f"{description} is missing"
        raise RuntimeError(msg) from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        msg = f"{description} must be a directory"
        raise RuntimeError(msg)


def _ensure_directory(path: Path, description: str) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        msg = f"{description} could not be created"
        raise RuntimeError(msg) from error
    _require_directory(path, description)


def _ensure_safe_directory_chain(path: Path, description: str) -> Path:
    """Create a directory only through a fully non-symlinked ancestor chain."""
    absolute = path.absolute()
    current = Path(absolute.anchor)
    _require_directory(current, description)
    for part in absolute.parts[1:]:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            try:
                current.mkdir()
            except OSError as error:
                msg = f"{description} could not be created"
                raise RuntimeError(msg) from error
            try:
                metadata = current.lstat()
            except OSError as error:
                msg = f"{description} could not be created"
                raise RuntimeError(msg) from error
        except OSError as error:
            msg = f"{description} is unavailable"
            raise RuntimeError(msg) from error
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            msg = f"{description} path is unsafe"
            raise RuntimeError(msg)
    return absolute


def _require_safe_directory_chain(path: Path, description: str) -> None:
    """Require an existing directory chain with no symlinked component."""
    absolute = path.absolute()
    current = Path(absolute.anchor)
    _require_directory(current, description)
    for part in absolute.parts[1:]:
        current /= part
        _require_directory(current, description)


def _extract_windows_jre(archive: Path, destination: Path) -> None:
    """Safely expand the verified Windows JRE ZIP into a new destination."""
    try:
        with zipfile.ZipFile(archive) as package:
            members = _validated_archive_members(package)
            try:
                destination.mkdir(parents=False, exist_ok=False)
            except OSError as error:
                msg = "Temurin JRE extraction destination is unavailable"
                raise RuntimeError(msg) from error
            extracted_bytes = 0
            for info, relative, is_directory in members:
                target = destination.joinpath(*relative.parts)
                try:
                    _ = target.relative_to(destination)
                except ValueError as error:
                    msg = "Temurin JRE archive contains an escaping member path"
                    raise RuntimeError(msg) from error
                if is_directory:
                    _ensure_directory(target, "Temurin JRE archive directory")
                    continue
                _ensure_directory(target.parent, "Temurin JRE archive parent directory")
                try:
                    with package.open(info, "r") as source, target.open("xb") as output:
                        member_bytes = 0
                        while chunk := source.read(_HASH_CHUNK_BYTES):
                            member_bytes += len(chunk)
                            extracted_bytes += len(chunk)
                            if (
                                member_bytes > info.file_size
                                or extracted_bytes > _MAX_ZIP_EXPANDED_BYTES
                            ):
                                msg = "Temurin JRE archive exceeds the expansion budget"
                                raise RuntimeError(msg)
                            _ = output.write(chunk)
                        if member_bytes != info.file_size:
                            msg = "Temurin JRE archive member size is invalid"
                            raise RuntimeError(msg)
                        output.flush()
                        os.fsync(output.fileno())
                except (OSError, zipfile.BadZipFile) as error:
                    msg = "Temurin JRE archive extraction failed"
                    raise RuntimeError(msg) from error
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as error:
        msg = "Temurin JRE archive is invalid"
        raise RuntimeError(msg) from error


def _release_markers(path: Path, expected_version: str) -> None:
    """Require the immutable Temurin Windows JRE release identity markers."""
    metadata = _require_regular_non_sparse(path, "Temurin JRE release file")
    if metadata.st_size > _MAX_RELEASE_BYTES:
        msg = "Temurin JRE release file exceeds its size budget"
        raise RuntimeError(msg)
    try:
        contents = path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        msg = "Temurin JRE release file is invalid"
        raise RuntimeError(msg) from error
    markers: dict[str, str] = {}
    for line in contents.splitlines():
        name, separator, value = line.partition("=")
        if not separator:
            continue
        if not name or not value.startswith('"') or not value.endswith('"'):
            continue
        if name in markers:
            msg = "Temurin JRE release file contains duplicate markers"
            raise RuntimeError(msg)
        markers[name] = value[1:-1]
    expected = {
        "IMPLEMENTOR": "Eclipse Adoptium",
        "JAVA_RUNTIME_VERSION": f"{expected_version}-LTS",
        "OS_ARCH": "x86_64",
        "OS_NAME": "Windows",
        "IMAGE_TYPE": "JRE",
    }
    if any(markers.get(name) != value for name, value in expected.items()):
        msg = "Temurin JRE release markers are invalid"
        raise RuntimeError(msg)


def _require_amd64_pe(path: Path) -> None:
    """Require a regular AMD64 PE image without loading it into memory."""
    metadata = _require_regular_non_sparse(path, "Temurin JRE executable")
    try:
        with path.open("rb") as executable:
            dos_header = executable.read(_DOS_HEADER_BYTES)
            if len(dos_header) != _DOS_HEADER_BYTES or dos_header[:2] != b"MZ":
                msg = "Temurin JRE executable is not a PE image"
                raise RuntimeError(msg)
            pe_offset = int.from_bytes(dos_header[0x3C:0x40], "little")
            if pe_offset > metadata.st_size - 6:
                msg = "Temurin JRE executable has an invalid PE header"
                raise RuntimeError(msg)
            _ = executable.seek(pe_offset)
            pe_header = executable.read(6)
    except OSError as error:
        msg = "Temurin JRE executable is unreadable"
        raise RuntimeError(msg) from error
    if pe_header[:4] != b"PE\0\0" or pe_header[4:6] != b"\x64\x86":
        msg = "Temurin JRE executable is not AMD64"
        raise RuntimeError(msg)


def _safe_regular_file(path: Path, description: str) -> None:
    _ = _require_regular_non_sparse(path, description)


def _find_windows_jre_home(root: Path, expected_version: str) -> Path:
    """Find and statically verify exactly one Windows JRE home."""
    _require_directory(root, "Temurin JRE extraction root")
    candidates: list[Path] = []
    for current, directories, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        for directory in directories:
            _require_directory(current_path / directory, "Temurin JRE directory")
        for filename in files:
            path = current_path / filename
            try:
                metadata = path.lstat()
            except OSError as error:
                msg = "Temurin JRE extraction is unreadable"
                raise RuntimeError(msg) from error
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                msg = "Temurin JRE extraction contains a non-regular file"
                raise RuntimeError(msg)
            if filename == "release":
                candidates.append(current_path)
    if len(candidates) != 1:
        msg = "Temurin JRE archive must contain exactly one JRE home"
        raise RuntimeError(msg)
    java_home = candidates[0]
    _release_markers(java_home / "release", expected_version)
    java = java_home / "bin/java.exe"
    jvm = java_home / "bin/server/jvm.dll"
    _safe_regular_file(java, "Temurin JRE java executable")
    _safe_regular_file(jvm, "Temurin JRE JVM library")
    _require_amd64_pe(java)
    _require_amd64_pe(jvm)
    return java_home


def _cache_fingerprint(files: VendoredWindowsJavaFiles) -> str:
    """Hash every verified materialization input into a cache namespace."""
    digest = sha256()
    for label, size, artifact_hash in (
        (
            "temurin-jre",
            files.jre_archive_size,
            files.jre_archive_sha256,
        ),
        (
            "apache-worker",
            files.worker_jar_size,
            files.worker_jar_sha256,
        ),
    ):
        digest.update(label.encode("ascii"))
        digest.update(b"\0")
        digest.update(str(_trusted_artifact_size(size, label)).encode("ascii"))
        digest.update(b"\0")
        digest.update(_trusted_artifact_hash(artifact_hash, label).encode("ascii"))
        digest.update(b"\0")
    digest.update(files.java_runtime_version.encode("ascii"))
    return digest.hexdigest()


def _trusted_artifact_size(value: int | None, label: str) -> int:
    """Return a verifier-provided artifact size, never a mutable file stat."""
    try:
        return _positive_size(value, f"verified {label} size is invalid")
    except TypeError as error:
        msg = f"verified {label} metadata is unavailable"
        raise RuntimeError(msg) from error


def _trusted_artifact_hash(value: str | None, label: str) -> str:
    """Return a verifier-provided artifact digest, never a mutable file hash."""
    try:
        return _sha256(value, f"verified {label} SHA-256 is invalid")
    except TypeError as error:
        msg = f"verified {label} metadata is unavailable"
        raise RuntimeError(msg) from error


def _snapshot_verified_file(
    source: Path,
    destination: Path,
    *,
    expected_size: int,
    expected_sha256: str,
    description: str,
) -> None:
    """Copy one verifier-bound artifact into a private immutable input snapshot."""
    digest = sha256()
    copied = 0
    try:
        with source.open("rb") as input_stream, destination.open("xb") as output:
            metadata = os.fstat(input_stream.fileno())
            if not stat.S_ISREG(metadata.st_mode):
                msg = f"{description} must be a regular file"
                raise RuntimeError(msg)
            while chunk := input_stream.read(_HASH_CHUNK_BYTES):
                copied += len(chunk)
                if copied > expected_size:
                    msg = f"{description} failed its integrity check"
                    raise RuntimeError(msg)
                digest.update(chunk)
                _ = output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
    except OSError as error:
        msg = f"{description} could not be snapshotted"
        raise RuntimeError(msg) from error
    if copied != expected_size or digest.hexdigest() != expected_sha256:
        msg = f"{description} failed its integrity check"
        raise RuntimeError(msg)


def _snapshot_verified_inputs(
    files: VendoredWindowsJavaFiles,
    snapshot_parent: Path,
) -> VendoredWindowsJavaFiles:
    """Snapshot both artifacts before any later cache or ZIP consumption."""
    jre_size = _trusted_artifact_size(files.jre_archive_size, "Temurin JRE")
    jre_hash = _trusted_artifact_hash(files.jre_archive_sha256, "Temurin JRE")
    worker_size = _trusted_artifact_size(files.worker_jar_size, "Apache worker")
    worker_hash = _trusted_artifact_hash(files.worker_jar_sha256, "Apache worker")
    jre_archive = snapshot_parent / "temurin-jre.zip"
    worker_jar = snapshot_parent / "apache-worker.jar"
    _snapshot_verified_file(
        files.jre_archive,
        jre_archive,
        expected_size=jre_size,
        expected_sha256=jre_hash,
        description="Temurin JRE",
    )
    _snapshot_verified_file(
        files.worker_jar,
        worker_jar,
        expected_size=worker_size,
        expected_sha256=worker_hash,
        description="Apache worker",
    )
    return VendoredWindowsJavaFiles(
        jre_archive=jre_archive,
        worker_jar=worker_jar,
        java_runtime_version=files.java_runtime_version,
        jre_archive_size=jre_size,
        jre_archive_sha256=jre_hash,
        worker_jar_size=worker_size,
        worker_jar_sha256=worker_hash,
    )


def _cache_file_records(
    cache_entry: Path,
    *,
    require_integrity: bool = True,
) -> tuple[list[dict[str, object]], set[str]]:
    """Return a verified regular-file inventory and all actual directories."""
    _require_directory(cache_entry, "Windows Java cache entry")
    try:
        top_level = {child.name for child in cache_entry.iterdir()}
    except OSError as error:
        msg = "Windows Java cache entry is unreadable"
        raise RuntimeError(msg) from error
    expected_top_level = (
        {"integrity.json", "jre", "worker.jar"}
        if require_integrity
        else {"jre", "worker.jar"}
    )
    if top_level != expected_top_level:
        msg = "Windows Java cache entry has unexpected files"
        raise RuntimeError(msg)
    if require_integrity:
        _safe_regular_file(
            cache_entry / "integrity.json", "Windows Java cache integrity"
        )
    root = cache_entry / "jre"
    _require_directory(root, "Windows Java cache JRE")
    directories = {"jre"}
    worker = cache_entry / "worker.jar"
    worker_metadata = _require_regular_non_sparse(worker, "Windows Java cache worker")
    records: list[dict[str, object]] = [
        {
            "path": "worker.jar",
            "sha256": _hash_file(worker),
            "size": worker_metadata.st_size,
        }
    ]
    for current, child_directories, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        current_relative = current_path.relative_to(cache_entry).as_posix()
        directories.add(current_relative)
        for directory in child_directories:
            directory_path = current_path / directory
            _require_directory(directory_path, "Windows Java cache directory")
            directories.add(directory_path.relative_to(cache_entry).as_posix())
        for filename in filenames:
            path = current_path / filename
            metadata = _require_regular_non_sparse(path, "Windows Java cache file")
            records.append(
                {
                    "path": path.relative_to(cache_entry).as_posix(),
                    "sha256": _hash_file(path),
                    "size": metadata.st_size,
                }
            )
    return sorted(records, key=lambda record: cast("str", record["path"])), directories


def _cache_integrity_record(
    cache_entry: Path,
    fingerprint: str,
    java_runtime_version: str,
) -> dict[str, object]:
    records, directories = _cache_file_records(cache_entry, require_integrity=False)
    return {
        "fingerprint": fingerprint,
        "java_runtime_version": java_runtime_version,
        "files": records,
        "directories": sorted(directories),
    }


def _write_cache_integrity(
    cache_entry: Path,
    fingerprint: str,
    java_runtime_version: str,
) -> None:
    """Write and fsync the integrity record before publishing a cache entry."""
    record = _cache_integrity_record(cache_entry, fingerprint, java_runtime_version)
    encoded = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    integrity = cache_entry / "integrity.json"
    try:
        with integrity.open("xb") as output:
            _ = output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
    except OSError as error:
        msg = "Windows Java cache integrity record could not be written"
        raise RuntimeError(msg) from error


def _cache_integrity(path: Path) -> dict[str, object]:
    metadata = _require_regular_non_sparse(path, "Windows Java cache integrity")
    if metadata.st_size > _MAX_INTEGRITY_BYTES:
        msg = "Windows Java cache integrity record exceeds its size budget"
        raise RuntimeError(msg)
    try:
        value = cast("object", json.loads(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        msg = "Windows Java cache integrity record is invalid"
        raise RuntimeError(msg) from error
    record = _mapping(value, "Windows Java cache integrity record is invalid")
    if set(record) != {"directories", "files", "fingerprint", "java_runtime_version"}:
        msg = "Windows Java cache integrity record is invalid"
        raise RuntimeError(msg)
    if _sha256(record.get("fingerprint"), "Windows Java cache fingerprint is invalid"):
        return record
    msg = "Windows Java cache integrity record is invalid"
    raise RuntimeError(msg)


def _integrity_files(record: dict[str, object]) -> list[dict[str, object]]:
    value = record.get("files")
    if not isinstance(value, list):
        msg = "Windows Java cache file inventory is invalid"
        raise TypeError(msg)
    entries = cast("list[object]", value)
    files: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in entries:
        file_record = _mapping(item, "Windows Java cache file inventory is invalid")
        if set(file_record) != {"path", "sha256", "size"}:
            msg = "Windows Java cache file inventory is invalid"
            raise RuntimeError(msg)
        path = _text(file_record.get("path"), "Windows Java cache file path is invalid")
        relative = PurePosixPath(path)
        if (
            relative.is_absolute()
            or not relative.parts
            or (relative != PurePosixPath("worker.jar") and relative.parts[0] != "jre")
            or any(part in ("", ".", "..") or ":" in part for part in relative.parts)
        ):
            msg = "Windows Java cache file path is invalid"
            raise RuntimeError(msg)
        key = relative.as_posix().casefold()
        if key in seen:
            msg = "Windows Java cache file inventory is invalid"
            raise RuntimeError(msg)
        seen.add(key)
        _ = _sha256(
            file_record.get("sha256"), "Windows Java cache file hash is invalid"
        )
        _ = _positive_size(
            file_record.get("size"), "Windows Java cache file size is invalid"
        )
        files.append(file_record)
    return sorted(files, key=lambda item: cast("str", item["path"]))


def _integrity_directories(record: dict[str, object]) -> set[str]:
    value = record.get("directories")
    if not isinstance(value, list):
        msg = "Windows Java cache directory inventory is invalid"
        raise TypeError(msg)
    entries = cast("list[object]", value)
    directories: set[str] = set()
    seen: set[str] = set()
    for entry in entries:
        path = _text(entry, "Windows Java cache directory path is invalid")
        relative = PurePosixPath(path)
        if (
            relative.is_absolute()
            or not relative.parts
            or relative.parts[0] != "jre"
            or any(part in ("", ".", "..") or ":" in part for part in relative.parts)
        ):
            msg = "Windows Java cache directory path is invalid"
            raise RuntimeError(msg)
        key = relative.as_posix().casefold()
        if key in seen:
            msg = "Windows Java cache directory inventory is invalid"
            raise RuntimeError(msg)
        seen.add(key)
        directories.add(relative.as_posix())
    return directories


def _verified_cached_jre(cache: Path, fingerprint: str) -> Path:
    """Verify one cached entry against its full integrity-bound inventory."""
    cache_entry = cache / fingerprint
    record = _cache_integrity(cache_entry / "integrity.json")
    if record.get("fingerprint") != fingerprint:
        msg = "Windows Java cache fingerprint does not match"
        raise RuntimeError(msg)
    version = _text(
        record.get("java_runtime_version"), "Windows Java cache Java version is invalid"
    )
    if version != _EXPECTED_JAVA_RUNTIME_VERSION:
        msg = "Windows Java cache Java version is invalid"
        raise RuntimeError(msg)
    expected_files = _integrity_files(record)
    expected_directories = _integrity_directories(record)
    actual_files, actual_directories = _cache_file_records(cache_entry)
    if actual_files != expected_files:
        msg = "Windows Java cache file inventory does not match"
        raise RuntimeError(msg)
    if actual_directories != expected_directories:
        msg = "Windows Java cache directory inventory does not match"
        raise RuntimeError(msg)
    return _find_windows_jre_home(cache_entry / "jre", version)


def _cached_jre_is_valid(cache: Path, fingerprint: str) -> Path | None:
    """Return a fully verified cached JRE, or reject the whole cache entry."""
    try:
        return _verified_cached_jre(cache, fingerprint)
    except (OSError, TypeError, ValueError, RuntimeError):
        return None


def _cached_jre_matches_verified_archive(
    files: VendoredWindowsJavaFiles,
    cache: Path,
    fingerprint: str,
) -> Path | None:
    """Return a cache hit only when every tree byte derives from the Git ZIP."""
    java_home = _cached_jre_is_valid(cache, fingerprint)
    if java_home is None:
        return None
    try:
        expected_files, expected_directories = _verified_cache_inventory(files)
        actual_files, actual_directories = _cache_file_records(cache / fingerprint)
        if actual_files != expected_files or actual_directories != expected_directories:
            return None
    except (OSError, TypeError, ValueError, RuntimeError):
        return None
    return java_home


def _remove_cache_path(path: Path) -> None:
    """Remove one cache entry without following a top-level symbolic link."""
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return
    except OSError as error:
        msg = "Windows Java cache entry could not be removed"
        raise RuntimeError(msg) from error
    try:
        if stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode):
            shutil.rmtree(path)
        else:
            path.unlink()
    except OSError as error:
        msg = "Windows Java cache entry could not be removed"
        raise RuntimeError(msg) from error


def _publish_cache_entry(staged: Path, target: Path) -> None:
    """Atomically publish a complete verified entry, replacing an invalid one."""
    backup: Path | None = None
    try:
        _ = target.lstat()
    except FileNotFoundError:
        pass
    except OSError as error:
        msg = "Windows Java cache entry is unavailable"
        raise RuntimeError(msg) from error
    else:
        backup = target.with_name(f".{target.name}.stale-{uuid.uuid4().hex}")
        try:
            _ = target.replace(backup)
        except OSError as error:
            msg = "Windows Java cache entry could not be replaced"
            raise RuntimeError(msg) from error
    try:
        _ = staged.replace(target)
    except OSError as error:
        if backup is not None:
            with suppress(OSError):
                _ = backup.replace(target)
        msg = "Windows Java cache entry could not be published"
        raise RuntimeError(msg) from error
    if backup is not None:
        _remove_cache_path(backup)


def _materialize_verified_jre(files: VendoredWindowsJavaFiles, cache: Path) -> Path:
    """Rebuild a cache entry transactionally unless its integrity still holds."""
    cache = _ensure_safe_directory_chain(cache, "Windows Java cache")
    fingerprint = _cache_fingerprint(files)
    try:
        snapshot_parent = Path(tempfile.mkdtemp(prefix=".verified-inputs.", dir=cache))
    except OSError as error:
        msg = "Windows Java input snapshot directory could not be created"
        raise RuntimeError(msg) from error
    try:
        snapshot_files = _snapshot_verified_inputs(files, snapshot_parent)
        cached = _cached_jre_matches_verified_archive(
            snapshot_files, cache, fingerprint
        )
        if cached is None:
            try:
                staging_parent = Path(
                    tempfile.mkdtemp(prefix=f".{fingerprint}.", dir=cache)
                )
            except OSError as error:
                msg = "Windows Java cache staging directory could not be created"
                raise RuntimeError(msg) from error
            staged = staging_parent / fingerprint
            try:
                _ensure_directory(staged, "Windows Java cache staging entry")
                _extract_windows_jre(snapshot_files.jre_archive, staged / "jre")
                _snapshot_verified_file(
                    snapshot_files.worker_jar,
                    staged / "worker.jar",
                    expected_size=_trusted_artifact_size(
                        snapshot_files.worker_jar_size, "Apache worker"
                    ),
                    expected_sha256=_trusted_artifact_hash(
                        snapshot_files.worker_jar_sha256, "Apache worker"
                    ),
                    description="Apache worker",
                )
                _ = _find_windows_jre_home(
                    staged / "jre", snapshot_files.java_runtime_version
                )
                _write_cache_integrity(
                    staged, fingerprint, snapshot_files.java_runtime_version
                )
                if (
                    _cached_jre_matches_verified_archive(
                        snapshot_files, staging_parent, fingerprint
                    )
                    is None
                ):
                    msg = "Windows Java cache staging verification failed"
                    raise RuntimeError(msg)
                _publish_cache_entry(staged, cache / fingerprint)
                cached = _cached_jre_matches_verified_archive(
                    snapshot_files, cache, fingerprint
                )
                if cached is None:
                    msg = "Windows Java cache publication verification failed"
                    raise RuntimeError(msg)
            finally:
                _remove_cache_path(staging_parent)
        return cached
    finally:
        _remove_cache_path(snapshot_parent)


def _is_native_windows() -> bool:
    """Allow native Windows probing without making tests alter process globals."""
    return os.name == "nt"


def _terminate_native_probe(
    process: subprocess.Popen[bytes],
    deadline: float,
) -> None:
    try:
        process.kill()
    except OSError:
        return
    timeout = _remaining_native_probe_seconds(deadline)
    if timeout <= 0:
        return
    try:
        _ = process.wait(timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return


def _start_native_probe(command: tuple[str, str, str]) -> subprocess.Popen[bytes]:
    try:
        process = subprocess.Popen(  # noqa: S603 - statically verified pinned java.exe
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    except OSError as error:
        msg = "Temurin JRE native probe could not start"
        raise RuntimeError(msg) from error
    return process


def _remaining_native_probe_seconds(deadline: float) -> float:
    return max(0.0, deadline - time.monotonic())


def _capture_native_probe_output(
    process: subprocess.Popen[bytes],
    deadline: float,
) -> bytes:
    if process.stdout is None:
        _terminate_native_probe(process, deadline)
        msg = "Temurin JRE native probe could not capture output"
        raise RuntimeError(msg)
    output: list[tuple[bytes, bool]] = []
    read_errors: list[Exception] = []

    def read_output(stream: BinaryIO) -> None:
        try:
            captured = stream.read(_MAX_NATIVE_OUTPUT_BYTES)
            output.append((captured, bool(stream.read(1))))
        except OSError as error:  # pragma: no cover - platform pipe failure
            read_errors.append(error)

    reader = threading.Thread(target=read_output, args=(process.stdout,), daemon=True)
    reader.start()
    reader.join(_remaining_native_probe_seconds(deadline))
    if reader.is_alive():
        _terminate_native_probe(process, deadline)
        reader.join(_remaining_native_probe_seconds(deadline))
        msg = "Temurin JRE native probe timed out"
        raise RuntimeError(msg)
    if read_errors:
        _terminate_native_probe(process, deadline)
        msg = "Temurin JRE native probe output could not be read"
        raise RuntimeError(msg) from read_errors[0]
    captured, exceeded_output_budget = output[0]
    if exceeded_output_budget:
        _terminate_native_probe(process, deadline)
        msg = "Temurin JRE native probe exceeded its output budget"
        raise RuntimeError(msg)
    return captured


def _native_probe_return_code(process: subprocess.Popen[bytes], deadline: float) -> int:
    timeout = _remaining_native_probe_seconds(deadline)
    if timeout <= 0:
        _terminate_native_probe(process, deadline)
        msg = "Temurin JRE native probe timed out"
        raise RuntimeError(msg)
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        _terminate_native_probe(process, deadline)
        msg = "Temurin JRE native probe timed out"
        raise RuntimeError(msg) from error
    except OSError as error:
        msg = "Temurin JRE native probe could not complete"
        raise RuntimeError(msg) from error


def _verify_native_windows_java(java_home: Path, expected_version: str) -> None:
    """Probe the materialized JRE on Windows with bounded time and output."""
    command = (
        str(java_home / "bin/java.exe"),
        "-XshowSettings:properties",
        "-version",
    )
    deadline = time.monotonic() + _NATIVE_PROBE_TIMEOUT_SECONDS
    process = _start_native_probe(command)
    captured = _capture_native_probe_output(process, deadline)
    return_code = _native_probe_return_code(process, deadline)
    if return_code != 0:
        msg = "Temurin JRE native probe failed"
        raise RuntimeError(msg)
    output_text = captured.decode("utf-8", errors="replace")
    if (
        "java.vendor = Eclipse Adoptium" not in output_text
        or f"java.runtime.version = {expected_version}-LTS" not in output_text
    ):
        msg = "Temurin JRE native probe reported the wrong runtime"
        raise RuntimeError(msg)


def prepare_vendored_windows_java(
    project_root: Path,
    cache: Path,
) -> PreparedWindowsJava:
    """Verify, materialize, and (on Windows) execute-probe the vendored JRE."""
    files = verify_vendored_windows_java_files(project_root)
    java_home = _materialize_verified_jre(files, cache)
    if _is_native_windows():
        _verify_native_windows_java(java_home, files.java_runtime_version)
    return PreparedWindowsJava(
        java_home=java_home,
        worker_jar=java_home.parents[1] / "worker.jar",
    )


def _directory_sha256(root: Path) -> str:
    """Hash a prepared directory for the verification CLI's stable output."""
    digest = sha256()
    records, _ = _cache_file_records(root.parent.parent)
    prefix = root.relative_to(root.parent.parent).as_posix()
    for record in records:
        path = cast("str", record["path"])
        if path == prefix or path.startswith(f"{prefix}/"):
            digest.update(path.encode("utf-8"))
            digest.update(b"\0")
            digest.update(cast("str", record["sha256"]).encode("ascii"))
            digest.update(b"\0")
    return digest.hexdigest()


def _repository_relative_path(project_root: Path, path: Path) -> str:
    project_root = project_root.absolute()
    path = path.absolute()
    try:
        relative = path.relative_to(project_root)
    except ValueError as error:
        msg = "verification paths must stay inside the repository"
        raise RuntimeError(msg) from error
    _require_safe_directory_chain(project_root, "verification repository")
    current = project_root
    for part in relative.parts[:-1]:
        current /= part
        _require_directory(current, "verification path")
    try:
        metadata = path.lstat()
    except OSError as error:
        msg = "verification path is unavailable"
        raise RuntimeError(msg) from error
    if stat.S_ISLNK(metadata.st_mode):
        msg = "verification path is unsafe"
        raise RuntimeError(msg)
    return relative.as_posix()


def _cli() -> int:
    parser = argparse.ArgumentParser()
    _ = parser.add_argument("--cache", required=True, type=Path)
    arguments = parser.parse_args()
    project_root = Path(__file__).resolve().parents[1]
    cache_argument = cast("Path", arguments.cache)
    cache = _safe_project_file(project_root, cache_argument.as_posix(), "cache")
    cache = _ensure_safe_directory_chain(cache, "Windows Java cache")
    prepared = prepare_vendored_windows_java(project_root, cache)
    java_home_path = _repository_relative_path(project_root, prepared.java_home)
    worker_jar_path = _repository_relative_path(project_root, prepared.worker_jar)
    _ = sys.stdout.write(
        f"java_home={java_home_path} sha256={_directory_sha256(prepared.java_home)}\n"
    )
    _ = sys.stdout.write(
        f"worker_jar={worker_jar_path} sha256={_hash_file(prepared.worker_jar)}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
