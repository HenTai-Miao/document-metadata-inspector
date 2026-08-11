"""Strict resolution and integrity checks for bundled parser resources."""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import Field, ValidationError

from document_metadata_inspector.models import FrozenModel
from document_metadata_inspector.subprocesses import hidden_subprocess_creation_flags

if TYPE_CHECKING:
    from collections.abc import Mapping

_MANIFEST_RELATIVE_PATH = Path("tools/manifest.json")
_HASH_CHUNK_BYTES = 1024 * 1024
_VERSION_TIMEOUT_SECONDS = 5.0


class ToolResourceError(RuntimeError):
    """Report a sanitized bundled-tool resolution or integrity failure."""


class ToolResourceUnavailableError(ToolResourceError):
    """Report that the required platform resource is not bundled."""


class _SourceArtifact(FrozenModel):
    url: str
    sha256: str
    directory: str
    tree_sha256: str


class _PackagedResource(FrozenModel):
    available: bool
    command: tuple[str, ...] = ()
    files: dict[str, str] = Field(default_factory=dict)


class _ExifToolManifest(FrozenModel):
    version: str
    official_source: _SourceArtifact
    packaged: dict[str, _PackagedResource]


class _ApachePackagedResource(FrozenModel):
    available: bool
    java: str = ""
    worker_jar: str = ""
    files: dict[str, str] = Field(default_factory=dict)


class _ApacheManifest(FrozenModel):
    tika_version: str
    java_major_version: int
    java_vendor: str | None = None
    java_runtime_version: str | None = None
    packaged: dict[str, _ApachePackagedResource]


class _RuntimeSourceArtifact(FrozenModel):
    url: str
    sha256: str


class _PerlModuleManifest(FrozenModel):
    version: str
    official_source: _RuntimeSourceArtifact


class _PortablePerlManifest(FrozenModel):
    version: str
    official_source: _RuntimeSourceArtifact
    modules: dict[str, _PerlModuleManifest] = Field(default_factory=dict)


class _WindowsExifToolManifest(FrozenModel):
    version: str
    official_archive: _RuntimeSourceArtifact


class _TemurinArchive(FrozenModel):
    url: str
    sha256: str
    archive_type: Literal["tar.gz", "zip"]


class _TemurinJdkManifest(FrozenModel):
    version: str
    release_url: str
    archives: dict[str, _TemurinArchive]


class _ToolManifest(FrozenModel):
    schema_version: str
    exiftool: _ExifToolManifest
    apache_worker: _ApacheManifest | None = None
    portable_perl: _PortablePerlManifest | None = None
    windows_exiftool: _WindowsExifToolManifest | None = None
    temurin_jdk: _TemurinJdkManifest | None = None
    temurin_jre: _TemurinJdkManifest | None = None


@dataclass(frozen=True, slots=True)
class ExifToolResource:
    """Hold the verified ExifTool command prefix and provenance."""

    command_prefix: tuple[str, ...]
    version: str
    source: str


@dataclass(frozen=True, slots=True)
class ApacheWorkerResource:
    """Hold verified Java and shaded-worker paths."""

    java_executable: Path
    worker_jar: Path
    tika_version: str
    java_major_version: int
    source: str


def platform_key() -> str:
    """Return the stable manifest key for the current OS and CPU architecture."""
    system_aliases = {
        "darwin": "darwin",
        "linux": "linux",
        "windows": "windows",
    }
    architecture_aliases = {
        "amd64": "x86_64",
        "x86_64": "x86_64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }
    system = system_aliases.get(platform.system().casefold())
    architecture = architecture_aliases.get(platform.machine().casefold())
    if system is None or architecture is None:
        msg = "This operating system or architecture is not supported."
        raise ToolResourceUnavailableError(msg)
    return f"{system}-{architecture}"


def file_sha256(path: Path) -> str:
    """Hash one regular, non-symlink resource file."""
    if path.is_symlink() or not path.is_file():
        msg = "A bundled tool resource is missing or is not a regular file."
        raise ToolResourceError(msg)
    digest = sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(_HASH_CHUNK_BYTES):
                digest.update(chunk)
    except OSError as error:
        msg = "A bundled tool resource could not be read."
        raise ToolResourceError(msg) from error
    return digest.hexdigest()


def tree_sha256(root: Path) -> str:
    """Hash a resource tree by sorted relative path and file content digest."""
    if root.is_symlink() or not root.is_dir():
        msg = "The bundled tool resource tree is missing."
        raise ToolResourceError(msg)
    paths = sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix())
    digest = sha256()
    file_count = 0
    for path in paths:
        if path.is_symlink():
            msg = "Bundled tool resource trees must not contain symbolic links."
            raise ToolResourceError(msg)
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        digest.update(bytes.fromhex(file_sha256(path)))
        digest.update(b"\0")
        file_count += 1
    if file_count == 0:
        msg = "The bundled tool resource tree is empty."
        raise ToolResourceError(msg)
    return digest.hexdigest()


