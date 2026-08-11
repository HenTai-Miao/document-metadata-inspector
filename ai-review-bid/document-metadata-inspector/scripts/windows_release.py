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
from typing import TYPE_CHECKING, Never, Protocol, cast
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

if TYPE_CHECKING:
    from collections.abc import Generator
    from datetime import datetime
    from typing import BinaryIO

_MAX_CLI_CHECKSUM_BYTES = 256
_MAX_RELEASE_CHECKSUM_BYTES = 4096
_PRIVATE_DIRECTORY_MODE = 0o700
_VERSION_TOKEN_PATTERN = re.compile(r"(?=.{1,64}\Z)[A-Za-z0-9]+(?:[._+-][A-Za-z0-9]+)*")


class _InvalidCliArchiveError(Exception):
    pass


class _CreateFileW(Protocol):
    argtypes: tuple[object, ...]
    restype: object

    def __call__(  # noqa: PLR0913, PLR0917 - mirrors the Win32 API
        self,
        file_name: str,
        desired_access: int,
        share_mode: int,
        security_attributes: object | None,
        creation_disposition: int,
        flags_and_attributes: int,
        template_file: object | None,
    ) -> int | None: ...


class _CloseHandle(Protocol):
    argtypes: tuple[object, ...]
    restype: object

    def __call__(self, handle: int) -> int: ...


def _reject_cli_archive() -> Never:
    raise _InvalidCliArchiveError


@dataclass(frozen=True)
class _StableSource:
    path: Path
    fingerprint: _FileFingerprint
    description: str


@dataclass(frozen=True)
class _Sources:
    setup: _StableSource
    portable: _StableSource
    cli: _StableSource
    core: _StableSource
    core_checksum: _StableSource
    notices: _StableSource


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
    cli_sha256: str
    notices_sha256: str


@dataclass(frozen=True)
class _PublicationEvidence:
    directory_identity: tuple[int, ...]
    inventory: tuple[str, ...]
    manifest_records: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class _PreviousRelease:
    path: Path
    directory_identity: tuple[int, ...]


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


def _opened_file_fingerprint_matches_path(
    path_fingerprint: _FileFingerprint,
    opened_fingerprint: _FileFingerprint,
    *,
    platform_name: str = os.name,
) -> bool:
    if platform_name != "nt":
        return opened_fingerprint == path_fingerprint
    return (
        opened_fingerprint.device == path_fingerprint.device
        and opened_fingerprint.inode == path_fingerprint.inode
        and stat.S_IFMT(opened_fingerprint.mode) == stat.S_IFMT(path_fingerprint.mode)
        and opened_fingerprint.links == path_fingerprint.links
        and opened_fingerprint.size == path_fingerprint.size
        and opened_fingerprint.modified_ns == path_fingerprint.modified_ns
        and opened_fingerprint.file_attributes == path_fingerprint.file_attributes
    )


