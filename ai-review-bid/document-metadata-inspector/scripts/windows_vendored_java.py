"""Validate pinned Windows Java artifacts before they enter a release build."""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import cast

_HASH_CHUNK_BYTES = 1024 * 1024
_TARGET_KEY = "windows-x86_64"
_EXPECTED_BUILD_COMMAND = (
    "mvnw",
    "--batch-mode",
    "--no-transfer-progress",
    "verify",
)
_EXPECTED_JAVA_RUNTIME_VERSION = "21.0.12+8"
_SHA256_LENGTH = 64
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
        try:
            metadata = path.lstat()
        except OSError as error:
            msg = "Apache worker source input is missing"
            raise RuntimeError(msg) from error
        if stat.S_ISLNK(metadata.st_mode):
            msg = "Apache worker source input contains a symbolic link"
            raise RuntimeError(msg)
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
    worker_size = _positive_size(worker.get("size"), "Apache worker size is invalid")
    jre_size = _positive_size(jre.get("size"), "Temurin JRE size is invalid")
    worker_hash = _sha256(worker.get("sha256"), "Apache worker SHA-256 is invalid")
    jre_hash = _sha256(jre.get("sha256"), "Temurin JRE SHA-256 is invalid")
    source_hash = _sha256(
        worker.get("source_tree_sha256"), "Apache worker source hash is invalid"
    )
    _ = _text(
        worker.get("artifact_version"), "Apache worker artifact version is invalid"
    )
    runtime_version = _text(
        worker.get("build_java_runtime_version"),
        "Apache worker Java version is invalid",
    )
    if runtime_version != _EXPECTED_JAVA_RUNTIME_VERSION:
        msg = "Apache worker Java version is invalid"
        raise RuntimeError(msg)
    _ = _build_command(worker.get("build_command"))
    _ = _text(jre.get("url"), "Temurin JRE URL is invalid")
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
    return VendoredWindowsJavaFiles(jre_path, worker_path, runtime_version)