def project_root() -> Path:
    """Locate the source checkout or PyInstaller extraction root."""
    bundled_root = getattr(sys, "_MEIPASS", None)
    if isinstance(bundled_root, str) and bundled_root:
        return Path(bundled_root)
    return Path(__file__).resolve().parents[2]


def load_tool_manifest(root: Path | None = None) -> _ToolManifest:
    """Load the strict versioned tool manifest without accepting extra fields."""
    base = root if root is not None else project_root()
    path = base / _MANIFEST_RELATIVE_PATH
    try:
        return _ToolManifest.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValidationError) as error:
        msg = "The bundled tool manifest is missing or invalid."
        raise ToolResourceError(msg) from error


def resolve_exiftool(
    *,
    root: Path | None = None,
    development: bool = False,
    environment: Mapping[str, str] | None = None,
) -> ExifToolResource:
    """Resolve a verified packaged resource, or an explicit development override."""
    base = root if root is not None else project_root()
    manifest = load_tool_manifest(base)
    key = platform_key()
    packaged = manifest.exiftool.packaged.get(key)
    if packaged is not None and packaged.available:
        return _resolve_packaged(base, manifest.exiftool.version, packaged)

    if not development:
        msg = "ExifTool is not bundled for this platform."
        raise ToolResourceUnavailableError(msg)

    values = environment if environment is not None else os.environ
    explicit_path = values.get("DOCMETA_EXIFTOOL")
    if not explicit_path:
        msg = "Set DOCMETA_EXIFTOOL for development use."
        raise ToolResourceUnavailableError(msg)
    return _resolve_development(
        Path(explicit_path),
        manifest.exiftool.version,
        values,
    )


def resolve_apache_worker(
    *,
    root: Path | None = None,
    development: bool = False,
    environment: Mapping[str, str] | None = None,
) -> ApacheWorkerResource:
    """Resolve the bundled Java worker or explicit development paths."""
    base = root if root is not None else project_root()
    manifest = load_tool_manifest(base)
    apache = manifest.apache_worker
    if apache is None:
        msg = "The Apache worker is absent from the tool manifest."
        raise ToolResourceUnavailableError(msg)
    packaged = apache.packaged.get(platform_key())
    if packaged is not None and packaged.available:
        return _resolve_packaged_apache(base, apache, packaged)
    if not development:
        msg = "The Apache worker is not bundled for this platform."
        raise ToolResourceUnavailableError(msg)

    values = environment if environment is not None else os.environ
    java_text = values.get("DOCMETA_JAVA")
    jar_text = values.get("DOCMETA_APACHE_WORKER_JAR")
    if not java_text or not jar_text:
        msg = "Set DOCMETA_JAVA and DOCMETA_APACHE_WORKER_JAR for development."
        raise ToolResourceUnavailableError(msg)
    java = Path(java_text).expanduser().resolve()
    worker_jar = Path(jar_text).expanduser().resolve()
    _require_regular_file(java, "The explicit development Java path is invalid.")
    _require_regular_file(
        worker_jar,
        "The explicit development Apache worker path is invalid.",
    )
    _require_java_version(java, apache.java_major_version, worker_jar.parent)
    return ApacheWorkerResource(
        java_executable=java,
        worker_jar=worker_jar,
        tika_version=apache.tika_version,
        java_major_version=apache.java_major_version,
        source="development_override",
    )


def _resolve_packaged_apache(
    root: Path,
    manifest: _ApacheManifest,
    resource: _ApachePackagedResource,
) -> ApacheWorkerResource:
    if not resource.java or not resource.worker_jar or not resource.files:
        msg = "The packaged Apache worker manifest entry is incomplete."
        raise ToolResourceError(msg)
    for relative_path, expected_hash in resource.files.items():
        if file_sha256(_safe_resource_path(root, relative_path)) != expected_hash:
            msg = "A packaged Apache worker resource failed its integrity check."
            raise ToolResourceError(msg)
    if resource.java not in resource.files or resource.worker_jar not in resource.files:
        msg = "The packaged Apache command is not fully covered by hashes."
        raise ToolResourceError(msg)
    java = _safe_resource_path(root, resource.java)
    worker_jar = _safe_resource_path(root, resource.worker_jar)
    _require_java_version(
        java,
        manifest.java_major_version,
        worker_jar.parent,
        expected_vendor=manifest.java_vendor,
        expected_runtime_version=manifest.java_runtime_version,
    )
    return ApacheWorkerResource(
        java_executable=java,
        worker_jar=worker_jar,
        tika_version=manifest.tika_version,
        java_major_version=manifest.java_major_version,
        source="packaged",
    )


def _resolve_packaged(
    root: Path,
    version: str,
    resource: _PackagedResource,
) -> ExifToolResource:
    if not resource.command or not resource.files:
        msg = "The packaged ExifTool manifest entry is incomplete."
        raise ToolResourceError(msg)
    for relative_path, expected_hash in resource.files.items():
        path = _safe_resource_path(root, relative_path)
        if file_sha256(path) != expected_hash:
            msg = "A packaged ExifTool resource failed its integrity check."
            raise ToolResourceError(msg)
    command = tuple(str(_safe_resource_path(root, item)) for item in resource.command)
    if any(item not in resource.files for item in resource.command):
        msg = "The packaged ExifTool command is not fully covered by hashes."
        raise ToolResourceError(msg)
    _require_version(command, version, root)
    return ExifToolResource(command_prefix=command, version=version, source="packaged")


