"""Cross-package one self-contained Windows x64 desktop release on macOS."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import stat
import subprocess
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Protocol, cast
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

if TYPE_CHECKING:
    from collections.abc import Sequence

if __package__:
    from scripts.windows_embedded_runtime import (
        build_windows_embedded_runtime,
        verify_runtime_inventory,
    )
else:
    from windows_embedded_runtime import (  # pyright: ignore[reportImplicitRelativeImport]
        build_windows_embedded_runtime,
        verify_runtime_inventory,
    )

_AMD64_MACHINE = 0x8664
_MAX_PE_HEADER_BYTES = 1024 * 1024
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_MIN_PE_OFFSET = 0x40
_PE_SUFFIXES = frozenset({".dll", ".exe", ".node", ".pyd"})
_HASH_CHUNK_BYTES = 1024 * 1024
_VERSION_PATTERN = re.compile(r"^[0-9]+(?:\.[0-9]+){2}$")


class _Arguments(Protocol):
    output_directory: Path
    cache: Path
    makensis: Path | None


def _hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _mapping(value: object, message: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError(message)
    return cast("dict[str, object]", value)


def _read_json_mapping(path: Path, description: str) -> dict[str, object]:
    try:
        value = cast("object", json.loads(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        msg = f"{description} is invalid"
        raise RuntimeError(msg) from error
    return _mapping(value, f"{description} is invalid")


def _require_regular(path: Path, description: str) -> None:
    try:
        metadata = path.lstat()
    except OSError as error:
        msg = f"{description} is missing"
        raise RuntimeError(msg) from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        msg = f"{description} must be a regular file"
        raise RuntimeError(msg)


def _require_tree(root: Path, description: str) -> None:
    try:
        metadata = root.lstat()
    except OSError as error:
        msg = f"{description} is missing"
        raise RuntimeError(msg) from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        msg = f"{description} must be a regular directory"
        raise RuntimeError(msg)
    for path in root.rglob("*"):
        child = path.lstat()
        if stat.S_ISLNK(child.st_mode):
            msg = f"{description} contains a symbolic link"
            raise RuntimeError(msg)
        if not (stat.S_ISDIR(child.st_mode) or stat.S_ISREG(child.st_mode)):
            msg = f"{description} contains a non-regular entry"
            raise RuntimeError(msg)


def require_amd64_pe(path: Path) -> None:
    """Require one regular PE file whose COFF machine is AMD64."""
    _require_regular(path, "the Windows executable")
    with path.open("rb") as stream:
        header = stream.read(_MAX_PE_HEADER_BYTES)
    if len(header) < _MIN_PE_OFFSET or header[0:2] != b"MZ":
        msg = "the Windows executable is not an AMD64 PE file"
        raise RuntimeError(msg)
    pe_offset = int.from_bytes(header[0x3C:0x40], "little")
    if (
        pe_offset < _MIN_PE_OFFSET
        or pe_offset + 6 > len(header)
        or header[pe_offset : pe_offset + 4] != b"PE\0\0"
    ):
        msg = "the Windows executable is not an AMD64 PE file"
        raise RuntimeError(msg)
    machine = int.from_bytes(header[pe_offset + 4 : pe_offset + 6], "little")
    if machine != _AMD64_MACHINE:
        msg = "the Windows executable is not AMD64"
        raise RuntimeError(msg)


def verify_packaged_windows_application(application: Path) -> int:
    """Verify complete embedded resources and every shipped PE machine type."""
    _require_tree(application, "the packaged Windows application")
    runtime = application / "resources/docmeta-runtime"
    _ = verify_runtime_inventory(runtime)
    required = (
        application / "docmeta-review.exe",
        runtime / "python.exe",
        runtime / "python312.dll",
        runtime / "app/src/document_metadata_inspector/cli.py",
        runtime / "app/tools/manifest.json",
        runtime / "app/tools/packaged/windows-x86_64/apache/jdk/bin/java.exe",
        runtime / "app/tools/packaged/windows-x86_64/apache/worker.jar",
        runtime / "app/tools/packaged/windows-x86_64/exiftool/exiftool.exe",
    )
    for path in required:
        _require_regular(path, "a required packaged Windows application file")
    binaries = sorted(
        (
            path
            for path in application.rglob("*")
            if path.is_file() and path.suffix.casefold() in _PE_SUFFIXES
        ),
        key=lambda path: path.relative_to(application).as_posix(),
    )
    if not binaries:
        msg = "the packaged Windows application contains no AMD64 binaries"
        raise RuntimeError(msg)
    for binary in binaries:
        require_amd64_pe(binary)
    return len(binaries)


def create_portable_zip(
    application: Path,
    archive: Path,
    top_level_name: str,
) -> Path:
    """Create a deterministic ZIP containing one complete application tree."""
    _require_tree(application, "the packaged Windows application")
    if not top_level_name or any(character in top_level_name for character in "/\\"):
        msg = "the portable application name is invalid"
        raise ValueError(msg)
    if archive.exists():
        msg = "the portable archive already exists"
        raise FileExistsError(msg)
    archive.parent.mkdir(parents=True, exist_ok=True)
    files = sorted(
        (path for path in application.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(application).as_posix(),
    )
    if not files:
        msg = "the packaged Windows application is empty"
        raise RuntimeError(msg)
    with ZipFile(archive, "x", ZIP_DEFLATED, compresslevel=9) as package:
        for path in files:
            relative = path.relative_to(application).as_posix()
            info = ZipInfo(f"{top_level_name}/{relative}", _ZIP_TIMESTAMP)
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            package.writestr(info, path.read_bytes(), compresslevel=9)
    return archive


def compile_windows_installer(
    application: Path,
    output: Path,
    script: Path,
    icon: Path,
    *,
    makensis: Path,
) -> Path:
    """Compile an NSIS installer around the exact prebuilt application tree."""
    _require_tree(application, "the packaged Windows application")
    _require_regular(script, "the NSIS installer script")
    _require_regular(icon, "the Windows application icon")
    _require_regular(makensis, "the NSIS compiler")
    if output.exists():
        msg = "the Windows installer output already exists"
        raise FileExistsError(msg)
    output.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(  # noqa: S603
        (
            str(makensis),
            "-V3",
            f"-DAPP_SOURCE={application}",
            f"-DOUTPUT_FILE={output}",
            f"-DICON_FILE={icon}",
            "-DPRODUCT_VERSION=0.1.0.0",
            "-DPRODUCT_DISPLAY_VERSION=0.1.0",
            str(script),
        ),
        cwd=script.parent,
        check=False,
        timeout=600,
    )
    if result.returncode != 0 or not output.is_file() or output.stat().st_size == 0:
        output.unlink(missing_ok=True)
        msg = "the Windows NSIS installer build failed"
        raise RuntimeError(msg)
    return output


def _run(command: Sequence[str], cwd: Path, timeout: float) -> None:
    result = subprocess.run(  # noqa: S603
        tuple(command),
        cwd=cwd,
        check=False,
        timeout=timeout,
    )
    if result.returncode != 0:
        msg = "the Mac-side Windows application package command failed"
        raise RuntimeError(msg)


def _package_electron(project_root: Path) -> Path:
    desktop = project_root / "desktop"
    pnpm = shutil.which("pnpm")
    if pnpm is None:
        msg = "pnpm is required to cross-package the Windows application"
        raise RuntimeError(msg)
    _run((pnpm, "install", "--frozen-lockfile"), desktop, 900)
    _run((pnpm, "run", "package:windows-embedded"), desktop, 1800)
    candidates = [
        path
        for path in (desktop / "out").glob("*-win32-x64")
        if path.is_dir()
        and (path / "docmeta-review.exe").is_file()
        and (path / "resources/docmeta-runtime/python.exe").is_file()
    ]
    if len(candidates) != 1:
        msg = "Electron Forge did not produce exactly one Windows x64 application"
        raise RuntimeError(msg)
    return candidates[0]


def _product_version(project_root: Path) -> str:
    value = _read_json_mapping(
        project_root / "desktop/package.json",
        "the desktop package metadata",
    )
    version = value.get("version")
    if not isinstance(version, str) or _VERSION_PATTERN.fullmatch(version) is None:
        msg = "the desktop product version is invalid"
        raise RuntimeError(msg)
    return version


def _git_commit(project_root: Path) -> str:
    git = shutil.which("git")
    if git is None:
        return "unavailable"
    result = subprocess.run(  # noqa: S603
        (git, "-C", str(project_root), "rev-parse", "HEAD"),
        check=False,
        capture_output=True,
        timeout=30,
    )
    if result.returncode != 0:
        return "unavailable"
    commit = result.stdout.decode("ascii", errors="ignore").strip().casefold()
    return commit if re.fullmatch(r"[0-9a-f]{40}", commit) else "unavailable"


def _write_release_manifest(staged: Path, covered: Sequence[Path]) -> None:
    records = [f"{_hash(path)}  {path.name}" for path in sorted(covered)]
    _ = (staged / "SHA256SUMS").write_text(
        "\n".join(records) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _release_version(build_info: dict[str, object]) -> str:
    version = build_info.get("product_version")
    if (
        build_info.get("schema_version") != "1"
        or build_info.get("target") != "windows-x86_64"
        or not isinstance(version, str)
        or _VERSION_PATTERN.fullmatch(version) is None
    ):
        msg = "the Windows release build information is invalid"
        raise RuntimeError(msg)
    return version


def _checksum_records(release: Path, expected_names: set[str]) -> dict[str, str]:
    lines = (release / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    records: dict[str, str] = {}
    for line in lines:
        digest, separator, name = line.partition("  ")
        if (
            separator != "  "
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or name not in expected_names
            or name in records
        ):
            msg = "the Windows release checksum manifest is invalid"
            raise RuntimeError(msg)
        records[name] = digest
    if set(records) != expected_names:
        msg = "the Windows release checksum manifest is incomplete"
        raise RuntimeError(msg)
    for name, digest in records.items():
        if _hash(release / name) != digest:
            msg = "the Windows release checksum verification failed"
            raise RuntimeError(msg)
    return records


def verify_windows_release_directory(release: Path) -> int:
    """Verify the exact Mac-produced Windows x64 release file set and hashes."""
    _require_tree(release, "the Windows release directory")
    build_info_path = release / "BUILD-INFO.json"
    _require_regular(build_info_path, "the Windows release build information")
    build_info = _read_json_mapping(
        build_info_path,
        "the Windows release build information",
    )
    version = _release_version(build_info)
    portable_name = f"DocumentMetadataInspector-{version}-win-x64-Portable.zip"
    setup_name = f"DocumentMetadataInspector-{version}-win-x64-Setup.exe"
    expected_names = {
        "BUILD-INFO.json",
        portable_name,
        setup_name,
        "SHA256SUMS",
        "THIRD_PARTY_NOTICES.md",
    }
    observed_names = {path.name for path in release.iterdir()}
    if observed_names != expected_names:
        msg = "the Windows release directory has an unexpected inventory"
        raise RuntimeError(msg)
    expected_covered = expected_names - {"SHA256SUMS"}
    records = _checksum_records(release, expected_covered)
    artifacts = _mapping(
        build_info.get("artifacts"),
        "the Windows release build information is invalid",
    )
    if (
        artifacts.get("portable_sha256") != records[portable_name]
        or artifacts.get("setup_sha256") != records[setup_name]
    ):
        msg = "the Windows release artifact hashes are inconsistent"
        raise RuntimeError(msg)
    return len(records)


def build_windows_embedded_release(
    project_root: Path,
    output_directory: Path,
    cache: Path,
    *,
    makensis: Path | None = None,
) -> Path:
    """Build and atomically publish a Mac-cross-packaged Windows x64 release."""
    project_root = project_root.resolve()
    output_directory = output_directory.resolve()
    cache = cache.resolve()
    if output_directory.exists():
        msg = "the Windows x64 release output already exists"
        raise FileExistsError(msg)
    runtime = project_root / "desktop/.runtime/docmeta-runtime"
    if runtime.exists():
        shutil.rmtree(runtime)
    _ = build_windows_embedded_runtime(project_root, runtime, cache)
    application = _package_electron(project_root)
    pe_count = verify_packaged_windows_application(application)
    version = _product_version(project_root)
    executable = makensis
    if executable is None:
        resolved = shutil.which("makensis")
        if resolved is None:
            msg = "native macOS makensis is required to build the Windows installer"
            raise RuntimeError(msg)
        executable = Path(resolved)

    output_directory.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        prefix=f".{output_directory.name}.",
        dir=output_directory.parent,
    ) as temporary_text:
        staged = Path(temporary_text) / output_directory.name
        staged.mkdir()
        base = f"DocumentMetadataInspector-{version}-win-x64"
        portable = create_portable_zip(
            application, staged / f"{base}-Portable.zip", base
        )
        setup = compile_windows_installer(
            application,
            staged / f"{base}-Setup.exe",
            project_root / "desktop/installer/windows-x64.nsi",
            project_root / "desktop/build/icons/icon.ico",
            makensis=executable,
        )
        notices = staged / "THIRD_PARTY_NOTICES.md"
        _ = shutil.copy2(project_root / "THIRD_PARTY_NOTICES.md", notices)
        runtime_inventory = (
            application / "resources/docmeta-runtime/RUNTIME-SHA256SUMS.json"
        )
        build_info = staged / "BUILD-INFO.json"
        _ = build_info.write_text(
            json.dumps(
                {
                    "schema_version": "1",
                    "target": "windows-x86_64",
                    "product_version": version,
                    "built_at_utc": datetime.now(UTC).isoformat(),
                    "git_commit": _git_commit(project_root),
                    "packaged_pe_file_count": pe_count,
                    "runtime_inventory_sha256": _hash(runtime_inventory),
                    "artifacts": {
                        "portable_sha256": _hash(portable),
                        "setup_sha256": _hash(setup),
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        _write_release_manifest(staged, (build_info, portable, setup, notices))
        _ = verify_windows_release_directory(staged)
        _ = staged.replace(output_directory)
    return output_directory


def _parser(project_root: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a self-contained Windows x64 installer entirely on macOS."
    )
    _ = parser.add_argument(
        "--output-directory",
        type=Path,
        default=project_root / "release/windows-x64",
    )
    _ = parser.add_argument(
        "--cache",
        type=Path,
        default=project_root / "tools/build-cache/windows-embedded",
    )
    _ = parser.add_argument("--makensis", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Mac-only Windows x64 release builder."""
    project_root = Path(__file__).resolve().parent.parent
    arguments = cast(
        "_Arguments",
        cast("object", _parser(project_root).parse_args(argv)),
    )
    result = build_windows_embedded_release(
        project_root,
        arguments.output_directory,
        arguments.cache,
        makensis=arguments.makensis,
    )
    print(f"Windows x64 release is ready: {result}")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