def _open_windows_read_descriptor(path: Path) -> int:
    import ctypes  # noqa: PLC0415 - imported only on native Windows
    import msvcrt  # noqa: PLC0415 - unavailable on non-Windows hosts
    from ctypes import wintypes  # noqa: PLC0415 - imported only on native Windows

    generic_read = 0x80000000
    file_share_read = 0x00000001
    open_existing = 3
    file_flag_open_reparse_point = 0x00200000
    file_flag_sequential_scan = 0x08000000
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = cast("_CreateFileW", cast("object", kernel32.CreateFileW))
    create_file.argtypes = (
        ctypes.c_wchar_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    close_handle = cast("_CloseHandle", cast("object", kernel32.CloseHandle))
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL

    handle = create_file(
        str(path.absolute()),
        generic_read,
        file_share_read,
        None,
        open_existing,
        file_flag_open_reparse_point | file_flag_sequential_scan,
        None,
    )
    invalid_handle = cast("int", ctypes.c_void_p(-1).value)
    if handle is None or handle == invalid_handle:
        error_code = ctypes.get_last_error()
        message = "CreateFileW could not open the source for stable reading"
        raise OSError(error_code, message, path)
    try:
        return msvcrt.open_osfhandle(
            handle,
            os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOINHERIT", 0),
        )
    except BaseException:
        _ = close_handle(handle)
        raise


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
        if os.name == "nt":
            return _open_windows_read_descriptor(Path(open_path))
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
        if (
            not _opened_file_fingerprint_matches_path(before, opened)
            or _path_fingerprint(path, description) != before
        ):
            _reject_changed_file(description)
        try:
            yield stream, before
        finally:
            after = _regular_file_fingerprint(
                os.fstat(descriptor),
                description,
            )
            if (
                not _opened_file_fingerprint_matches_path(before, after)
                or _path_fingerprint(path, description) != before
            ):
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
        source_digest, source_size = _hash_stream(source_stream)
        if source_size != before.size:
            _reject_changed_file(description)
        _ = source_stream.seek(0)
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        destination_descriptor = os.open(destination, flags, 0o600)
        copied = 0
        copied_digest = sha256()
        with os.fdopen(
            destination_descriptor, "wb", closefd=True
        ) as destination_stream:
            while chunk := source_stream.read(1024 * 1024):
                _ = destination_stream.write(chunk)
                copied_digest.update(chunk)
                copied += len(chunk)
        if (
            copied != source_size
            or copied_digest.hexdigest() != source_digest
            or copied != before.size
        ):
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
    )


def _reject_staged_release() -> Never:
    message = "the staged Windows release checksum is invalid"
    raise RuntimeError(message)


def _reject_published_release() -> Never:
    message = "the published Windows release does not match sealed publication evidence"
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
    expected_manifest_records: tuple[tuple[str, str], ...],
) -> None:
    expected_records = dict(expected_manifest_records)
    covered_names = set(expected_records)
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
    if records != expected_records:
        _reject_staged_release()
    for name, expected_digest in expected_manifest_records:
        if (
            _stable_hash(
                staged / name,
                f"the staged Windows release file {name}",
            )
            != expected_digest
        ):
            _reject_staged_release()

    after_directory, after_files = _direct_inventory_fingerprints(
        staged,
        expected_names,
    )
    if after_directory != before_directory or after_files != before_files:
        _reject_staged_release()


def _verify_published_release(
    output: Path,
    evidence: _PublicationEvidence,
) -> None:
    try:
        if (
            _object_identity(
                _directory_fingerprint(output, "the published Windows release")
            )
            != evidence.directory_identity
        ):
            _reject_published_release()
        expected_inventory = tuple(
            sorted({name for name, _ in evidence.manifest_records} | {"SHA256SUMS"})
        )
        if evidence.inventory != expected_inventory:
            _reject_published_release()
        _verify_sealed_release(output, evidence.manifest_records)
        if (
            _object_identity(
                _directory_fingerprint(output, "the published Windows release")
            )
            != evidence.directory_identity
        ):
            _reject_published_release()
    except (OSError, RuntimeError):
        _reject_published_release()


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

    return _Sources(
        setup=_StableSource(
            setup,
            _path_fingerprint(setup, "the Squirrel output"),
            "the Squirrel output",
        ),
        portable=_StableSource(
            portable,
            _path_fingerprint(portable, "the Windows ZIP output"),
            "the Windows ZIP output",
        ),
        cli=_StableSource(
            cli,
            _path_fingerprint(cli, "the CLI archive"),
            "the CLI archive",
        ),
        core=_StableSource(
            core,
            _path_fingerprint(core, "the frozen core"),
            "the frozen core",
        ),
        core_checksum=_StableSource(
            core_checksum,
            _path_fingerprint(core_checksum, "the frozen core checksum"),
            "the frozen core checksum",
        ),
        notices=_StableSource(
            notices,
            _path_fingerprint(notices, "the third-party notices"),
            "the third-party notices",
        ),
    )


