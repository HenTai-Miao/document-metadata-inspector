"""Assemble the normalized, checksummed Windows x64 release directory."""

from __future__ import annotations

import json
import re
import shutil
import stat
import tempfile
import tomllib
import zlib
from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Never, cast
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

if TYPE_CHECKING:
    from datetime import datetime

_MAX_CLI_CHECKSUM_BYTES = 256


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
    core_sha256: str
    core_size: int
    notices_sha256: str
    notices_size: int


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


def _hash_and_size(path: Path) -> tuple[str, int]:
    digest = sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


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
    return value if isinstance(value, str) and value else None


def _load_release_metadata(
    project_root: Path,
    git_commit: str,
    built_at_utc: datetime,
) -> dict[str, object]:
    with (project_root / "pyproject.toml").open("rb") as stream:
        pyproject = tomllib.load(stream)
    python_version = (
        (project_root / ".python-version").read_text(encoding="utf-8").strip()
    )
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
    if product_version is None or product_version != desktop_version:
        message = "product versions must match"
        raise RuntimeError(message)

    exiftool_version = _version(manifest, "exiftool", "version")
    windows_exiftool_version = _version(manifest, "windows_exiftool", "version")
    if exiftool_version is None or exiftool_version != windows_exiftool_version:
        message = "ExifTool versions must match"
        raise RuntimeError(message)

    java_runtime_version = _version(manifest, "apache_worker", "java_runtime_version")
    temurin_jdk_version = _version(manifest, "temurin_jdk", "version")
    if java_runtime_version is None or java_runtime_version != temurin_jdk_version:
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
        or forge_cli_version != forge_squirrel_version
        or forge_cli_version != forge_zip_version
    ):
        message = "Electron Forge versions must match"
        raise RuntimeError(message)
    if not python_version or electron_version is None:
        message = "release component versions must be non-empty strings"
        raise RuntimeError(message)
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
    cli: Path,
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
    cli: Path,
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

    core_sha256, core_size = _hash_and_size(core)
    notices_sha256, notices_size = _hash_and_size(notices)
    expected_checksum = f"{core_sha256}  docmeta.exe"
    try:
        checksum_lines = core_checksum.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        message = "the frozen core checksum is invalid"
        raise RuntimeError(message) from None
    if checksum_lines != [expected_checksum]:
        message = "the frozen core checksum is invalid"
        raise RuntimeError(message)
    return _Sources(
        setup,
        portable,
        cli,
        core,
        core_checksum,
        notices,
        core_sha256,
        core_size,
        notices_sha256,
        notices_size,
    )


def _cleanup_recovery_directory(path: Path) -> None:
    shutil.rmtree(path)


def _publish_directory(  # noqa: C901, PLR0912 - explicit recovery state machine
    staged: Path,
    output: Path,
    temporary_root: Path,
) -> None:
    failed = temporary_root / "failed-windows-x64"
    if output.is_symlink() or (output.exists() and not output.is_dir()):
        message = "the Windows release output must be a safe directory"
        raise RuntimeError(message)

    previous: Path | None = None
    if output.exists():
        previous = Path(
            tempfile.mkdtemp(
                dir=output.parent,
                prefix=f".{output.name}-recovery-",
            )
        )
        previous.rmdir()
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

        if quarantine_error is None and restoration_error is None:
            raise

        details = [f"publication failure: {publication_error}"]
        if quarantine_error is not None:
            details.append(f"quarantine failure: {quarantine_error}")
        if restoration_error is not None:
            details.append(f"restoration failure: {restoration_error}")
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


def _stage_release(
    staged: Path,
    sources: _Sources,
    product_version: str,
    build_info: dict[str, object],
) -> None:
    staged.mkdir()
    normalized_sources = {
        f"DocumentMetadataInspector-{product_version}-win-x64-Setup.exe": (
            sources.setup
        ),
        f"DocumentMetadataInspector-{product_version}-win-x64-Portable.zip": (
            sources.portable
        ),
        f"DocumentMetadataInspector-{product_version}-win-x64-CLI.zip": sources.cli,
        "THIRD_PARTY_NOTICES.md": sources.notices,
    }
    for filename, source in normalized_sources.items():
        _ = shutil.copyfile(source, staged / filename)
    _ = (staged / "BUILD-INFO.json").write_text(
        f"{json.dumps(build_info, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )

    covered_files = sorted(
        (*normalized_sources.keys(), "BUILD-INFO.json"),
    )
    checksums = {filename: _hash(staged / filename) for filename in covered_files}
    _ = (staged / "SHA256SUMS").write_text(
        "".join(f"{checksums[filename]}  {filename}\n" for filename in covered_files),
        encoding="utf-8",
    )
    for filename, expected in checksums.items():
        if _hash(staged / filename) != expected:
            message = "the staged Windows release checksum is invalid"
            raise RuntimeError(message)


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
    _validate_cli_archive(
        sources.cli,
        external_core_sha256=sources.core_sha256,
        external_core_size=sources.core_size,
        external_notices_sha256=sources.notices_sha256,
        external_notices_size=sources.notices_size,
    )
    build_info = {**metadata, "core_sha256": sources.core_sha256}

    output_directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        dir=output_directory.parent,
        prefix=".windows-release-",
    ) as temporary_directory:
        temporary_root = Path(temporary_directory)
        staged = temporary_root / "windows-x64"
        _stage_release(staged, sources, product_version, build_info)
        _publish_directory(staged, output_directory, temporary_root)
    return output_directory
