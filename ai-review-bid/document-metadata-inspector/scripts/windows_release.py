"""Assemble the normalized, checksummed Windows x64 release directory."""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import tempfile
import tomllib
import zlib
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Never, cast
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

if TYPE_CHECKING:
    from collections.abc import Generator
    from datetime import datetime
    from typing import BinaryIO

_MAX_CLI_CHECKSUM_BYTES = 256
_MAX_RELEASE_CHECKSUM_BYTES = 4096
_VERSION_TOKEN_PATTERN = re.compile(r"(?=.{1,64}\Z)[A-Za-z0-9]+(?:[._+-][A-Za-z0-9]+)*")


class _InvalidCliArchiveError(Exception):
    pass


def _reject_cli_archive() -> Never:
    raise _InvalidCliArchiveError


@dataclass(frozen=True)
class _Sources:
    setup: Path
    portable: Path
    cli: Path
    core: Path
    core_checksum: Path
    notices: Path
    setup_fingerprint: _FileFingerprint
    portable_fingerprint: _FileFingerprint
    cli_fingerprint: _FileFingerprint
    core_fingerprint: _FileFingerprint
    core_checksum_fingerprint: _FileFingerprint
    notices_fingerprint: _FileFingerprint


@dataclass(frozen=True)
class _Snapshot:
    setup: Path
    portable: Path
    cli: Path
    core: Path
    core_checksum: Path
    notices: Path


@dataclass(frozen=True)
class _SnapshotEvidence:
    core_sha256: str
    core_size: int
    cli_sha256: str
    notices_sha256: str
    notices_size: int


@dataclass(frozen=True)
class _FileFingerprint:
    device: int
    inode: int
    mode: int
    links: int
    size: int
    modified_ns: int
    changed_ns: int
    file_attributes: int | None


def _fingerprint(file_stat: os.stat_result) -> _FileFingerprint:
    return _FileFingerprint(
        device=file_stat.st_dev,
        inode=file_stat.st_ino,
        mode=file_stat.st_mode,
        links=file_stat.st_nlink,
        size=file_stat.st_size,
        modified_ns=file_stat.st_mtime_ns,
        changed_ns=file_stat.st_ctime_ns,
        file_attributes=cast(
            "int | None",
            getattr(file_stat, "st_file_attributes", None),
        ),
    )


def _is_reparse_point(file_stat: os.stat_result) -> bool:
    attributes = cast("int", getattr(file_stat, "st_file_attributes", 0))
    reparse_flag = cast(
        "int",
        getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400),
    )
    return bool(attributes & reparse_flag)


def _regular_file_fingerprint(
    file_stat: os.stat_result,
    description: str,
) -> _FileFingerprint:
    if not stat.S_ISREG(file_stat.st_mode) or _is_reparse_point(file_stat):
        message = f"{description} must remain a safe regular file during snapshot"
        raise RuntimeError(message)
    return _fingerprint(file_stat)


def _path_fingerprint(path: Path, description: str) -> _FileFingerprint:
    try:
        return _regular_file_fingerprint(path.lstat(), description)
    except OSError:
        message = f"{description} must remain a safe regular file during snapshot"
        raise RuntimeError(message) from None


def _reject_changed_file(description: str) -> Never:
    message = f"{description} must remain a safe regular file"
    raise RuntimeError(message)