def _require_private_empty_staging_directory(staged: Path) -> None:
    message = "the staged Windows release must be a safe private empty directory"
    try:
        fingerprint = _directory_fingerprint(staged, "the staged Windows release")
        entries = list(staged.iterdir())
    except (OSError, RuntimeError):
        raise RuntimeError(message) from None
    if entries or (
        os.name != "nt" and stat.S_IMODE(fingerprint.mode) != _PRIVATE_DIRECTORY_MODE
    ):
        raise RuntimeError(message)


def _snapshot_sources(
    staged: Path,
    evidence_directory: Path,
    sources: _Sources,
    product_version: str,
) -> _Snapshot:
    _require_private_empty_staging_directory(staged)
    try:
        evidence_directory.mkdir(mode=_PRIVATE_DIRECTORY_MODE)
    except OSError:
        message = "the source evidence directory must be fresh and private"
        raise RuntimeError(message) from None
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
            sources.setup.path,
            snapshot.setup,
            sources.setup.description,
            sources.setup.fingerprint,
        ),
        (
            sources.portable.path,
            snapshot.portable,
            sources.portable.description,
            sources.portable.fingerprint,
        ),
        (
            sources.cli.path,
            snapshot.cli,
            sources.cli.description,
            sources.cli.fingerprint,
        ),
        (
            sources.core.path,
            snapshot.core,
            sources.core.description,
            sources.core.fingerprint,
        ),
        (
            sources.core_checksum.path,
            snapshot.core_checksum,
            sources.core_checksum.description,
            sources.core_checksum.fingerprint,
        ),
        (
            sources.notices.path,
            snapshot.notices,
            sources.notices.description,
            sources.notices.fingerprint,
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
        cli_sha256=cli_sha256,
        notices_sha256=notices_sha256,
    )


def _unsafe_cleanup_tree(path: Path) -> Never:
    message = f"cleanup tree contains an unsafe entry: {path}"
    raise OSError(message)


def _cleanup_directory_contents(
    directory: Path,
) -> tuple[_FileFingerprint, list[Path]]:
    try:
        directory_stat = directory.lstat()
    except OSError:
        _unsafe_cleanup_tree(directory)
    if not stat.S_ISDIR(directory_stat.st_mode) or _is_reparse_point(directory_stat):
        _unsafe_cleanup_tree(directory)
    try:
        entries = list(directory.iterdir())
    except OSError:
        _unsafe_cleanup_tree(directory)
    return _fingerprint(directory_stat), entries


def _cleanup_entry_stat(entry: Path) -> os.stat_result:
    try:
        entry_stat = entry.lstat()
    except OSError:
        _unsafe_cleanup_tree(entry)
    if _is_reparse_point(entry_stat):
        _unsafe_cleanup_tree(entry)
    return entry_stat


def _collect_cleanup_tree(
    root: Path,
) -> tuple[dict[Path, _FileFingerprint], dict[Path, _FileFingerprint]]:
    files: dict[Path, _FileFingerprint] = {}
    directories: dict[Path, _FileFingerprint] = {}
    pending = [root]
    while pending:
        directory = pending.pop()
        directory_fingerprint, entries = _cleanup_directory_contents(directory)
        directories[directory] = directory_fingerprint
        for entry in entries:
            entry_stat = _cleanup_entry_stat(entry)
            if stat.S_ISREG(entry_stat.st_mode):
                if entry_stat.st_nlink != 1:
                    _unsafe_cleanup_tree(entry)
                files[entry] = _fingerprint(entry_stat)
            elif stat.S_ISDIR(entry_stat.st_mode):
                pending.append(entry)
            else:
                _unsafe_cleanup_tree(entry)
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