def _resolve_development(
    path: Path,
    version: str,
    environment: Mapping[str, str],
) -> ExifToolResource:
    candidate = path.expanduser().resolve()
    if candidate.is_symlink() or not candidate.is_file():
        msg = "The explicit development ExifTool path is invalid."
        raise ToolResourceUnavailableError(msg)
    command = _development_command(candidate, environment)
    _require_version(command, version, candidate.parent)
    return ExifToolResource(
        command_prefix=command,
        version=version,
        source="development_override",
    )


def _development_command(
    candidate: Path,
    environment: Mapping[str, str],
) -> tuple[str, ...]:
    try:
        header = candidate.read_bytes()[:128]
    except OSError as error:
        msg = "The explicit development ExifTool path could not be read."
        raise ToolResourceError(msg) from error
    if b"perl" not in header.partition(b"\n")[0].lower():
        return (str(candidate),)

    explicit_perl = environment.get("DOCMETA_PERL")
    perl = explicit_perl or shutil.which("perl")
    if not perl:
        msg = "Perl is required only for this development ExifTool source tree."
        raise ToolResourceUnavailableError(msg)
    perl_path = Path(perl).expanduser().resolve()
    if perl_path.is_symlink() or not perl_path.is_file():
        msg = "The explicit development Perl path is invalid."
        raise ToolResourceUnavailableError(msg)
    return (str(perl_path), str(candidate))


def _require_version(command: tuple[str, ...], version: str, cwd: Path) -> None:
    environment = {
        "HOME": str(cwd),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TZ": "UTC",
    }
    try:
        result = subprocess.run(  # noqa: S603
            (*command, "-ver"),
            cwd=cwd,
            env=environment,
            check=False,
            capture_output=True,
            timeout=_VERSION_TIMEOUT_SECONDS,
            creationflags=hidden_subprocess_creation_flags(),
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        msg = "ExifTool could not be started."
        raise ToolResourceUnavailableError(msg) from error
    try:
        observed = result.stdout.decode("ascii", errors="strict").strip()
    except UnicodeDecodeError as error:
        msg = "ExifTool returned an invalid version."
        raise ToolResourceError(msg) from error
    if result.returncode != 0 or observed != version:
        msg = "The ExifTool version does not match the locked build version."
        raise ToolResourceError(msg)


def _require_regular_file(path: Path, message: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise ToolResourceUnavailableError(message)


def _require_java_version(
    java: Path,
    expected_major: int,
    cwd: Path,
    *,
    expected_vendor: str | None = None,
    expected_runtime_version: str | None = None,
) -> None:
    environment = {
        "HOME": str(cwd),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TZ": "UTC",
    }
    for name in ("SYSTEMROOT", "WINDIR"):
        value = os.environ.get(name)
        if value:
            environment[name] = value
    try:
        result = subprocess.run(  # noqa: S603
            (str(java), "-XshowSettings:properties", "-version"),
            cwd=cwd,
            env=environment,
            check=False,
            capture_output=True,
            timeout=_VERSION_TIMEOUT_SECONDS,
            creationflags=hidden_subprocess_creation_flags(),
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        msg = "The Java runtime for the Apache worker could not be started."
        raise ToolResourceUnavailableError(msg) from error
    output = (result.stdout + result.stderr).decode("utf-8", errors="replace")
    match = re.search(r'version\s+"(\d+)(?:[.]|\")', output)
    if result.returncode != 0 or match is None or int(match.group(1)) != expected_major:
        msg = "The Java runtime version does not match the locked worker version."
        raise ToolResourceError(msg)
    if expected_vendor is not None and f"java.vendor = {expected_vendor}" not in output:
        msg = "The Java runtime vendor does not match the locked release vendor."
        raise ToolResourceError(msg)
    if expected_runtime_version is not None:
        runtime_match = re.search(r"java[.]runtime[.]version\s*=\s*(\S+)", output)
        if runtime_match is None or not runtime_match.group(1).startswith(
            expected_runtime_version
        ):
            msg = "The Java runtime patch version does not match the locked release."
            raise ToolResourceError(msg)


def _safe_resource_path(root: Path, relative_text: str) -> Path:
    relative = Path(relative_text)
    if relative.is_absolute() or ".." in relative.parts:
        msg = "The bundled tool manifest contains an unsafe path."
        raise ToolResourceError(msg)
    base = root.resolve()
    candidate = (base / relative).resolve()
    if not candidate.is_relative_to(base):
        msg = "The bundled tool manifest path escapes the application."
        raise ToolResourceError(msg)
    return candidate


__all__ = (
    "ApacheWorkerResource",
    "ExifToolResource",
    "ToolResourceError",
    "ToolResourceUnavailableError",
    "file_sha256",
    "load_tool_manifest",
    "platform_key",
    "project_root",
    "resolve_apache_worker",
    "resolve_exiftool",
    "tree_sha256",
)
