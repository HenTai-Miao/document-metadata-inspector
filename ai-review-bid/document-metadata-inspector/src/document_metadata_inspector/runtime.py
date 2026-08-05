"""Resolve verified parser engines for source checkouts and frozen applications."""

from __future__ import annotations

import os
import platform
import shutil
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from document_metadata_inspector.models import FrozenModel
from document_metadata_inspector.resources import (
    ToolResourceError,
    ToolResourceUnavailableError,
    project_root,
    resolve_apache_worker,
    resolve_exiftool,
)
from document_metadata_inspector.scanner import Scanner
from document_metadata_inspector.workers.apache import ApacheWorker
from document_metadata_inspector.workers.exiftool import ExifToolWorker

if TYPE_CHECKING:
    from collections.abc import Mapping


class RuntimeComponentStatus(StrEnum):
    """Describe whether one version-locked parser engine can run."""

    READY = "ready"
    UNAVAILABLE = "unavailable"
    INVALID = "invalid"


class RuntimeComponent(FrozenModel):
    """Expose a sanitized parser-runtime readiness result."""

    name: str
    version: str
    status: RuntimeComponentStatus
    source: str | None = None
    message: str | None = None


@dataclass(frozen=True, slots=True)
class RuntimeEnvironment:
    """Hold the ready scanner and its independently resolved components."""

    scanner: Scanner
    components: tuple[RuntimeComponent, ...]

    @property
    def warnings(self) -> tuple[str, ...]:
        """Return stable report warnings for every unavailable component."""
        return tuple(
            f"runtime_component:{item.name}:{item.status.value}"
            for item in self.components
            if item.status is not RuntimeComponentStatus.READY
        )

    @property
    def ready(self) -> bool:
        """Report whether every optional corroborating engine is ready."""
        return all(
            item.status is RuntimeComponentStatus.READY for item in self.components
        )


def _first_executable(
    values: Mapping[str, str],
    variable: str,
    executable_name: str,
) -> str | None:
    explicit = values.get(variable)
    if explicit:
        return explicit
    return shutil.which(executable_name, path=values.get("PATH"))


def _development_values(
    root: Path,
    environment: Mapping[str, str],
) -> dict[str, str]:
    values = dict(environment)
    exiftool = root / "tools/vendor/exiftool/13.55/source/exiftool"
    if "DOCMETA_EXIFTOOL" not in values and exiftool.is_file():
        values["DOCMETA_EXIFTOOL"] = str(exiftool)
    if "DOCMETA_PERL" not in values:
        perl = _first_executable(values, "DOCMETA_PERL", "perl")
        if perl:
            values["DOCMETA_PERL"] = perl

    worker_jar = root / "java-worker/target/document-metadata-apache-worker.jar"
    if "DOCMETA_APACHE_WORKER_JAR" not in values and worker_jar.is_file():
        values["DOCMETA_APACHE_WORKER_JAR"] = str(worker_jar)
    return values


def _java_candidates(values: Mapping[str, str]) -> tuple[str, ...]:
    explicit = values.get("DOCMETA_JAVA")
    if explicit:
        return (explicit,)

    executable = "java.exe" if os.name == "nt" else "java"
    candidates: list[Path] = []
    java_home = values.get("JAVA_HOME")
    if java_home:
        candidates.append(Path(java_home) / "bin" / executable)

    sdkman_directory = Path(values.get("SDKMAN_DIR", str(Path.home() / ".sdkman")))
    candidates.extend(
        sorted(
            (sdkman_directory / "candidates/java").glob(f"*/bin/{executable}"),
            key=lambda item: item.as_posix(),
        )
    )
    system = platform.system().casefold()
    if system == "darwin":
        candidates.extend(
            sorted(
                Path("/Library/Java/JavaVirtualMachines").glob(
                    f"*/Contents/Home/bin/{executable}"
                ),
                key=lambda item: item.as_posix(),
            )
        )
    elif system == "linux":
        candidates.extend(
            sorted(
                Path("/usr/lib/jvm").glob(f"*/bin/{executable}"),
                key=lambda item: item.as_posix(),
            )
        )
    discovered = shutil.which(executable, path=values.get("PATH"))
    if discovered:
        candidates.append(Path(discovered))

    unique: dict[str, None] = {}
    for candidate in candidates:
        if candidate.is_file():
            unique.setdefault(str(candidate.resolve()), None)
    return tuple(unique)


def _component_error(
    name: str,
    version: str,
    error: ToolResourceError,
) -> RuntimeComponent:
    status = (
        RuntimeComponentStatus.UNAVAILABLE
        if isinstance(error, ToolResourceUnavailableError)
        else RuntimeComponentStatus.INVALID
    )
    return RuntimeComponent(
        name=name,
        version=version,
        status=status,
        message=str(error),
    )


def create_runtime(
    *,
    root: Path | None = None,
    development: bool | None = None,
    environment: Mapping[str, str] | None = None,
) -> RuntimeEnvironment:
    """Build a scanner from packaged resources or locked development artifacts."""
    base = root if root is not None else project_root()
    is_development = (
        not bool(getattr(sys, "frozen", False)) if development is None else development
    )
    supplied = environment if environment is not None else os.environ
    values = _development_values(base, supplied) if is_development else dict(supplied)

    apache_worker: ApacheWorker | None = None
    apache_error: ToolResourceError | None = None
    java_candidates = _java_candidates(values) if is_development else ("",)
    if not java_candidates:
        java_candidates = ("",)
    for java_candidate in java_candidates:
        candidate_values = dict(values)
        if java_candidate:
            candidate_values["DOCMETA_JAVA"] = java_candidate
        try:
            apache_resource = resolve_apache_worker(
                root=base,
                development=is_development,
                environment=candidate_values,
            )
            apache_worker = ApacheWorker.from_runtime(
                apache_resource.java_executable,
                apache_resource.worker_jar,
            )
            apache_component = RuntimeComponent(
                name="apache-tika",
                version=apache_resource.tika_version,
                status=RuntimeComponentStatus.READY,
                source=apache_resource.source,
            )
            break
        except ToolResourceError as error:
            apache_error = error
    else:
        if apache_error is None:
            apache_error = ToolResourceUnavailableError(
                "No Java runtime candidate was discovered for development."
            )
        apache_component = _component_error("apache-tika", "3.3.2", apache_error)

    exiftool_worker: ExifToolWorker | None = None
    try:
        exiftool_resource = resolve_exiftool(
            root=base,
            development=is_development,
            environment=values,
        )
        exiftool_worker = ExifToolWorker(
            command_prefix=exiftool_resource.command_prefix,
            version=exiftool_resource.version,
        )
        exiftool_component = RuntimeComponent(
            name="exiftool",
            version=exiftool_resource.version,
            status=RuntimeComponentStatus.READY,
            source=exiftool_resource.source,
        )
    except ToolResourceError as error:
        exiftool_component = _component_error("exiftool", "13.55", error)

    return RuntimeEnvironment(
        scanner=Scanner(
            apache_worker=apache_worker,
            exiftool_worker=exiftool_worker,
        ),
        components=(apache_component, exiftool_component),
    )


__all__ = (
    "RuntimeComponent",
    "RuntimeComponentStatus",
    "RuntimeEnvironment",
    "create_runtime",
)