@contextmanager
def _open_stable_regular_file(
    path: Path,
    description: str,
    expected: _FileFingerprint | None = None,
) -> Generator[tuple[BinaryIO, _FileFingerprint]]:
    before = _path_fingerprint(path, description)
    if expected is not None and before != expected:
        _reject_changed_file(description)
    extra_flags = (
        getattr(os, "O_BINARY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )

    def stable_opener(open_path: str, flags: int) -> int:
        return os.open(open_path, flags | extra_flags)

    try:
        stream = open(  # noqa: SIM115 - isolate open failure before entering context
            path,
            "rb",
            opener=stable_opener,
        )
    except OSError:
        _reject_changed_file(description)
    with stream:
        descriptor = stream.fileno()
        opened = _regular_file_fingerprint(os.fstat(descriptor), description)
        if opened != before or _path_fingerprint(path, description) != before:
            _reject_changed_file(description)
        try:
            yield stream, before
        finally:
            after = _regular_file_fingerprint(
                os.fstat(descriptor),
                description,
            )
            if after != before or _path_fingerprint(path, description) != before:
                _reject_changed_file(description)


def _snapshot_regular_file(
    source: Path,
    destination: Path,
    description: str,
    expected: _FileFingerprint,
) -> None:
    with _open_stable_regular_file(
        source,
        description,
        expected,
    ) as (source_stream, before):
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        destination_descriptor = os.open(destination, flags, 0o600)
        copied = 0
        with os.fdopen(
            destination_descriptor, "wb", closefd=True
        ) as destination_stream:
            while chunk := source_stream.read(1024 * 1024):
                _ = destination_stream.write(chunk)
                copied += len(chunk)
        if copied != before.size:
            _reject_changed_file(description)


def _directory_fingerprint(path: Path, description: str) -> _FileFingerprint:
    try:
        directory_stat = path.lstat()
    except OSError:
        message = f"{description} must remain a safe directory"
        raise RuntimeError(message) from None
    if not stat.S_ISDIR(directory_stat.st_mode) or _is_reparse_point(directory_stat):
        message = f"{description} must remain a safe directory"
        raise RuntimeError(message)
    return _fingerprint(directory_stat)


def _object_identity(fingerprint: _FileFingerprint) -> tuple[int, ...]:
    return (
        fingerprint.device,
        fingerprint.inode,
        stat.S_IFMT(fingerprint.mode),
        fingerprint.links,
        fingerprint.size,
        fingerprint.modified_ns,
    )


def _reject_staged_release() -> Never:
    message = "the staged Windows release checksum is invalid"
    raise RuntimeError(message)


def _direct_inventory_fingerprints(
    directory: Path,
    expected_names: set[str],
) -> tuple[_FileFingerprint, dict[str, _FileFingerprint]]:
    directory_fingerprint = _directory_fingerprint(
        directory,
        "the staged Windows release",
    )
    entries = list(directory.iterdir())
    if {entry.name for entry in entries} != expected_names:
        _reject_staged_release()
    fingerprints = {
        entry.name: _path_fingerprint(
            entry,
            f"the staged Windows release file {entry.name}",
        )
        for entry in entries
    }
    return directory_fingerprint, fingerprints


def _sealed_mode(file_stat: os.stat_result) -> int:
    write_bits = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
    return file_stat.st_mode & ~write_bits


def _is_read_only(file_stat: os.stat_result) -> bool:
    if os.name == "nt":
        attributes = cast("int", getattr(file_stat, "st_file_attributes", 0))
        readonly = cast(
            "int",
            getattr(stat, "FILE_ATTRIBUTE_READONLY", 0x1),
        )
        return bool(attributes & readonly)
    write_bits = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
    return not file_stat.st_mode & write_bits


def _seal_staged_release(staged: Path, expected_names: set[str]) -> None:
    before_directory, before_files = _direct_inventory_fingerprints(
        staged,
        expected_names,
    )
    for name, before in before_files.items():
        path = staged / name
        path.chmod(_sealed_mode(path.lstat()))
        after_stat = path.lstat()
        after = _regular_file_fingerprint(
            after_stat,
            f"the staged Windows release file {name}",
        )
        if _object_identity(after) != _object_identity(before) or not _is_read_only(
            after_stat
        ):
            _reject_staged_release()
    if os.name != "nt":
        staged.chmod(_sealed_mode(staged.lstat()))
    after_directory = _directory_fingerprint(staged, "the staged Windows release")
    if _object_identity(after_directory) != _object_identity(before_directory):
        _reject_staged_release()
    if os.name != "nt" and not _is_read_only(staged.lstat()):
        _reject_staged_release()


def _read_checksum_manifest(
    manifest: Path,
    expected_names: set[str],
) -> dict[str, str]:
    try:
        with _open_stable_regular_file(
            manifest,
            "the staged Windows release checksum manifest",
        ) as (stream, fingerprint):
            if fingerprint.size > _MAX_RELEASE_CHECKSUM_BYTES:
                _reject_staged_release()
            manifest_bytes = stream.read(_MAX_RELEASE_CHECKSUM_BYTES + 1)
            if len(manifest_bytes) != fingerprint.size:
                _reject_staged_release()
        lines = manifest_bytes.decode("utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        _reject_staged_release()
    records: dict[str, str] = {}
    record_names: list[str] = []
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  ([^\r\n]+)", line)
        if match is None or match.group(2) in records:
            _reject_staged_release()
        records[match.group(2)] = match.group(1)
        record_names.append(match.group(2))
    if set(records) != expected_names or record_names != sorted(expected_names):
        _reject_staged_release()
    return records


def _stable_hash(path: Path, description: str) -> str:
    with _open_stable_regular_file(path, description) as (stream, fingerprint):
        digest, size = _hash_stream(stream)
        if size != fingerprint.size:
            _reject_changed_file(description)
    return digest


def _verify_sealed_release(
    staged: Path,
    verification_order: tuple[str, ...],
) -> None:
    covered_names = set(verification_order)
    expected_names = {*covered_names, "SHA256SUMS"}
    before_directory, before_files = _direct_inventory_fingerprints(
        staged,
        expected_names,
    )
    if any(not _is_read_only((staged / name).lstat()) for name in expected_names):
        _reject_staged_release()
    if os.name != "nt" and not _is_read_only(staged.lstat()):
        _reject_staged_release()

    records = _read_checksum_manifest(staged / "SHA256SUMS", covered_names)
    for name in verification_order:
        if (
            _stable_hash(
                staged / name,
                f"the staged Windows release file {name}",
            )
            != records[name]
        ):
            _reject_staged_release()

    after_directory, after_files = _direct_inventory_fingerprints(
        staged,
        expected_names,
    )
    if after_directory != before_directory or after_files != before_files:
        _reject_staged_release()


def _one_regular_file(directory: Path, pattern: str, description: str) -> Path:
    matches = sorted(directory.glob(pattern))
    if len(matches) != 1:
        message = f"{description} must contain exactly one regular file"
        raise RuntimeError(message)
    path = matches[0]
    if path.is_symlink() or not path.is_file():
        message = f"{description} must contain exactly one regular file"
        raise RuntimeError(message)
    return path


def _hash_stream(stream: BinaryIO) -> tuple[str, int]:
    digest = sha256()
    size = 0
    while chunk := stream.read(1024 * 1024):
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def _hash_and_size(path: Path) -> tuple[str, int]:
    with path.open("rb") as stream:
        return _hash_stream(stream)


def _hash(path: Path) -> str:
    return _hash_and_size(path)[0]


def _mapping_value(mapping: object, key: str) -> object:
    if not isinstance(mapping, dict):
        return None
    return cast("dict[object, object]", mapping).get(key)


def _version(mapping: object, *keys: str) -> str | None:
    value = mapping
    for key in keys:
        value = _mapping_value(value, key)
    return (
        value
        if isinstance(value, str)
        and _VERSION_TOKEN_PATTERN.fullmatch(value) is not None
        else None
    )


def _text_version(path: Path) -> str | None:
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) != 1 or _VERSION_TOKEN_PATTERN.fullmatch(lines[0]) is None:
        return None
    return lines[0]


def _reject_unsafe_versions() -> Never:
    message = "release metadata versions must be safe fixed tokens"
    raise RuntimeError(message)


def _load_release_metadata(  # noqa: C901 - explicit fail-closed metadata validation
    project_root: Path,
    git_commit: str,
    built_at_utc: datetime,
) -> dict[str, object]:
    with (project_root / "pyproject.toml").open("rb") as stream:
        pyproject = tomllib.load(stream)
    python_version = _text_version(project_root / ".python-version")
    desktop = cast(
        "object",
        json.loads((project_root / "desktop/package.json").read_text(encoding="utf-8")),
    )
    manifest = cast(
        "object",
        json.loads((project_root / "tools/manifest.json").read_text(encoding="utf-8")),
    )

    product_version = _version(pyproject, "project", "version")
    desktop_version = _version(desktop, "version")
    if product_version is None or desktop_version is None:
        _reject_unsafe_versions()
    if product_version != desktop_version:
        message = "product versions must match"
        raise RuntimeError(message)

    exiftool_version = _version(manifest, "exiftool", "version")
    windows_exiftool_version = _version(manifest, "windows_exiftool", "version")
    if exiftool_version is None or windows_exiftool_version is None:
        _reject_unsafe_versions()
    if exiftool_version != windows_exiftool_version:
        message = "ExifTool versions must match"
        raise RuntimeError(message)

    java_runtime_version = _version(manifest, "apache_worker", "java_runtime_version")
    temurin_jdk_version = _version(manifest, "temurin_jdk", "version")
    if java_runtime_version is None or temurin_jdk_version is None:
        _reject_unsafe_versions()
    if java_runtime_version != temurin_jdk_version:
        message = "Java runtime versions must match"
        raise RuntimeError(message)

    electron_version = _version(desktop, "devDependencies", "electron")
    forge_cli_version = _version(desktop, "devDependencies", "@electron-forge/cli")
    forge_squirrel_version = _version(
        desktop, "devDependencies", "@electron-forge/maker-squirrel"
    )
    forge_zip_version = _version(
        desktop, "devDependencies", "@electron-forge/maker-zip"
    )
    if (
        forge_cli_version is None
        or forge_squirrel_version is None
        or forge_zip_version is None
    ):
        _reject_unsafe_versions()
    if forge_cli_version != forge_squirrel_version or (
        forge_cli_version != forge_zip_version
    ):
        message = "Electron Forge versions must match"
        raise RuntimeError(message)
    if python_version is None or electron_version is None:
        _reject_unsafe_versions()
    if re.fullmatch(r"[0-9a-f]{40}", git_commit) is None:
        message = "Git commit must be a full lowercase SHA"
        raise RuntimeError(message)
    if built_at_utc.tzinfo is None or built_at_utc.utcoffset() != timedelta(0):
        message = "build time must be UTC-aware"
        raise RuntimeError(message)

    serialized_time = built_at_utc.replace(microsecond=0).isoformat()
    if serialized_time.endswith("+00:00"):
        serialized_time = f"{serialized_time[:-6]}Z"
    return {
        "schema_version": "1",
        "product_version": product_version,
        "git_commit": git_commit,
        "target_platform": "windows-x86_64",
        "built_at_utc": serialized_time,
        "versions": {
            "python": python_version,
            "java_runtime": java_runtime_version,
            "exiftool": exiftool_version,
            "electron": electron_version,
            "electron_forge": forge_cli_version,
        },
    }


def _require_regular_file(path: Path, description: str) -> None:
    if path.is_symlink() or not path.is_file():
        message = f"{description} must be a regular file"
        raise RuntimeError(message)


def _cli_core_digest(  # noqa: C901 - explicit fail-closed archive validation
    cli: BinaryIO,
    *,
    external_core_size: int,
    external_notices_sha256: str,
    external_notices_size: int,
) -> str:
    root = "document-metadata-inspector-windows-x86_64"
    core_name = f"{root}/docmeta.exe"
    checksum_name = f"{root}/SHA256SUMS"
    notices_name = f"{root}/THIRD_PARTY_NOTICES.md"
    expected_names = {
        core_name,
        checksum_name,
        notices_name,
    }
    try:
        with ZipFile(cli, "r") as archive:
            members = archive.infolist()
            names = [member.filename for member in members]
            for member in members:
                name = member.filename
                parts = name.split("/")
                unsafe_name = (
                    name.startswith("/")
                    or re.match(r"^[A-Za-z]:", name) is not None
                    or "\\" in name
                    or any(part in {"", ".", ".."} for part in parts)
                )
                mode = member.external_attr >> 16
                file_type = stat.S_IFMT(mode)
                if (
                    unsafe_name
                    or member.is_dir()
                    or file_type not in {0, stat.S_IFREG}
                    or member.flag_bits & 1
                    or member.compress_type != ZIP_DEFLATED
                ):
                    _reject_cli_archive()
            if len(names) != len(expected_names) or set(names) != expected_names:
                _reject_cli_archive()

            core_info = archive.getinfo(core_name)
            notices_info = archive.getinfo(notices_name)
            checksum_info = archive.getinfo(checksum_name)
            if (
                core_info.file_size != external_core_size
                or notices_info.file_size != external_notices_size
                or checksum_info.file_size > _MAX_CLI_CHECKSUM_BYTES
            ):
                _reject_cli_archive()
            checksum_text = archive.read(checksum_info).decode("utf-8")
            checksum_lines = checksum_text.splitlines()
            if len(checksum_lines) != 1:
                _reject_cli_archive()
            match = re.fullmatch(r"([0-9a-f]{64})  docmeta\.exe", checksum_lines[0])
            if match is None:
                _reject_cli_archive()

            digest = sha256()
            with archive.open(core_name, "r") as core_stream:
                while chunk := core_stream.read(1024 * 1024):
                    digest.update(chunk)
            cli_core_sha256 = digest.hexdigest()
            if cli_core_sha256 != match.group(1):
                _reject_cli_archive()

            digest = sha256()
            with archive.open(notices_name, "r") as notices_stream:
                while chunk := notices_stream.read(1024 * 1024):
                    digest.update(chunk)
            if digest.hexdigest() != external_notices_sha256:
                _reject_cli_archive()
    except (
        BadZipFile,
        EOFError,
        _InvalidCliArchiveError,
        NotImplementedError,
        OSError,
        RuntimeError,
        UnicodeDecodeError,
        ValueError,
        zlib.error,
    ):
        message = "the CLI archive is invalid"
        raise RuntimeError(message) from None
    return cli_core_sha256


def _validate_cli_archive(
    cli: BinaryIO,
    *,
    external_core_sha256: str,
    external_core_size: int,
    external_notices_sha256: str,
    external_notices_size: int,
) -> None:
    cli_core_sha256 = _cli_core_digest(
        cli,
        external_core_size=external_core_size,
        external_notices_sha256=external_notices_sha256,
        external_notices_size=external_notices_size,
    )
    if cli_core_sha256 != external_core_sha256:
        message = "CLI archive core does not match the frozen core"
        raise RuntimeError(message)


def _discover_sources(
    project_root: Path,
    forge_output: Path,
    cli_release_directory: Path,
    product_version: str,
) -> _Sources:
    setup = _one_regular_file(
        forge_output / "squirrel.windows" / "x64",
        "*Setup.exe",
        "the Squirrel output",
    )
    portable = _one_regular_file(
        forge_output / "zip" / "win32" / "x64",
        "*.zip",
        "the Windows ZIP output",
    )
    cli = cli_release_directory / "document-metadata-inspector-windows-x86_64.zip"
    core = project_root / "dist/windows-x86_64/onefile/docmeta.exe"
    core_checksum = core.parent / "SHA256SUMS"
    notices = project_root / "THIRD_PARTY_NOTICES.md"

    for path, description in (
        (cli, "the CLI archive"),
        (core, "the frozen core"),
        (core_checksum, "the frozen core checksum"),
        (notices, "the third-party notices"),
    ):
        _require_regular_file(path, description)
    if not setup.name.endswith(f"-{product_version} Setup.exe"):
        message = "Maker output version does not match"
        raise RuntimeError(message)
    if not portable.name.endswith(f"-{product_version}.zip"):
        message = "Maker output version does not match"
        raise RuntimeError(message)

    setup_fingerprint = _path_fingerprint(setup, "the Squirrel output")
    portable_fingerprint = _path_fingerprint(portable, "the Windows ZIP output")
    cli_fingerprint = _path_fingerprint(cli, "the CLI archive")
    core_fingerprint = _path_fingerprint(core, "the frozen core")
    core_checksum_fingerprint = _path_fingerprint(
        core_checksum,
        "the frozen core checksum",
    )
    notices_fingerprint = _path_fingerprint(notices, "the third-party notices")
    return _Sources(
        setup,
        portable,
        cli,
        core,
        core_checksum,
        notices,
        setup_fingerprint,
        portable_fingerprint,
        cli_fingerprint,
        core_fingerprint,
        core_checksum_fingerprint,
        notices_fingerprint,
    )


def _snapshot_sources(
    staged: Path,
    evidence_directory: Path,
    sources: _Sources,
    product_version: str,
) -> _Snapshot:
    staged.mkdir()
    evidence_directory.mkdir()
    snapshot = _Snapshot(
        setup=staged / f"DocumentMetadataInspector-{product_version}-win-x64-Setup.exe",
        portable=staged
        / f"DocumentMetadataInspector-{product_version}-win-x64-Portable.zip",
        cli=staged / f"DocumentMetadataInspector-{product_version}-win-x64-CLI.zip",
        core=evidence_directory / "docmeta.exe",
        core_checksum=evidence_directory / "SHA256SUMS",
        notices=staged / "THIRD_PARTY_NOTICES.md",
    )
    for source, destination, description, expected in (
        (
            sources.setup,
            snapshot.setup,
            "the Squirrel output",
            sources.setup_fingerprint,
        ),
        (
            sources.portable,
            snapshot.portable,
            "the Windows ZIP output",
            sources.portable_fingerprint,
        ),
        (
            sources.cli,
            snapshot.cli,
            "the CLI archive",
            sources.cli_fingerprint,
        ),
        (
            sources.core,
            snapshot.core,
            "the frozen core",
            sources.core_fingerprint,
        ),
        (
            sources.core_checksum,
            snapshot.core_checksum,
            "the frozen core checksum",
            sources.core_checksum_fingerprint,
        ),
        (
            sources.notices,
            snapshot.notices,
            "the third-party notices",
            sources.notices_fingerprint,
        ),
    ):
        _snapshot_regular_file(source, destination, description, expected)
    return snapshot


def _validate_snapshot(snapshot: _Snapshot) -> _SnapshotEvidence:
    core_sha256, core_size = _hash_and_size(snapshot.core)
    expected_checksum = f"{core_sha256}  docmeta.exe"
    try:
        checksum_lines = snapshot.core_checksum.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        message = "the frozen core checksum is invalid"
        raise RuntimeError(message) from None
    if checksum_lines != [expected_checksum]:
        message = "the frozen core checksum is invalid"
        raise RuntimeError(message)

    notices_sha256, notices_size = _hash_and_size(snapshot.notices)
    with _open_stable_regular_file(
        snapshot.cli,
        "the staged CLI archive",
    ) as (cli_stream, cli_fingerprint):
        cli_sha256, cli_size = _hash_stream(cli_stream)
        if cli_size != cli_fingerprint.size:
            _reject_changed_file("the staged CLI archive")
        _ = cli_stream.seek(0)
        _validate_cli_archive(
            cli_stream,
            external_core_sha256=core_sha256,
            external_core_size=core_size,
            external_notices_sha256=notices_sha256,
            external_notices_size=notices_size,
        )
    return _SnapshotEvidence(
        core_sha256=core_sha256,
        core_size=core_size,
        cli_sha256=cli_sha256,
        notices_sha256=notices_sha256,
        notices_size=notices_size,
    )


def _unsafe_cleanup_tree(path: Path) -> Never:
    message = f"cleanup tree contains an unsafe entry: {path}"
    raise OSError(message)


def _collect_cleanup_tree(
    root: Path,
) -> tuple[dict[Path, _FileFingerprint], dict[Path, _FileFingerprint]]:
    files: dict[Path, _FileFingerprint] = {}
    directories: dict[Path, _FileFingerprint] = {}

    def collect(directory: Path) -> None:
        try:
            directory_stat = directory.lstat()
        except OSError:
            _unsafe_cleanup_tree(directory)
        if not stat.S_ISDIR(directory_stat.st_mode) or _is_reparse_point(
            directory_stat
        ):
            _unsafe_cleanup_tree(directory)
        directories[directory] = _fingerprint(directory_stat)
        try:
            entries = list(directory.iterdir())
        except OSError:
            _unsafe_cleanup_tree(directory)
        for entry in entries:
            try:
                entry_stat = entry.lstat()
            except OSError:
                _unsafe_cleanup_tree(entry)
            if _is_reparse_point(entry_stat):
                _unsafe_cleanup_tree(entry)
            if stat.S_ISREG(entry_stat.st_mode):
                files[entry] = _fingerprint(entry_stat)
            elif stat.S_ISDIR(entry_stat.st_mode):
                collect(entry)
            else:
                _unsafe_cleanup_tree(entry)

    collect(root)
    return files, directories


def _restore_owner_write(
    path: Path, before: _FileFingerprint, *, directory: bool
) -> None:
    try:
        current_stat = path.lstat()
    except OSError:
        _unsafe_cleanup_tree(path)
    expected_type = stat.S_IFDIR if directory else stat.S_IFREG
    if (
        stat.S_IFMT(current_stat.st_mode) != expected_type
        or _is_reparse_point(current_stat)
        or _object_identity(_fingerprint(current_stat)) != _object_identity(before)
    ):
        _unsafe_cleanup_tree(path)
    owner_permissions = stat.S_IRUSR | stat.S_IWUSR
    if directory:
        owner_permissions |= stat.S_IXUSR
    writable_mode = current_stat.st_mode | owner_permissions
    if os.chmod in os.supports_follow_symlinks:
        path.chmod(writable_mode, follow_symlinks=False)
    else:
        path.chmod(writable_mode)
    try:
        after_stat = path.lstat()
    except OSError:
        _unsafe_cleanup_tree(path)
    if (
        stat.S_IFMT(after_stat.st_mode) != expected_type
        or _is_reparse_point(after_stat)
        or _object_identity(_fingerprint(after_stat)) != _object_identity(before)
        or not after_stat.st_mode & stat.S_IWUSR
    ):
        _unsafe_cleanup_tree(path)


def _make_cleanup_tree_writable(path: Path) -> None:
    files, directories = _collect_cleanup_tree(path)
    for file_path, fingerprint in files.items():
        _restore_owner_write(file_path, fingerprint, directory=False)
    for directory_path, fingerprint in reversed(directories.items()):
        _restore_owner_write(directory_path, fingerprint, directory=True)


def _cleanup_recovery_directory(path: Path) -> None:
    _make_cleanup_tree_writable(path)
    shutil.rmtree(path)


def _reserve_absent_sibling(parent: Path, prefix: str) -> Path:
    reserved = Path(tempfile.mkdtemp(dir=parent, prefix=prefix))
    reserved.rmdir()
    return reserved


def _publish_directory(  # noqa: C901, PLR0912 - explicit recovery state machine
    staged: Path,
    output: Path,
) -> None:
    failed = _reserve_absent_sibling(
        output.parent,
        f".{output.name}-failed-",
    )
    if output.is_symlink() or (output.exists() and not output.is_dir()):
        message = "the Windows release output must be a safe directory"
        raise RuntimeError(message)

    previous: Path | None = None
    if output.exists():
        previous = _reserve_absent_sibling(
            output.parent,
            f".{output.name}-recovery-",
        )
        _ = output.replace(previous)
    try:
        _ = staged.replace(output)
    except BaseException as publication_error:
        quarantine_error: OSError | None = None
        if output.exists():
            try:
                _ = output.replace(failed)
            except OSError as error:
                quarantine_error = error

        restoration_error: OSError | None = None
        if previous is not None and previous.exists():
            try:
                _ = previous.replace(output)
            except OSError as error:
                restoration_error = error

        failed_cleanup_error: OSError | None = None
        if failed.exists():
            try:
                _cleanup_recovery_directory(failed)
            except OSError as error:
                failed_cleanup_error = error

        if (
            quarantine_error is None
            and restoration_error is None
            and failed_cleanup_error is None
        ):
            raise

        details = [f"publication failure: {publication_error}"]
        if quarantine_error is not None:
            details.append(f"quarantine failure: {quarantine_error}")
        if restoration_error is not None:
            details.append(f"restoration failure: {restoration_error}")
        if failed_cleanup_error is not None:
            details.append(f"failed-output cleanup failure: {failed_cleanup_error}")
        if previous is not None and previous.exists():
            details.append(f"previous release is recoverable at {previous}")
        message = "; ".join(details)
        raise RuntimeError(message) from publication_error

    if previous is not None:
        try:
            _cleanup_recovery_directory(previous)
        except OSError as cleanup_error:
            message = (
                "Windows release publication succeeded, but cleanup is incomplete: "
                f"{cleanup_error}; stale previous-release data is possibly partial "
                f"at {previous}"
            )
            raise RuntimeError(message) from cleanup_error


def _finish_staged_release(
    staged: Path,
    snapshot: _Snapshot,
    evidence: _SnapshotEvidence,
    build_info: dict[str, object],
) -> None:
    _ = (staged / "BUILD-INFO.json").write_text(
        f"{json.dumps(build_info, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )

    checksums = {
        snapshot.setup.name: _hash(snapshot.setup),
        snapshot.portable.name: _hash(snapshot.portable),
        snapshot.cli.name: evidence.cli_sha256,
        snapshot.notices.name: evidence.notices_sha256,
        "BUILD-INFO.json": _hash(staged / "BUILD-INFO.json"),
    }
    _ = (staged / "SHA256SUMS").write_text(
        "".join(
            f"{checksums[filename]}  {filename}\n" for filename in sorted(checksums)
        ),
        encoding="utf-8",
    )
    expected_names = {*checksums, "SHA256SUMS"}
    _seal_staged_release(staged, expected_names)
    _verify_sealed_release(staged, tuple(checksums))


def assemble_windows_release(  # noqa: PLR0913 - stable release assembly interface
    project_root: Path,
    forge_output: Path,
    cli_release_directory: Path,
    output_directory: Path,
    *,
    git_commit: str,
    built_at_utc: datetime,
) -> Path:
    """Assemble and atomically publish the Windows x64 release directory."""
    metadata = _load_release_metadata(project_root, git_commit, built_at_utc)
    product_version = cast("str", metadata["product_version"])
    sources = _discover_sources(
        project_root,
        forge_output,
        cli_release_directory,
        product_version,
    )
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    with (
        tempfile.TemporaryDirectory(
            dir=output_directory.parent,
            prefix=".windows-release-evidence-",
        ) as evidence_temporary_directory,
        tempfile.TemporaryDirectory(
            dir=output_directory.parent,
            prefix=".windows-x64-staged-",
        ) as staged_temporary_directory,
    ):
        evidence_temporary_root = Path(evidence_temporary_directory)
        staged = Path(staged_temporary_directory)
        staged.rmdir()
        snapshot = _snapshot_sources(
            staged,
            evidence_temporary_root / "source-evidence",
            sources,
            product_version,
        )
        evidence = _validate_snapshot(snapshot)
        build_info = {**metadata, "core_sha256": evidence.core_sha256}
        _finish_staged_release(staged, snapshot, evidence, build_info)
        _publish_directory(staged, output_directory)
    return output_directory
