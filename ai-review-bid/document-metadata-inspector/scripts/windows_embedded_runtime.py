"""Assemble a self-contained Windows x64 Python application runtime."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import urllib.request
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import TYPE_CHECKING, cast
from urllib.parse import urlparse
from zipfile import ZipFile, ZipInfo

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from typing import BinaryIO

if __package__:
    from scripts.bootstrap_jdk import ensure_jdk
    from scripts.build_windows_exiftool import build as build_windows_exiftool
else:
    from bootstrap_jdk import (  # pyright: ignore[reportImplicitRelativeImport]
        ensure_jdk,
    )
    from build_windows_exiftool import (  # pyright: ignore[reportImplicitRelativeImport]
        build as build_windows_exiftool,
    )

_TARGET_KEY = "windows-x86_64"
_HASH_CHUNK_BYTES = 1024 * 1024
_INVENTORY_NAME = "RUNTIME-SHA256SUMS.json"
_MAX_ARCHIVE_ENTRIES = 50_000
_MAX_ARCHIVE_BYTES = 4 * 1024 * 1024 * 1024
_PYTHON_TARGET = "cpython-3.12.13-windows-x86_64-none"
_PYTHON_PLATFORM = "x86_64-pc-windows-msvc"
_SHA256_HEX_LENGTH = 64
_PYTHON_ROOT_OMISSIONS = frozenset({"include", "libs", "scripts", "tcl"})
_PYTHON_LIB_OMISSIONS = frozenset(
    {"ensurepip", "idlelib", "lib2to3", "tkinter", "turtledemo", "venv"}
)
_PYTHON_DLL_OMISSIONS = frozenset({"_tkinter.pyd", "tcl86t.dll", "tk86t.dll"})


@dataclass(frozen=True, slots=True)
class WindowsRuntimeSources:
    """Hold already acquired Windows x64 runtime inputs."""

    python_home: Path
    java_home: Path
    worker_jar: Path
    exiftool_home: Path


def _hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _run(command: Sequence[str], cwd: Path, timeout: float) -> None:
    result = subprocess.run(  # noqa: S603
        tuple(command),
        cwd=cwd,
        env={**os.environ, "PYTHONHOME": "", "PYTHONPATH": ""},
        check=False,
        timeout=timeout,
    )
    if result.returncode != 0:
        msg = "a Windows embedded-runtime build command failed"
        raise RuntimeError(msg)


def _require_regular(path: Path, description: str) -> None:
    try:
        metadata = path.lstat()
    except OSError as error:
        msg = f"{description} is missing"
        raise RuntimeError(msg) from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        msg = f"{description} must be a regular file"
        raise RuntimeError(msg)


def _require_tree(
    root: Path,
    description: str,
    *,
    ignored_symlinks: frozenset[Path] | None = None,
) -> None:
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
            if ignored_symlinks is not None and path in ignored_symlinks:
                continue
            msg = f"{description} contains a symbolic link"
            raise RuntimeError(msg)
        if not (stat.S_ISDIR(child.st_mode) or stat.S_ISREG(child.st_mode)):
            msg = f"{description} contains a non-regular entry"
            raise RuntimeError(msg)


def _copy_tree(source: Path, destination: Path, description: str) -> None:
    _require_tree(source, description)
    _ = shutil.copytree(
        source,
        destination,
        copy_function=shutil.copy2,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )


def _copy_windows_python_tree(source: Path, destination: Path) -> None:
    """Copy only the Windows Python files needed by this runtime."""
    launcher = source / "python"
    library = source / "Lib"
    dynamic_libraries = source / "DLLs"
    site_packages = source / "Lib/site-packages"
    ignored_symlinks: frozenset[Path] = (
        frozenset({launcher}) if launcher.is_symlink() else frozenset()
    )
    _require_tree(
        source,
        "the Windows Python runtime",
        ignored_symlinks=ignored_symlinks,
    )
    default_ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo")

    def ignored(directory: str, names: list[str]) -> set[str]:
        result = set(default_ignore(directory, names))
        current = Path(directory)
        if current == source:
            result.update(
                name for name in names if name.casefold() in _PYTHON_ROOT_OMISSIONS
            )
            if ignored_symlinks and "python" in names:
                result.add("python")
        elif current == library:
            result.update(
                name for name in names if name.casefold() in _PYTHON_LIB_OMISSIONS
            )
        elif current == dynamic_libraries:
            result.update(
                name for name in names if name.casefold() in _PYTHON_DLL_OMISSIONS
            )
        elif current == site_packages:
            result.update(
                name
                for name in names
                if name.casefold() == "pip"
                or (
                    name.casefold().startswith("pip-")
                    and name.casefold().endswith(".dist-info")
                )
            )
        return result

    _ = shutil.copytree(
        source,
        destination,
        copy_function=shutil.copy2,
        ignore=ignored,
    )


def _find_windows_python_home(root: Path) -> Path:
    candidates: set[Path] = set()
    for executable in root.rglob("python.exe"):
        home = executable.parent
        if (
            executable.is_file()
            and not executable.is_symlink()
            and (home / "python312.dll").is_file()
            and (home / "Lib").is_dir()
        ):
            candidates.add(home)
    if len(candidates) != 1:
        msg = "the uv installation must contain exactly one Windows Python 3.12 home"
        raise RuntimeError(msg)
    return candidates.pop()


def _safe_archive_relative(name: str) -> PurePosixPath:
    if not name or "\\" in name:
        msg = "the Windows archive contains an unsafe member path"
        raise RuntimeError(msg)
    relative = PurePosixPath(name)
    if (
        relative.is_absolute()
        or any(part in ("", ".", "..") for part in relative.parts)
        or (relative.parts and ":" in relative.parts[0])
    ):
        msg = "the Windows archive contains an unsafe member path"
        raise RuntimeError(msg)
    return relative


def _extract_windows_zip(archive: Path, destination: Path) -> None:
    if destination.exists():
        msg = "the Windows archive destination already exists"
        raise FileExistsError(msg)
    with ZipFile(archive) as package:
        members = package.infolist()
        if len(members) > _MAX_ARCHIVE_ENTRIES:
            msg = "the Windows archive contains too many entries"
            raise RuntimeError(msg)
        if sum(member.file_size for member in members) > _MAX_ARCHIVE_BYTES:
            msg = "the Windows archive is too large"
            raise RuntimeError(msg)
        normalized: set[str] = set()
        validated: list[tuple[ZipInfo, PurePosixPath]] = []
        for member in members:
            relative = _safe_archive_relative(member.filename.rstrip("/"))
            key = relative.as_posix().casefold()
            if key in normalized:
                msg = "the Windows archive contains duplicate member paths"
                raise RuntimeError(msg)
            normalized.add(key)
            mode = (member.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                msg = "the Windows archive contains an unsafe symbolic link"
                raise RuntimeError(msg)
            validated.append((member, relative))
        destination.mkdir(parents=True)
        try:
            for member, relative in validated:
                target = destination.joinpath(*relative.parts)
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with package.open(member) as source, target.open("xb") as output:
                    _ = shutil.copyfileobj(source, output)
        except BaseException:
            shutil.rmtree(destination)
            raise


def _find_windows_jre_home(root: Path, expected_version: str) -> Path:
    candidates: set[Path] = set()
    accepted_runtime_versions = (expected_version, f"{expected_version}-LTS")
    for executable in root.rglob("java.exe"):
        home = executable.parent.parent
        release = home / "release"
        jvm = home / "bin/server/jvm.dll"
        if not release.is_file() or not jvm.is_file():
            continue
        try:
            release_text = release.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        version_matches = any(
            f'JAVA_RUNTIME_VERSION="{version}"' in release_text
            for version in accepted_runtime_versions
        )
        provenance_matches = all(
            marker in release_text
            for marker in (
                'IMPLEMENTOR="Eclipse Adoptium"',
                'OS_ARCH="x86_64"',
                'OS_NAME="Windows"',
                'IMAGE_TYPE="JRE"',
            )
        )
        if version_matches and provenance_matches:
            candidates.add(home)
    if len(candidates) != 1:
        msg = "the archive did not contain exactly one pinned Temurin JRE home"
        raise RuntimeError(msg)
    return candidates.pop()


def _acquire_windows_python(project_root: Path, cache: Path) -> Path:
    install_root = cache.parent / "python-windows-x64"
    try:
        return _find_windows_python_home(install_root)
    except RuntimeError:
        pass
    _run(
        (
            "uv",
            "python",
            "install",
            _PYTHON_TARGET,
            "--install-dir",
            str(install_root),
            "--no-bin",
            "--cache-dir",
            str(cache.parent / "uv"),
        ),
        project_root,
        900,
    )
    return _find_windows_python_home(install_root)


def _windows_wheel_install_command(
    requirements: Path,
    site_packages: Path,
    cache: Path,
) -> tuple[str, ...]:
    return (
        "uv",
        "pip",
        "install",
        "--requirements",
        str(requirements),
        "--target",
        str(site_packages),
        "--python-version",
        "3.12.13",
        "--python-platform",
        _PYTHON_PLATFORM,
        "--only-binary",
        ":all:",
        "--require-hashes",
        "--cache-dir",
        str(cache),
    )


def _prepare_windows_python(
    project_root: Path,
    source: Path,
    destination: Path,
    cache: Path,
) -> Path:
    _copy_windows_python_tree(source, destination)
    site_packages = destination / "Lib/site-packages"
    site_packages.mkdir(parents=True, exist_ok=True)
    requirements = destination.parent / "windows-production-requirements.txt"
    _run(
        (
            "uv",
            "export",
            "--locked",
            "--no-dev",
            "--no-emit-project",
            "--no-emit-workspace",
            "--format",
            "requirements.txt",
            "--output-file",
            str(requirements),
        ),
        project_root,
        120,
    )
    _run(
        _windows_wheel_install_command(
            requirements,
            site_packages,
            cache.parent / "uv",
        ),
        project_root,
        900,
    )
    return destination


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(  # noqa: S310
        url,
        headers={"User-Agent": "document-metadata-inspector-build/0.1"},
    )
    response = cast(
        "BinaryIO",
        urllib.request.urlopen(request, timeout=120),  # noqa: S310
    )
    with response, destination.open("wb") as output:
        while chunk := response.read(_HASH_CHUNK_BYTES):
            _ = output.write(chunk)


def _verified_download(
    url: str,
    expected_hash: str,
    downloads: Path,
    prefix: str,
) -> Path:
    name = Path(urlparse(url).path).name
    if not name:
        msg = "a Windows runtime URL has no filename"
        raise RuntimeError(msg)
    downloads.mkdir(parents=True, exist_ok=True)
    archive = downloads / f"{prefix}-{name}"
    if archive.is_file():
        if _hash(archive) != expected_hash:
            msg = "a cached Windows runtime archive failed its integrity check"
            raise RuntimeError(msg)
        return archive
    with NamedTemporaryFile(
        prefix=f".{prefix}.",
        suffix=".download",
        dir=downloads,
        delete=False,
    ) as stream:
        temporary = Path(stream.name)
    try:
        _download(url, temporary)
        if _hash(temporary) != expected_hash:
            msg = "a downloaded Windows runtime archive failed its integrity check"
            raise RuntimeError(msg)
        _ = temporary.replace(archive)
    finally:
        temporary.unlink(missing_ok=True)
    return archive


def _acquire_windows_jre(project_root: Path, cache: Path) -> Path:
    try:
        value = cast(
            "object",
            json.loads(
                (project_root / "tools/manifest.json").read_text(encoding="utf-8")
            ),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        msg = "the tool manifest is invalid"
        raise RuntimeError(msg) from error
    payload = _mapping(value, "the tool manifest root must be an object")
    temurin = _mapping(
        payload.get("temurin_jre"),
        "the Temurin JRE manifest is missing",
    )
    archives = _mapping(
        temurin.get("archives"),
        "the Temurin JRE archives are missing",
    )
    archive_config = _mapping(
        archives.get(_TARGET_KEY),
        "the Windows x64 Temurin JRE archive is missing",
    )
    version = temurin.get("version")
    url = archive_config.get("url")
    expected_hash = archive_config.get("sha256")
    archive_type = archive_config.get("archive_type")
    if (
        not isinstance(version, str)
        or not isinstance(url, str)
        or not isinstance(expected_hash, str)
        or archive_type != "zip"
    ):
        msg = "the Windows x64 Temurin JRE configuration is invalid"
        raise RuntimeError(msg)
    destination = cache / "jre" / version.replace("+", "_")
    if destination.exists():
        return _find_windows_jre_home(destination, version)
    archive = _verified_download(
        url,
        expected_hash,
        cache.parent / "temurin/downloads",
        _TARGET_KEY,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        prefix=f".{_TARGET_KEY}-jre.",
        dir=destination.parent,
    ) as temporary_text:
        temporary = Path(temporary_text)
        extracted = temporary / "extracted"
        _extract_windows_zip(archive, extracted)
        home = _find_windows_jre_home(extracted, version)
        _copy_tree(home, temporary / "home", "the Windows Temurin JRE")
        _ = (temporary / "home").replace(destination)
    return _find_windows_jre_home(destination, version)


def _build_apache_worker(project_root: Path, cache: Path) -> Path:
    java_home = ensure_jdk(cache.parent / "temurin")
    wrapper = project_root / "java-worker/mvnw"
    _require_regular(wrapper, "the Maven Wrapper")
    environment = {
        **os.environ,
        "JAVA_HOME": str(java_home),
        "PATH": f"{java_home / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}",
    }
    result = subprocess.run(  # noqa: S603
        (
            "/bin/sh",
            str(wrapper),
            "--batch-mode",
            "--no-transfer-progress",
            "verify",
        ),
        cwd=project_root / "java-worker",
        env=environment,
        check=False,
        timeout=1200,
    )
    if result.returncode != 0:
        msg = "the Apache Java worker build failed"
        raise RuntimeError(msg)
    worker = project_root / "java-worker/target/document-metadata-apache-worker.jar"
    _require_regular(worker, "the Apache worker JAR")
    return worker


def _acquire_windows_exiftool(project_root: Path, cache: Path) -> Path:
    output = cache / "exiftool"
    if output.exists():
        _require_tree(output, "the cached Windows ExifTool runtime")
        _require_regular(output / "exiftool.exe", "the Windows ExifTool executable")
        _require_tree(output / "exiftool_files", "the Windows ExifTool support tree")
        return output
    _ = build_windows_exiftool(output, project_root / "tools/build-cache/downloads")
    _require_regular(output / "exiftool.exe", "the Windows ExifTool executable")
    _require_tree(output / "exiftool_files", "the Windows ExifTool support tree")
    return output


def _mapping(value: object, message: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError(message)
    return cast("dict[str, object]", value)


def _file_hashes(root: Path, prefix: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        files[(prefix / relative).as_posix()] = _hash(path)
    if not files:
        msg = "a packaged runtime component is empty"
        raise RuntimeError(msg)
    return files


def _release_manifest(project_root: Path, application: Path) -> None:
    source = project_root / "tools/manifest.json"
    _require_regular(source, "the tool manifest")
    try:
        value = cast("object", json.loads(source.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        msg = "the tool manifest is invalid"
        raise RuntimeError(msg) from error
    payload = _mapping(value, "the tool manifest root must be an object")
    apache_manifest = _mapping(
        payload.get("apache_worker"),
        "the Apache worker manifest is missing",
    )
    apache_packaged = _mapping(
        apache_manifest.get("packaged"),
        "the Apache packaged manifest is missing",
    )
    exiftool_manifest = _mapping(
        payload.get("exiftool"),
        "the ExifTool manifest is missing",
    )
    exiftool_packaged = _mapping(
        exiftool_manifest.get("packaged"),
        "the ExifTool packaged manifest is missing",
    )
    packaged_root = application / "tools/packaged" / _TARGET_KEY
    apache = packaged_root / "apache"
    exiftool = packaged_root / "exiftool"
    prefix = Path("tools/packaged") / _TARGET_KEY
    apache_packaged[_TARGET_KEY] = {
        "available": True,
        "java": (prefix / "apache/jre/bin/java.exe").as_posix(),
        "worker_jar": (prefix / "apache/worker.jar").as_posix(),
        "files": _file_hashes(apache, prefix / "apache"),
    }
    exiftool_packaged[_TARGET_KEY] = {
        "available": True,
        "command": [(prefix / "exiftool/exiftool.exe").as_posix()],
        "files": _file_hashes(exiftool, prefix / "exiftool"),
    }
    manifest = application / "tools/manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    _ = manifest.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _runtime_metadata(project_root: Path, runtime: Path) -> None:
    source_manifest = cast(
        "Mapping[str, object]",
        json.loads((project_root / "tools/manifest.json").read_text(encoding="utf-8")),
    )
    apache = cast("Mapping[str, object]", source_manifest["apache_worker"])
    exiftool = cast("Mapping[str, object]", source_manifest["exiftool"])
    payload = {
        "schema_version": "1",
        "target": _TARGET_KEY,
        "python_version": "3.12.13",
        "java_runtime_version": apache.get("java_runtime_version"),
        "exiftool_version": exiftool.get("version"),
        "launcher": "python.exe",
        "application_module": "document_metadata_inspector.cli",
    }
    _ = (runtime / "RUNTIME-INFO.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _inventory_files(runtime: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in sorted(runtime.rglob("*"), key=lambda item: item.as_posix()):
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            msg = "the embedded runtime contains a symbolic link"
            raise RuntimeError(msg)
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if not stat.S_ISREG(metadata.st_mode):
            msg = "the embedded runtime contains a non-regular entry"
            raise RuntimeError(msg)
        relative = path.relative_to(runtime).as_posix()
        if relative != _INVENTORY_NAME:
            files[relative] = _hash(path)
    return files


def _write_inventory(runtime: Path) -> None:
    payload = {"schema_version": "1", "files": _inventory_files(runtime)}
    _ = (runtime / _INVENTORY_NAME).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def verify_runtime_inventory(runtime: Path) -> int:
    """Verify the complete embedded runtime against its exact file inventory."""
    _require_tree(runtime, "the embedded runtime")
    manifest = runtime / _INVENTORY_NAME
    _require_regular(manifest, "the embedded runtime inventory")
    try:
        value = cast("object", json.loads(manifest.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        msg = "the embedded runtime inventory is invalid"
        raise RuntimeError(msg) from error
    payload = _mapping(value, "the embedded runtime inventory is invalid")
    if payload.get("schema_version") != "1":
        msg = "the embedded runtime inventory schema is invalid"
        raise RuntimeError(msg)
    records = _mapping(
        payload.get("files"), "the embedded runtime inventory is invalid"
    )
    observed = _inventory_files(runtime)
    if set(records) != set(observed):
        msg = "the embedded runtime inventory does not match its files"
        raise RuntimeError(msg)
    for relative, digest in records.items():
        if (
            not isinstance(digest, str)
            or len(digest) != _SHA256_HEX_LENGTH
            or observed.get(relative) != digest
        ):
            msg = "the embedded runtime inventory failed verification"
            raise RuntimeError(msg)
    return len(records)


def assemble_windows_embedded_runtime(
    project_root: Path,
    destination: Path,
    sources: WindowsRuntimeSources,
) -> Path:
    """Atomically assemble one complete Windows x64 embedded runtime tree."""
    project_root = project_root.resolve()
    destination = destination.resolve()
    if destination.exists():
        msg = "the embedded runtime destination already exists"
        raise FileExistsError(msg)
    for source, description in (
        (sources.python_home, "the Windows Python runtime"),
        (sources.java_home, "the Windows JRE runtime"),
        (sources.exiftool_home, "the Windows ExifTool runtime"),
    ):
        _require_tree(source, description)
    _require_regular(sources.worker_jar, "the Apache worker JAR")
    for package in ("document_metadata_inspector", "xlsx_metadata_forensics"):
        _require_tree(project_root / "src" / package, f"the {package} package")
    _require_regular(project_root / "THIRD_PARTY_NOTICES.md", "the notices file")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        prefix=f".{destination.name}.",
        dir=destination.parent,
    ) as temporary_text:
        staging = Path(temporary_text) / destination.name
        _copy_tree(sources.python_home, staging, "the Windows Python runtime")
        _require_regular(staging / "python.exe", "the embedded Python executable")
        _require_regular(staging / "python312.dll", "the embedded Python DLL")
        site_packages = staging / "Lib/site-packages"
        site_packages.mkdir(parents=True, exist_ok=True)
        _ = (site_packages / "docmeta-app.pth").write_text(
            "../../app/src\n",
            encoding="utf-8",
            newline="\n",
        )

        application = staging / "app"
        for package in ("document_metadata_inspector", "xlsx_metadata_forensics"):
            _copy_tree(
                project_root / "src" / package,
                application / "src" / package,
                f"the {package} package",
            )
        packaged = application / "tools/packaged" / _TARGET_KEY
        _copy_tree(
            sources.java_home,
            packaged / "apache/jre",
            "the Windows JRE runtime",
        )
        (packaged / "apache").mkdir(parents=True, exist_ok=True)
        _ = shutil.copy2(sources.worker_jar, packaged / "apache/worker.jar")
        _copy_tree(
            sources.exiftool_home,
            packaged / "exiftool",
            "the Windows ExifTool runtime",
        )
        _release_manifest(project_root, application)
        _ = shutil.copy2(
            project_root / "THIRD_PARTY_NOTICES.md",
            staging / "THIRD_PARTY_NOTICES.md",
        )
        _runtime_metadata(project_root, staging)
        python_hash = _hash(staging / "python.exe")
        _ = (staging / "SHA256SUMS").write_text(
            f"{python_hash}  python.exe\n",
            encoding="utf-8",
            newline="\n",
        )
        _write_inventory(staging)
        _ = verify_runtime_inventory(staging)
        _ = staging.replace(destination)
    return destination


def build_windows_embedded_runtime(
    project_root: Path,
    destination: Path,
    cache: Path,
) -> Path:
    """Acquire pinned Windows x64 inputs and assemble the embedded runtime."""
    project_root = project_root.resolve()
    cache = cache.resolve()
    cache.mkdir(parents=True, exist_ok=True)
    python_source = _acquire_windows_python(project_root, cache)
    java_home = _acquire_windows_jre(project_root, cache)
    worker_jar = _build_apache_worker(project_root, cache)
    exiftool_home = _acquire_windows_exiftool(project_root, cache)
    with TemporaryDirectory(prefix=".windows-python.", dir=cache) as temporary_text:
        prepared_python = _prepare_windows_python(
            project_root,
            python_source,
            Path(temporary_text) / "python",
            cache,
        )
        return assemble_windows_embedded_runtime(
            project_root,
            destination,
            WindowsRuntimeSources(
                python_home=prepared_python,
                java_home=java_home,
                worker_jar=worker_jar,
                exiftool_home=exiftool_home,
            ),
        )
