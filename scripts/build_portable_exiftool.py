"""Build a relocatable Perl + ExifTool runtime for macOS or Linux releases."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tarfile
import urllib.request
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import TYPE_CHECKING, Protocol, cast

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import BinaryIO

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_MANIFEST_PATH = _PROJECT_ROOT / "tools/manifest.json"
_EXIFTOOL_SOURCE = _PROJECT_ROOT / "tools/vendor/exiftool/13.55/source"
_DEFAULT_CACHE = _PROJECT_ROOT / "tools/build-cache/downloads"
_CHUNK_BYTES = 1024 * 1024
_DIAGNOSTIC_BYTES = 8 * 1024


class _Arguments(Protocol):
    output: Path
    cache: Path
    jobs: int


def _hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _source_config() -> tuple[str, str, str]:
    value = cast("object", json.loads(_MANIFEST_PATH.read_text(encoding="utf-8")))
    if not isinstance(value, dict):
        msg = "tool manifest root must be an object"
        raise TypeError(msg)
    payload = cast("dict[str, object]", value)
    perl = payload.get("portable_perl")
    if not isinstance(perl, dict):
        msg = "portable Perl configuration is missing"
        raise TypeError(msg)
    perl_map = cast("dict[str, object]", perl)
    source = perl_map.get("official_source")
    version = perl_map.get("version")
    if not isinstance(source, dict) or not isinstance(version, str):
        msg = "portable Perl configuration is invalid"
        raise TypeError(msg)
    source_map = cast("dict[str, object]", source)
    url = source_map.get("url")
    expected_hash = source_map.get("sha256")
    if not isinstance(url, str) or not isinstance(expected_hash, str):
        msg = "portable Perl source configuration is invalid"
        raise TypeError(msg)
    return version, url, expected_hash


def _archive_zip_config() -> tuple[str, str, str]:
    value = cast("object", json.loads(_MANIFEST_PATH.read_text(encoding="utf-8")))
    if not isinstance(value, dict):
        msg = "tool manifest root must be an object"
        raise TypeError(msg)
    payload = cast("dict[str, object]", value)
    perl = payload.get("portable_perl")
    if not isinstance(perl, dict):
        msg = "portable Perl configuration is missing"
        raise TypeError(msg)
    modules = cast("dict[str, object]", perl).get("modules")
    if not isinstance(modules, dict):
        msg = "portable Perl module configuration is missing"
        raise TypeError(msg)
    archive_zip = cast("dict[str, object]", modules).get("archive_zip")
    if not isinstance(archive_zip, dict):
        msg = "Archive::Zip configuration is missing"
        raise TypeError(msg)
    module = cast("dict[str, object]", archive_zip)
    version = module.get("version")
    source = module.get("official_source")
    if not isinstance(version, str) or not isinstance(source, dict):
        msg = "Archive::Zip configuration is invalid"
        raise TypeError(msg)
    source_map = cast("dict[str, object]", source)
    url = source_map.get("url")
    expected_hash = source_map.get("sha256")
    if not isinstance(url, str) or not isinstance(expected_hash, str):
        msg = "Archive::Zip source configuration is invalid"
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


def _cached_archive(cache: Path, version: str, url: str, expected: str) -> Path:
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / f"perl-{version}.tar.gz"
    if archive.is_file():
        if _hash(archive) != expected:
            msg = "the cached Perl source failed its integrity check"
            raise RuntimeError(msg)
        return archive
    with NamedTemporaryFile(
        prefix=f".perl-{version}.", suffix=".download", dir=cache, delete=False
    ) as stream:
        temporary = Path(stream.name)
    try:
        _download(url, temporary)
        if _hash(temporary) != expected:
            msg = "the downloaded Perl source failed its integrity check"
            raise RuntimeError(msg)
        _ = temporary.replace(archive)
    finally:
        temporary.unlink(missing_ok=True)
    return archive


def _cached_module_archive(
    cache: Path,
    version: str,
    url: str,
    expected: str,
) -> Path:
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / f"Archive-Zip-{version}.tar.gz"
    if archive.is_file():
        if _hash(archive) != expected:
            msg = "the cached Archive::Zip source failed its integrity check"
            raise RuntimeError(msg)
        return archive
    with NamedTemporaryFile(
        prefix=f".Archive-Zip-{version}.",
        suffix=".download",
        dir=cache,
        delete=False,
    ) as stream:
        temporary = Path(stream.name)
    try:
        _download(url, temporary)
        if _hash(temporary) != expected:
            msg = "the downloaded Archive::Zip source failed its integrity check"
            raise RuntimeError(msg)
        _ = temporary.replace(archive)
    finally:
        temporary.unlink(missing_ok=True)
    return archive


def _extract(archive: Path, destination: Path, version: str) -> Path:
    with tarfile.open(archive, "r:gz") as source:
        members = source.getmembers()
        if any(not (member.isfile() or member.isdir()) for member in members):
            msg = "the Perl source archive contains unsupported entries"
            raise RuntimeError(msg)
        source.extractall(destination, members=members, filter="data")
    root = destination / f"perl-{version}"
    if not root.is_dir():
        msg = "the Perl source archive layout is invalid"
        raise RuntimeError(msg)
    return root


def _extract_archive_zip(archive: Path, destination: Path, version: str) -> Path:
    with tarfile.open(archive, "r:gz") as source:
        members = source.getmembers()
        if any(not (member.isfile() or member.isdir()) for member in members):
            msg = "the Archive::Zip source contains unsupported entries"
            raise RuntimeError(msg)
        source.extractall(destination, members=members, filter="data")
    root = destination / f"Archive-Zip-{version}"
    if not root.is_dir():
        msg = "the Archive::Zip source archive layout is invalid"
        raise RuntimeError(msg)
    return root


def _run(
    command: Sequence[str],
    cwd: Path,
    environment: dict[str, str],
    *,
    timeout: float,
    capture: bool = False,
) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(  # noqa: S603
        tuple(command),
        cwd=cwd,
        env=environment,
        check=False,
        capture_output=capture,
        timeout=timeout,
    )
    if result.returncode != 0:
        output_sections: list[str] = []
        for label, content in (("stdout", result.stdout), ("stderr", result.stderr)):
            if content:
                tail = content[-_DIAGNOSTIC_BYTES:].decode("utf-8", errors="replace")
                output_sections.append(f"{label} tail:\n{tail.rstrip()}")
        diagnostic = "\n".join(output_sections)
        suffix = f"\n{diagnostic}" if diagnostic else ""
        msg = (
            f"portable runtime command {command[0]!r} failed with "
            f"exit {result.returncode}{suffix}"
        )
        raise RuntimeError(msg)
    return result


def _copy_licenses(
    source_root: Path,
    archive_zip_root: Path,
    output: Path,
) -> None:
    perl_licenses = output / "licenses/perl"
    exiftool_licenses = output / "licenses/exiftool"
    archive_zip_licenses = output / "licenses/archive-zip"
    perl_licenses.mkdir(parents=True)
    exiftool_licenses.mkdir(parents=True)
    archive_zip_licenses.mkdir(parents=True)
    for name in ("Artistic", "Copying"):
        source = source_root / name
        if source.is_file():
            _ = shutil.copy2(source, perl_licenses / name)
    _ = shutil.copy2(_EXIFTOOL_SOURCE / "README", exiftool_licenses / "README")
    for name in ("LICENSE", "README", "README.md"):
        source = archive_zip_root / name
        if source.is_file():
            _ = shutil.copy2(source, archive_zip_licenses / name)


def _copy_exiftool_runtime(source: Path, destination: Path) -> None:
    """Copy only the upstream command and modules required for read-only use."""
    command = source / "exiftool"
    library = source / "lib"
    if command.is_symlink() or not command.is_file():
        msg = "the ExifTool source command is missing or unsafe"
        raise RuntimeError(msg)
    if library.is_symlink() or not library.is_dir():
        msg = "the ExifTool source library is missing or unsafe"
        raise RuntimeError(msg)
    if any(path.is_symlink() for path in library.rglob("*")):
        msg = "the ExifTool source library contains a symbolic link"
        raise RuntimeError(msg)
    destination.mkdir(parents=True)
    _ = shutil.copy2(command, destination / "exiftool")
    _ = shutil.copytree(library, destination / "lib", copy_function=shutil.copy2)


def _install_archive_zip(source: Path, install: Path, perl_version: str) -> None:
    """Install the pure-Perl ZIP reader into the relocatable site library."""
    module = source / "lib/Archive"
    if module.is_symlink() or not module.is_dir():
        msg = "the Archive::Zip source module is missing or unsafe"
        raise RuntimeError(msg)
    if any(path.is_symlink() for path in module.rglob("*")):
        msg = "the Archive::Zip source module contains a symbolic link"
        raise RuntimeError(msg)
    site_library = install / f"lib/site_perl/{perl_version}"
    site_library.mkdir(parents=True, exist_ok=True)
    _ = shutil.copytree(module, site_library / "Archive", copy_function=shutil.copy2)


def build(output: Path, cache: Path, jobs: int) -> Path:
    """Compile, relocate and execute a private Perl + ExifTool runtime."""
    output = output.resolve()
    cache = cache.resolve()
    if os.name == "nt":
        msg = "use build_windows_exiftool.py on Windows"
        raise RuntimeError(msg)
    if output.exists():
        msg = "the portable ExifTool output already exists"
        raise FileExistsError(msg)
    if not _EXIFTOOL_SOURCE.is_dir():
        msg = "run bootstrap_tools.py before building the portable runtime"
        raise RuntimeError(msg)
    version, url, expected_hash = _source_config()
    archive = _cached_archive(cache, version, url, expected_hash)
    module_version, module_url, module_hash = _archive_zip_config()
    module_archive = _cached_module_archive(
        cache,
        module_version,
        module_url,
        module_hash,
    )
    with TemporaryDirectory(prefix="docmeta-portable-perl-") as temporary_text:
        workspace = Path(temporary_text)
        source_root = _extract(archive, workspace / "source", version)
        archive_zip_root = _extract_archive_zip(
            module_archive,
            workspace / "modules",
            module_version,
        )
        install = workspace / "install"
        environment = {
            **os.environ,
            "HOME": str(workspace),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "TZ": "UTC",
        }
        _ = _run(
            (
                "sh",
                "Configure",
                "-des",
                f"-Dprefix={install}",
                "-Duserelocatableinc",
                "-Duseshrplib=false",
                "-Dman1dir=none",
                "-Dman3dir=none",
                "-Dhtml1dir=none",
                "-Dhtml3dir=none",
            ),
            source_root,
            environment,
            timeout=600,
            capture=True,
        )
        _ = _run(
            ("make", f"-j{jobs}"),
            source_root,
            environment,
            timeout=1800,
            capture=True,
        )
        _ = _run(
            ("make", "install"),
            source_root,
            environment,
            timeout=600,
            capture=True,
        )
        _install_archive_zip(archive_zip_root, install, version)
        staging = output.parent / f".{output.name}.staging"
        if staging.exists():
            msg = "a stale portable ExifTool staging directory exists"
            raise FileExistsError(msg)
        staging.mkdir(parents=True)
        try:
            _ = shutil.copytree(install, staging / "perl")
            _copy_exiftool_runtime(_EXIFTOOL_SOURCE, staging / "exiftool-source")
            _copy_licenses(source_root, archive_zip_root, staging)
            perl = staging / "perl/bin/perl"
            exiftool = staging / "exiftool-source/exiftool"
            module_result = _run(
                (
                    str(perl),
                    "-MArchive::Zip",
                    "-e",
                    "print $Archive::Zip::VERSION",
                ),
                staging,
                {**environment, "HOME": str(staging)},
                timeout=30,
                capture=True,
            )
            if (
                module_result.stdout.decode("ascii", errors="strict").strip()
                != module_version
            ):
                msg = "the relocated Archive::Zip module has the wrong version"
                raise RuntimeError(msg)
            version_result = _run(
                (str(perl), str(exiftool), "-ver"),
                staging,
                {**environment, "HOME": str(staging)},
                timeout=30,
                capture=True,
            )
            if (
                version_result.stdout.decode("ascii", errors="strict").strip()
                != "13.55"
            ):
                msg = "the relocated ExifTool runtime has the wrong version"
                raise RuntimeError(msg)
            _ = staging.replace(output)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    return output


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a relocatable Perl and ExifTool release runtime."
    )
    _ = parser.add_argument("--output", type=Path, required=True)
    _ = parser.add_argument("--cache", type=Path, default=_DEFAULT_CACHE)
    _ = parser.add_argument(
        "--jobs",
        type=int,
        default=max(1, min(8, os.cpu_count() or 1)),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Build and report one relocatable ExifTool runtime tree."""
    arguments = cast("_Arguments", cast("object", _parser().parse_args(argv)))
    runtime = build(arguments.output, arguments.cache, arguments.jobs)
    print(f"Portable ExifTool runtime is ready: {runtime}")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
