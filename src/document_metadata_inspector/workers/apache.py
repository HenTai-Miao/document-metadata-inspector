"""Killable JSON adapter for the bundled Apache Tika/POI/PDFBox worker."""

from __future__ import annotations

import json
import os
import re
import subprocess
from contextlib import suppress
from dataclasses import dataclass, field, replace
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from time import monotonic
from typing import TYPE_CHECKING, ClassVar, Literal, cast
from uuid import uuid4

import psutil
from pydantic import Field, ValidationError

from document_metadata_inspector.errors import ErrorCode
from document_metadata_inspector.models import (
    EmbeddedDocumentReport,
    EvidenceObservation,
    FrozenModel,
    JsonValue,
    ParserRun,
    ParserStatus,
)
from document_metadata_inspector.normalization import normalize_evidence_value
from document_metadata_inspector.subprocesses import hidden_subprocess_creation_flags

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import BinaryIO

    from document_metadata_inspector.models import InspectionLimits
    from document_metadata_inspector.source import SourceSnapshot

    type PasswordProvider = Callable[[str], str | None]

_READ_CHUNK_BYTES = 64 * 1024
_MAX_STDERR_BYTES = 64 * 1024
_MIN_JAVA_HEAP_MEBIBYTES = 128
_SAFE_SUFFIX = re.compile(r"\.[a-z0-9]{1,8}\Z", re.IGNORECASE)
_EMBEDDED_KEY = re.compile(r"embedded\[(\d+)]\.(.+)\Z")


def _process_tree_rss(process_id: int) -> int | None:
    try:
        root = psutil.Process(process_id)
        processes = (root, *root.children(recursive=True))
    except psutil.NoSuchProcess:
        return 0
    except psutil.Error:
        return None
    total = 0
    for process in processes:
        try:
            total += cast("int", process.memory_info().rss)
        except psutil.NoSuchProcess:
            continue
        except psutil.Error:
            return None
    return total


class _EmbeddedResource(FrozenModel):
    resource_id: str = ""
    parent_id: str = ""
    depth: int = 1
    path: str
    content_type: str
    size_bytes: int
    sha256: str = ""


class _WorkerError(FrozenModel):
    code: str
    message: str


class _WorkerResponse(FrozenModel):
    request_id: str
    status: Literal["ok", "partial", "failed"]
    content_type: str | None = None
    metadata: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    embedded_resources: tuple[_EmbeddedResource, ...] = ()
    warnings: tuple[str, ...] = ()
    error: _WorkerError | None = None


@dataclass(slots=True)
class _Capture:
    limit: int
    data: bytearray = field(default_factory=bytearray)
    exceeded: bool = False


@dataclass(frozen=True, slots=True)
class _AttemptContext:
    staged_path: Path
    task_directory: Path
    limits: InspectionLimits
    started: float
    source_sha256: str


@dataclass(frozen=True, slots=True)
class _ProcessExit:
    return_code: int
    timed_out: bool = False
    memory_exceeded: bool = False