def _path_present(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _directory_matches_identity(path: Path, expected: tuple[int, ...]) -> bool:
    try:
        actual = _object_identity(_directory_fingerprint(path, "the release directory"))
    except RuntimeError:
        return False
    return actual == expected


def _move_previous_release(output: Path) -> _PreviousRelease | None:
    if not output.exists():
        return None
    previous = _PreviousRelease(
        path=_reserve_absent_sibling(
            output.parent,
            f".{output.name}-recovery-",
        ),
        directory_identity=_object_identity(
            _directory_fingerprint(output, "the previous Windows release")
        ),
    )
    try:
        _ = output.replace(previous.path)
    except BaseException as old_rename_error:
        restoration_error: OSError | None = None
        if _directory_matches_identity(previous.path, previous.directory_identity):
            try:
                _ = previous.path.replace(output)
            except OSError as error:
                restoration_error = error
        restored = _directory_matches_identity(
            output, previous.directory_identity
        ) and not _path_present(previous.path)
        if restored:
            raise
        details = [f"old-output rename failure: {old_rename_error}"]
        if restoration_error is not None:
            details.append(f"restoration failure: {restoration_error}")
        else:
            details.append("old-output state is ambiguous after rename failure")
        if _directory_matches_identity(previous.path, previous.directory_identity):
            details.append(f"previous release is recoverable at {previous.path}")
        message = "; ".join(details)
        raise RuntimeError(message) from old_rename_error
    if not _directory_matches_identity(
        previous.path, previous.directory_identity
    ) or _path_present(output):
        details = ["old-output rename left an ambiguous state"]
        if _directory_matches_identity(previous.path, previous.directory_identity):
            details.append(f"previous release is recoverable at {previous.path}")
        raise RuntimeError("; ".join(details))
    return previous


def _attempt_failed_output_quarantine(
    output: Path, failed: Path
) -> BaseException | None:
    if not _path_present(output):
        return None
    try:
        output_identity = _object_identity(
            _directory_fingerprint(output, "the failed Windows release")
        )
    except RuntimeError:
        output_identity = None
    try:
        _ = output.replace(failed)
    except BaseException as error:  # noqa: BLE001 - recovery must inspect final state
        if (
            output_identity is not None
            and _directory_matches_identity(failed, output_identity)
            and not _path_present(output)
        ):
            return None
        return error
    if (
        output_identity is None
        or not _directory_matches_identity(failed, output_identity)
        or _path_present(output)
    ):
        return OSError("failed-output quarantine state is ambiguous")
    return None


def _attempt_previous_release_restoration(
    previous: _PreviousRelease,
    output: Path,
) -> BaseException | None:
    if not _path_present(previous.path):
        if _directory_matches_identity(output, previous.directory_identity):
            return None
        return OSError("the previous-release recovery path is missing")
    try:
        _ = previous.path.replace(output)
    except BaseException as error:  # noqa: BLE001 - recovery must inspect final state
        if _directory_matches_identity(
            output, previous.directory_identity
        ) and not _path_present(previous.path):
            return None
        return error
    if _directory_matches_identity(
        output, previous.directory_identity
    ) and not _path_present(previous.path):
        return None
    return OSError("previous-release restoration state is ambiguous")


def _recover_failed_publication(
    output: Path,
    failed: Path,
    previous: _PreviousRelease | None,
    publication_error: BaseException,
) -> Never:
    quarantine_error = _attempt_failed_output_quarantine(output, failed)
    restoration_error = (
        _attempt_previous_release_restoration(previous, output)
        if previous is not None
        else None
    )
    failed_cleanup_error: OSError | None = None
    if _path_present(failed):
        try:
            _cleanup_recovery_directory(failed)
        except OSError as error:
            failed_cleanup_error = error

    if (
        quarantine_error is None
        and restoration_error is None
        and failed_cleanup_error is None
    ):
        raise publication_error

    details = [f"publication failure: {publication_error}"]
    if quarantine_error is not None:
        details.append(f"quarantine failure: {quarantine_error}")
    if restoration_error is not None:
        details.append(f"restoration failure: {restoration_error}")
    if failed_cleanup_error is not None:
        details.append(f"failed-output cleanup failure: {failed_cleanup_error}")
    if previous is not None and _directory_matches_identity(
        previous.path, previous.directory_identity
    ):
        details.append(f"previous release is recoverable at {previous.path}")
    message = "; ".join(details)
    raise RuntimeError(message) from publication_error


def _cleanup_previous_release(previous: _PreviousRelease) -> None:
    try:
        _cleanup_recovery_directory(previous.path)
    except OSError as cleanup_error:
        message = (
            "Windows release publication succeeded, but cleanup is incomplete: "
            f"{cleanup_error}; stale previous-release data is possibly partial "
            f"at {previous.path}"
        )
        raise RuntimeError(message) from cleanup_error


def _publish_directory(
    staged: Path,
    output: Path,
    evidence: _PublicationEvidence,
) -> None:
    if output.is_symlink() or (output.exists() and not output.is_dir()):
        message = "the Windows release output must be a safe directory"
        raise RuntimeError(message)
    failed = _reserve_absent_sibling(output.parent, f".{output.name}-failed-")
    previous = _move_previous_release(output)
    try:
        _ = staged.replace(output)
        _verify_published_release(output, evidence)
    except BaseException as publication_error:  # noqa: BLE001 - rollback boundary
        _recover_failed_publication(output, failed, previous, publication_error)
    if previous is not None:
        _cleanup_previous_release(previous)


def _finish_staged_release(
    staged: Path,
    snapshot: _Snapshot,
    evidence: _SnapshotEvidence,
    build_info: dict[str, object],
) -> _PublicationEvidence:
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
    manifest_records = tuple(checksums.items())
    _seal_staged_release(staged, expected_names)
    _verify_sealed_release(staged, manifest_records)
    return _PublicationEvidence(
        directory_identity=_object_identity(
            _directory_fingerprint(staged, "the staged Windows release")
        ),
        inventory=tuple(sorted(expected_names)),
        manifest_records=manifest_records,
    )


def _cleanup_temporary_directories(
    temporaries: list[tempfile.TemporaryDirectory[str]],
) -> list[tuple[Path, BaseException]]:
    errors: list[tuple[Path, BaseException]] = []
    for temporary in reversed(temporaries):
        path = Path(temporary.name)
        try:
            temporary.cleanup()
        except BaseException as error:  # noqa: BLE001 - preserve the primary error
            errors.append((path, error))
    return errors


def _add_cleanup_notes(
    primary_error: BaseException,
    cleanup_errors: list[tuple[Path, BaseException]],
) -> None:
    for path, cleanup_error in cleanup_errors:
        primary_error.add_note(f"temporary cleanup failure at {path}: {cleanup_error}")


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
    temporaries: list[tempfile.TemporaryDirectory[str]] = []
    try:
        evidence_temporary = tempfile.TemporaryDirectory(
            dir=output_directory.parent,
            prefix=".windows-release-evidence-",
        )
        temporaries.append(evidence_temporary)
        staged_temporary = tempfile.TemporaryDirectory(
            dir=output_directory.parent,
            prefix=".windows-x64-staged-",
        )
        temporaries.append(staged_temporary)
        evidence_temporary_root = Path(evidence_temporary.name)
        staged = Path(staged_temporary.name)
        snapshot = _snapshot_sources(
            staged,
            evidence_temporary_root / "source-evidence",
            sources,
            product_version,
        )
        evidence = _validate_snapshot(snapshot)
        build_info = {**metadata, "core_sha256": evidence.core_sha256}
        publication = _finish_staged_release(staged, snapshot, evidence, build_info)
        _publish_directory(staged, output_directory, publication)
    except BaseException as primary_error:
        _add_cleanup_notes(
            primary_error,
            _cleanup_temporary_directories(temporaries),
        )
        raise

    cleanup_errors = _cleanup_temporary_directories(temporaries)
    if cleanup_errors:
        paths = ", ".join(str(path) for path, _ in cleanup_errors)
        details = "; ".join(
            f"{path}: {cleanup_error}" for path, cleanup_error in cleanup_errors
        )
        message = (
            "Windows release publication succeeded, but cleanup is incomplete: "
            f"{details}; stale temporary data may remain at: {paths}"
        )
        raise RuntimeError(message) from cleanup_errors[0][1]
    return output_directory