@dataclass(frozen=True, slots=True)
class ApacheWorker:
    """Run one metadata-only Apache parse in a separately killable process."""

    command: tuple[str, ...]
    version: str = "3.3.2"
    parser_name: ClassVar[str] = "apache-tika"

    def __post_init__(self) -> None:
        """Require an explicit executable and argument vector."""
        if not self.command or any(not argument for argument in self.command):
            msg = "the Apache worker command must not be empty"
            raise ValueError(msg)

    @classmethod
    def from_runtime(
        cls,
        java_executable: Path,
        worker_jar: Path,
        *,
        max_heap_megabytes: int = 512,
    ) -> ApacheWorker:
        """Build a bounded command for an app-bundled Java runtime and worker JAR."""
        if max_heap_megabytes < _MIN_JAVA_HEAP_MEBIBYTES:
            msg = "the Apache worker heap must be at least 128 MiB"
            raise ValueError(msg)
        return cls(
            command=(
                str(java_executable),
                "-Xms32m",
                f"-Xmx{max_heap_megabytes}m",
                "-Djava.security.manager=allow",
                "-Djava.awt.headless=true",
                "-Dfile.encoding=UTF-8",
                "-jar",
                str(worker_jar),
            )
        )

    def scan(
        self,
        snapshot: SourceSnapshot,
        password_provider: PasswordProvider | None,
        limits: InspectionLimits,
    ) -> ParserRun:
        """Stage the immutable stream, invoke the worker and validate its response."""
        started = monotonic()
        with TemporaryDirectory(prefix="docmeta-apache-") as task_directory:
            staged_path = Path(task_directory) / self._staged_name(snapshot.name)
            if not self._stage_snapshot(snapshot, staged_path):
                return self._failure(
                    ErrorCode.SOURCE_CHANGED,
                    started,
                    "The immutable source snapshot could not be staged safely.",
                )
            task_path = Path(task_directory)
            context = _AttemptContext(
                staged_path=staged_path,
                task_directory=task_path,
                limits=limits,
                started=started,
                source_sha256=snapshot.sha256,
            )
            run = self._attempt(context, None)
            if not self._matches_snapshot(staged_path, snapshot):
                return self._failure(
                    ErrorCode.SOURCE_CHANGED,
                    started,
                    "The staged source changed while the Apache parser was running.",
                )
            if (
                run.error_code != ErrorCode.PASSWORD_REQUIRED.value
                or password_provider is None
            ):
                return run
            password = password_provider(snapshot.name)
            if password is None:
                return run
            retry = self._attempt(context, password)
            password = None
            if not self._matches_snapshot(staged_path, snapshot):
                return self._failure(
                    ErrorCode.SOURCE_CHANGED,
                    started,
                    "The staged source changed while the Apache parser was running.",
                )
            return retry

    def _attempt(
        self,
        context: _AttemptContext,
        password: str | None,
    ) -> ParserRun:
        remaining = context.limits.parser_timeout_seconds - (
            monotonic() - context.started
        )
        if remaining <= 0:
            return self._failure(
                ErrorCode.PARSER_TIMEOUT,
                context.started,
                "The Apache metadata parser exceeded its total time limit.",
                status=ParserStatus.TIMED_OUT,
            )
        attempt_limits = replace(
            context.limits,
            parser_timeout_seconds=remaining,
        )
        request_id = uuid4().hex
        request = {
            "request_id": request_id,
            "path": str(context.staged_path),
            "source_sha256": context.source_sha256,
            "password_token": password,
            "limits": {
                "max_output_bytes": context.limits.max_worker_output_bytes,
                "max_embedded_depth": context.limits.max_embedded_depth,
                "max_embedded_resources": context.limits.max_embedded_resources,
                "max_embedded_total_bytes": context.limits.max_embedded_total_bytes,
            },
        }
        request_bytes = bytearray(
            json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode()
        )
        password = None
        request.clear()
        try:
            outcome = self._invoke(
                request_bytes,
                context.task_directory,
                attempt_limits,
            )
        finally:
            request_bytes[:] = b"\x00" * len(request_bytes)
        if isinstance(outcome, ParserRun):
            return outcome.model_copy(
                update={"duration_ms": self._duration_ms(context.started)},
            )
        return self._response_to_run(outcome, request_id, context.started)

    def _invoke(
        self,
        request_bytes: bytearray,
        task_directory: Path,
        limits: InspectionLimits,
    ) -> _WorkerResponse | ParserRun:
        stdout = _Capture(limits.max_worker_output_bytes)
        stderr = _Capture(min(limits.max_worker_output_bytes, _MAX_STDERR_BYTES))
        try:
            process = subprocess.Popen(  # noqa: S603
                self.command,
                cwd=task_directory,
                env=self._worker_environment(task_directory),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=hidden_subprocess_creation_flags(),
            )
        except OSError:
            return self._failure(
                ErrorCode.PARSER_UNAVAILABLE,
                monotonic(),
                "The bundled Apache metadata parser is unavailable.",
                status=ParserStatus.SKIPPED,
            )

        stdout_pipe = process.stdout
        stderr_pipe = process.stderr
        stdin_pipe = process.stdin
        if stdout_pipe is None or stderr_pipe is None or stdin_pipe is None:
            self._kill(process)
            _ = process.wait()
            return self._failure(
                ErrorCode.PARSER_CRASHED,
                monotonic(),
                "The Apache metadata parser pipes were unavailable.",
            )
        stdout_thread = Thread(
            target=self._drain,
            args=(stdout_pipe, stdout, process),
            daemon=True,
        )
        stderr_thread = Thread(
            target=self._drain,
            args=(stderr_pipe, stderr, process),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

        try:
            _ = stdin_pipe.write(request_bytes)
            _ = stdin_pipe.write(b"\n")
            stdin_pipe.close()
        except (BrokenPipeError, OSError):
            pass

        try:
            process_exit = self._wait_for_process(process, limits)
        finally:
            stdout_thread.join(timeout=2)
            stderr_thread.join(timeout=2)
            stdout_pipe.close()
            stderr_pipe.close()

        return self._interpret_process(process_exit, stdout, stderr)

    def _wait_for_process(
        self,
        process: subprocess.Popen[bytes],
        limits: InspectionLimits,
    ) -> _ProcessExit:
        deadline = monotonic() + limits.parser_timeout_seconds
        while True:
            remaining = deadline - monotonic()
            if remaining <= 0:
                self._kill(process)
                return _ProcessExit(process.wait(), timed_out=True)
            try:
                return _ProcessExit(process.wait(timeout=min(0.05, remaining)))
            except subprocess.TimeoutExpired:
                rss = _process_tree_rss(process.pid)
                if rss is None or rss > limits.max_worker_memory_bytes:
                    self._kill(process)
                    return _ProcessExit(process.wait(), memory_exceeded=True)

    def _interpret_process(
        self,
        process_exit: _ProcessExit,
        stdout: _Capture,
        stderr: _Capture,
    ) -> _WorkerResponse | ParserRun:
        if process_exit.timed_out:
            return self._failure(
                ErrorCode.PARSER_TIMEOUT,
                monotonic(),
                "The Apache metadata parser exceeded its time limit.",
                status=ParserStatus.TIMED_OUT,
            )
        if process_exit.memory_exceeded:
            return self._failure(
                ErrorCode.RESOURCE_LIMIT_EXCEEDED,
                monotonic(),
                "The Apache metadata parser exceeded its memory limit.",
            )
        if stdout.exceeded or stderr.exceeded:
            return self._failure(
                ErrorCode.RESOURCE_LIMIT_EXCEEDED,
                monotonic(),
                "The Apache metadata parser exceeded its output limit.",
            )
        if process_exit.return_code != 0:
            return self._failure(
                ErrorCode.PARSER_CRASHED,
                monotonic(),
                "The Apache metadata parser exited unexpectedly.",
            )
        return self._parse_response(bytes(stdout.data))

    def _parse_response(self, payload: bytes) -> _WorkerResponse | ParserRun:
        try:
            text = payload.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            return self._failure(
                ErrorCode.PARSER_OUTPUT_INVALID,
                monotonic(),
                "The Apache metadata parser returned an invalid response.",
            )
        lines = text.splitlines()
        if len(lines) != 1 or not lines[0].strip():
            return self._failure(
                ErrorCode.PARSER_OUTPUT_INVALID,
                monotonic(),
                "The Apache metadata parser returned an invalid response.",
            )
        try:
            return _WorkerResponse.model_validate_json(lines[0])
        except (ValueError, ValidationError):
            return self._failure(
                ErrorCode.PARSER_OUTPUT_INVALID,
                monotonic(),
                "The Apache metadata parser returned an invalid response.",
            )

    def _response_to_run(
        self,
        response: _WorkerResponse,
        request_id: str,
        started: float,
    ) -> ParserRun:
        if response.request_id != request_id:
            return self._failure(
                ErrorCode.PARSER_OUTPUT_INVALID,
                started,
                "The Apache metadata parser returned a mismatched response.",
            )
        if response.status == "failed":
            code = (
                response.error.code if response.error is not None else "parser_crashed"
            )
            return ParserRun(
                parser_name=self.parser_name,
                parser_version=self.version,
                status=ParserStatus.FAILED,
                warnings=tuple(response.warnings),
                error_code=code,
                duration_ms=self._duration_ms(started),
            )

        observations, embedded_documents = self._metadata_evidence(response)
        status = (
            ParserStatus.PARTIAL
            if response.status == "partial" or response.warnings
            else ParserStatus.SUCCEEDED
        )
        return ParserRun(
            parser_name=self.parser_name,
            parser_version=self.version,
            status=status,
            observations=observations,
            warnings=response.warnings,
            duration_ms=self._duration_ms(started),
            embedded_documents=embedded_documents,
        )

    def _metadata_evidence(
        self,
        response: _WorkerResponse,
    ) -> tuple[tuple[EvidenceObservation, ...], tuple[EmbeddedDocumentReport, ...]]:
        root_observations: list[EvidenceObservation] = []
        embedded_observations: dict[int, list[EvidenceObservation]] = {}
        for raw_name, values in response.metadata.items():
            match = _EMBEDDED_KEY.fullmatch(raw_name)
            canonical_name = self._canonical_name(match.group(2) if match else raw_name)
            target = root_observations
            location = "root"
            source_kind = "apache_tika"
            if match is not None:
                index = int(match.group(1))
                target = embedded_observations.setdefault(index, [])
                location = f"embedded[{index}]"
                source_kind = "apache_tika_embedded"
            target.extend(
                EvidenceObservation(
                    canonical_name=canonical_name,
                    raw_name=raw_name,
                    raw_value=value,
                    normalized_value=normalize_evidence_value(canonical_name, value),
                    value_type="string",
                    source_kind=source_kind,
                    location=location,
                    parser_name=self.parser_name,
                    parser_version=self.version,
                )
                for value in values
            )
        for resource in response.embedded_resources:
            raw_value: dict[str, JsonValue] = {
                "path": resource.path,
                "content_type": resource.content_type,
                "size_bytes": resource.size_bytes,
            }
            if resource.resource_id and resource.parent_id and resource.sha256:
                raw_value.update(
                    {
                        "resource_id": resource.resource_id,
                        "parent_id": resource.parent_id,
                        "depth": resource.depth,
                        "sha256": resource.sha256,
                    }
                )
            root_observations.append(
                EvidenceObservation(
                    canonical_name="embedded_resource",
                    raw_name="embedded_resource",
                    raw_value=raw_value,
                    normalized_value=raw_value,
                    value_type="embedded_resource_descriptor",
                    source_kind="apache_tika_embedded",
                    location=resource.path,
                    parser_name=self.parser_name,
                    parser_version=self.version,
                )
            )

        children: list[EmbeddedDocumentReport] = []
        for index, resource in enumerate(response.embedded_resources):
            values = tuple(embedded_observations.pop(index, ()))
            if (
                not resource.resource_id
                or not resource.parent_id
                or not resource.sha256
            ):
                root_observations.extend(
                    self._legacy_embedded_observation(item) for item in values
                )
                continue
            children.append(
                EmbeddedDocumentReport(
                    resource_id=resource.resource_id,
                    parent_id=resource.parent_id,
                    depth=resource.depth,
                    path=resource.path,
                    content_type=resource.content_type,
                    size_bytes=resource.size_bytes,
                    sha256=resource.sha256,
                    parser_names=(self.parser_name,),
                    observations=tuple(
                        item.model_copy(update={"location": resource.path})
                        for item in values
                    ),
                )
            )
        for values in embedded_observations.values():
            root_observations.extend(
                self._legacy_embedded_observation(item) for item in values
            )
        return tuple(root_observations), tuple(children)

    @staticmethod
    def _legacy_embedded_observation(
        observation: EvidenceObservation,
    ) -> EvidenceObservation:
        embedded_name = observation.canonical_name.removeprefix("apache_tika.")
        return observation.model_copy(
            update={"canonical_name": f"apache_tika.embedded.{embedded_name}"}
        )

    @staticmethod
    def _canonical_name(raw_name: str) -> str:
        lowered = raw_name.casefold()
        aliases = {
            "author": "author",
            "creator": "author",
            "dc:creator": "author",
            "meta:author": "author",
            "office:initial-author": "author",
            "last-author": "last_modified_by",
            "meta:last-author": "last_modified_by",
            "modifier": "last_modified_by",
            "dc:title": "title",
            "title": "title",
            "dc:subject": "subject",
            "subject": "subject",
            "dc:description": "description",
            "description": "description",
            "keywords": "keywords",
            "dcterms:created": "created_at",
            "creation-date": "created_at",
            "dcterms:modified": "modified_at",
            "last-save-date": "modified_at",
            "company": "company",
            "manager": "manager",
            "application-name": "application",
        }
        if lowered in aliases:
            return aliases[lowered]
        if lowered.startswith("pdf:docinfo:author"):
            return "author"
        safe_name = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
        return f"apache_tika.{safe_name or 'unknown'}"

    @staticmethod
    def _staged_name(source_name: str) -> str:
        suffix = Path(source_name).suffix
        if _SAFE_SUFFIX.fullmatch(suffix):
            return f"source{suffix.casefold()}"
        return "source.bin"

    @staticmethod
    def _stage_snapshot(snapshot: SourceSnapshot, destination: Path) -> bool:
        stream = snapshot.stream
        original_position: int | None = None
        try:
            original_position = stream.tell()
            _ = stream.seek(0)
            digest = sha256()
            copied = 0
            with destination.open("xb") as output:
                destination.chmod(0o600)
                while chunk := stream.read(_READ_CHUNK_BYTES):
                    copied += len(chunk)
                    if copied > snapshot.size_bytes:
                        return False
                    digest.update(chunk)
                    _ = output.write(chunk)
            return (
                copied == snapshot.size_bytes and digest.hexdigest() == snapshot.sha256
            )
        except OSError:
            return False
        finally:
            if original_position is not None:
                with suppress(OSError):
                    _ = stream.seek(original_position)

    @staticmethod
    def _matches_snapshot(path: Path, snapshot: SourceSnapshot) -> bool:
        try:
            if path.stat().st_size != snapshot.size_bytes:
                return False
            digest = sha256()
            with path.open("rb") as stream:
                while chunk := stream.read(_READ_CHUNK_BYTES):
                    digest.update(chunk)
            return digest.hexdigest() == snapshot.sha256
        except OSError:
            return False

    @staticmethod
    def _worker_environment(task_directory: Path) -> dict[str, str]:
        environment = {
            "HOME": str(task_directory),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "TEMP": str(task_directory),
            "TMP": str(task_directory),
            "TMPDIR": str(task_directory),
            "TZ": "UTC",
        }
        for name in ("SYSTEMROOT", "WINDIR"):
            value = os.environ.get(name)
            if value:
                environment[name] = value
        return environment

    @staticmethod
    def _drain(
        stream: BinaryIO,
        capture: _Capture,
        process: subprocess.Popen[bytes],
    ) -> None:
        while chunk := stream.read(_READ_CHUNK_BYTES):
            remaining = capture.limit - len(capture.data)
            if len(chunk) > remaining:
                capture.data.extend(chunk[: max(remaining, 0)])
                capture.exceeded = True
                ApacheWorker._kill(process)
                return
            capture.data.extend(chunk)

    @staticmethod
    def _kill(process: subprocess.Popen[bytes]) -> None:
        with suppress(OSError):
            process.kill()

    def _failure(
        self,
        code: ErrorCode,
        started: float,
        message: str,
        *,
        status: ParserStatus = ParserStatus.FAILED,
    ) -> ParserRun:
        return ParserRun(
            parser_name=self.parser_name,
            parser_version=self.version,
            status=status,
            warnings=(message,),
            error_code=code.value,
            duration_ms=self._duration_ms(started),
        )

    @staticmethod
    def _duration_ms(started: float) -> int:
        return max(0, round((monotonic() - started) * 1_000))


__all__ = ("ApacheWorker",)
