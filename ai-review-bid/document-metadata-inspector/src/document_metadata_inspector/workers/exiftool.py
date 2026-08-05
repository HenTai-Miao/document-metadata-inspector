"""Read-only, bounded adapter for the bundled ExifTool metadata worker."""

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
from typing import TYPE_CHECKING, ClassVar, cast

from document_metadata_inspector.errors import ErrorCode
from document_metadata_inspector.models import (
    EmbeddedDocumentReport,
    EvidenceObservation,
    JsonValue,
    ParserRun,
    ParserStatus,
)
from document_metadata_inspector.normalization import normalize_evidence_value

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import BinaryIO

    from document_metadata_inspector.models import InspectionLimits
    from document_metadata_inspector.source import SourceSnapshot

    type PasswordProvider = Callable[[str], str | None]

_READ_CHUNK_BYTES = 64 * 1024
_MAX_STDERR_BYTES = 64 * 1024
_SAFE_SUFFIX = re.compile(r"\.[a-z0-9]{1,8}\Z", re.IGNORECASE)
_VERSION_TAG = "ExifTool:ExifToolVersion"
_EXPECTED_VERSION = "13.55"
_FIXED_ARGUMENTS = (
    "-json",
    "-a",
    "-u",
    "-U",
    "-G3:1",
    "-struct",
    "-ee3",
    "-api",
    "RequestAll=3",
    "-api",
    "LargeFileSupport=1",
    "--System:all",
    "--MacOS:all",
    "--ExifTool:Now",
    "--ExifTool:NewGUID",
    "--ExifTool:FileSequence",
    "--ExifTool:ProcessingTime",
    "-@",
    "-",
)
_IGNORED_TAGS = frozenset({"SourceFile", _VERSION_TAG})
_DOCUMENT_GROUP = re.compile(r"Doc\d+\Z", re.IGNORECASE)
_ROOT_OFFICE_METADATA_PARTS = frozenset(
    {
        "docprops/app.xml",
        "docprops/core.xml",
        "docprops/custom.xml",
    }
)
_EMBEDDED_PATH_SEGMENTS = frozenset(
    {"attachments", "embedded", "embeddedfiles", "embeddings", "media"}
)
_EMBEDDED_DOCUMENT_SUFFIXES = frozenset(
    {
        ".doc",
        ".docm",
        ".docx",
        ".dot",
        ".dotm",
        ".dotx",
        ".pdf",
        ".xls",
        ".xlsb",
        ".xlsm",
        ".xlsx",
        ".xlt",
        ".xltm",
        ".xltx",
    }
)
_CANONICAL_TAGS = {
    "author": "author",
    "creator": "author",
    "initialauthor": "author",
    "lastauthor": "last_modified_by",
    "lastmodifiedby": "last_modified_by",
    "modifier": "last_modified_by",
    "title": "title",
    "subject": "subject",
    "description": "description",
    "comments": "description",
    "keywords": "keywords",
    "category": "category",
    "contentstatus": "content_status",
    "identifier": "identifier",
    "language": "language",
    "revision": "revision",
    "revisionnumber": "revision",
    "createdate": "created_at",
    "creationdate": "created_at",
    "modifydate": "modified_at",
    "modificationdate": "modified_at",
    "lastprinted": "last_printed_at",
    "application": "application",
    "applicationname": "application",
    "appversion": "application_version",
    "company": "company",
    "manager": "manager",
    "template": "template",
    "pagecount": "page_count",
    "wordcount": "word_count",
}


class _JsonObjectPairs(list[tuple[str, object]]):
    """Keep duplicate JSON object keys instead of silently overwriting them."""


@dataclass(slots=True)
class _Capture:
    limit: int
    data: bytearray = field(default_factory=bytearray)
    exceeded: bool = False


@dataclass(frozen=True, slots=True)
class _ProcessOutput:
    return_code: int
    stdout: bytes


@dataclass(frozen=True, slots=True)
class _StagedScan:
    snapshot: SourceSnapshot
    staged_path: Path
    task_directory: Path
    limits: InspectionLimits
    started: float


@dataclass(frozen=True, slots=True)
class ExifToolWorker:
    """Extract raw grouped tags without granting ExifTool write arguments."""

    command_prefix: tuple[str, ...]
    version: str = _EXPECTED_VERSION
    parser_name: ClassVar[str] = "exiftool"

    def __post_init__(self) -> None:
        """Require a trusted executable/launcher prefix."""
        if not self.command_prefix or any(not item for item in self.command_prefix):
            msg = "the ExifTool command prefix must not be empty"
            raise ValueError(msg)

    def build_command(self) -> tuple[str, ...]:
        """Return the immutable read-only command without source or password data."""
        return (*self.command_prefix, *_FIXED_ARGUMENTS)

    def scan(
        self,
        snapshot: SourceSnapshot,
        password_provider: PasswordProvider | None,
        limits: InspectionLimits,
    ) -> ParserRun:
        """Stage, scan and hash-reverify one immutable source snapshot."""
        started = monotonic()
        with TemporaryDirectory(prefix="docmeta-exiftool-") as task_directory_text:
            task_directory = Path(task_directory_text)
            staged_path = task_directory / self._staged_name(snapshot.name)
            if not self._stage_snapshot(snapshot, staged_path):
                return self._failure(
                    ErrorCode.SOURCE_CHANGED,
                    started,
                    "The immutable source snapshot could not be staged safely.",
                )
            return self._scan_staged(
                _StagedScan(
                    snapshot=snapshot,
                    staged_path=staged_path,
                    task_directory=task_directory,
                    limits=limits,
                    started=started,
                ),
                password_provider,
            )

    def _scan_staged(
        self,
        staged: _StagedScan,
        password_provider: PasswordProvider | None,
    ) -> ParserRun:
        """Retry one immutable staged source only after password-required evidence."""
        run = self._attempt(
            staged,
            None,
        )
        if not self._matches_snapshot(staged.staged_path, staged.snapshot):
            return self._failure(
                ErrorCode.SOURCE_CHANGED,
                staged.started,
                "The staged source changed while ExifTool was running.",
            )
        if (
            run.error_code != ErrorCode.PASSWORD_REQUIRED.value
            or password_provider is None
        ):
            return run
        password = password_provider(staged.snapshot.name)
        if password is None:
            return run
        unsafe_password = any(character in password for character in "\r\n\0")
        if unsafe_password:
            return self._failure(
                ErrorCode.UNSUPPORTED_ENCRYPTION,
                staged.started,
                "This password cannot be delivered safely to ExifTool.",
                status=ParserStatus.SKIPPED,
            )
        retry = self._attempt(
            staged,
            password,
        )
        password = None
        if not self._matches_snapshot(staged.staged_path, staged.snapshot):
            return self._failure(
                ErrorCode.SOURCE_CHANGED,
                staged.started,
                "The staged source changed while ExifTool was running.",
            )
        return retry

    def _attempt(
        self,
        staged: _StagedScan,
        password: str | None,
    ) -> ParserRun:
        remaining = staged.limits.parser_timeout_seconds - (
            monotonic() - staged.started
        )
        if remaining <= 0:
            return self._failure(
                ErrorCode.PARSER_TIMEOUT,
                staged.started,
                "ExifTool exceeded its total time limit.",
                status=ParserStatus.TIMED_OUT,
            )
        attempt_limits = replace(
            staged.limits,
            parser_timeout_seconds=remaining,
        )
        arguments: list[str] = []
        if password is not None:
            arguments.extend(("-password", password))
        arguments.extend(("--", str(staged.staged_path)))
        stdin_bytes = bytearray(("\n".join(arguments) + "\n").encode("utf-8"))
        password_used = password is not None
        password = None
        arguments.clear()
        try:
            outcome = self._invoke(
                stdin_bytes,
                staged.task_directory,
                attempt_limits,
                staged.started,
            )
        finally:
            stdin_bytes[:] = b"\x00" * len(stdin_bytes)
        if isinstance(outcome, ParserRun):
            return outcome
        return self._parse_output(
            outcome,
            staged.started,
            staged.snapshot.sha256,
            password_used=password_used,
        )

    def _invoke(
        self,
        stdin_bytes: bytearray,
        task_directory: Path,
        limits: InspectionLimits,
        started: float,
    ) -> _ProcessOutput | ParserRun:
        stdout = _Capture(limits.max_worker_output_bytes)
        stderr = _Capture(min(limits.max_worker_output_bytes, _MAX_STDERR_BYTES))
        try:
            process = subprocess.Popen(  # noqa: S603
                self.build_command(),
                cwd=task_directory,
                env=self._worker_environment(task_directory),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=os.name != "nt",
            )
        except OSError:
            return self._failure(
                ErrorCode.PARSER_UNAVAILABLE,
                started,
                "The bundled ExifTool parser is unavailable.",
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
                started,
                "The ExifTool parser pipes were unavailable.",
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
            _ = stdin_pipe.write(stdin_bytes)
            stdin_pipe.close()
        except (BrokenPipeError, OSError):
            pass

        timed_out = False
        try:
            return_code = process.wait(timeout=limits.parser_timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            self._kill(process)
            return_code = process.wait()
        finally:
            stdout_thread.join(timeout=2)
            stderr_thread.join(timeout=2)
            stdout_pipe.close()
            stderr_pipe.close()

        if timed_out:
            return self._failure(
                ErrorCode.PARSER_TIMEOUT,
                started,
                "ExifTool exceeded its time limit.",
                status=ParserStatus.TIMED_OUT,
            )
        if stdout.exceeded or stderr.exceeded:
            return self._failure(
                ErrorCode.RESOURCE_LIMIT_EXCEEDED,
                started,
                "ExifTool exceeded its output limit.",
            )
        if return_code != 0 and not stdout.data:
            return self._failure(
                ErrorCode.PARSER_CRASHED,
                started,
                "ExifTool exited unexpectedly.",
            )
        return _ProcessOutput(return_code=return_code, stdout=bytes(stdout.data))

    def _parse_output(
        self,
        output: _ProcessOutput,
        started: float,
        source_sha256: str,
        *,
        password_used: bool,
    ) -> ParserRun:
        try:
            decoded = output.stdout.decode("utf-8", errors="strict")
            payload = cast(
                "object",
                json.loads(
                    decoded,
                    object_pairs_hook=_JsonObjectPairs,
                    parse_constant=self._reject_json_constant,
                ),
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            return self._failure(
                ErrorCode.PARSER_OUTPUT_INVALID,
                started,
                "ExifTool returned invalid JSON.",
            )
        if not isinstance(payload, list):
            return self._failure(
                ErrorCode.PARSER_OUTPUT_INVALID,
                started,
                "ExifTool returned an unexpected JSON shape.",
            )
        root = cast("list[object]", payload)
        if len(root) != 1 or not isinstance(root[0], _JsonObjectPairs):
            return self._failure(
                ErrorCode.PARSER_OUTPUT_INVALID,
                started,
                "ExifTool returned an unexpected JSON shape.",
            )

        pairs = root[0]
        version_values = [value for key, value in pairs if key == _VERSION_TAG]
        if len(version_values) != 1 or str(version_values[0]) != self.version:
            return self._failure(
                ErrorCode.PARSER_OUTPUT_INVALID,
                started,
                "ExifTool returned an unexpected version.",
            )
        error_run = self._reported_error(pairs, started, password_used=password_used)
        if error_run is not None:
            return error_run

        warnings: list[str] = []
        if output.return_code != 0:
            warnings.append("exiftool_nonzero_exit")
        if any(key.endswith(":Warning") or key == "Warning" for key, _ in pairs):
            warnings.append("exiftool_warning")

        document_paths = {
            raw_name.partition(":")[0]: raw_value
            for raw_name, raw_value in pairs
            if raw_name.endswith(":ZIP:ZipFileName") and isinstance(raw_value, str)
        }
        observations, embedded_documents = self._metadata_evidence(
            pairs,
            document_paths,
            source_sha256,
        )
        return ParserRun(
            parser_name=self.parser_name,
            parser_version=self.version,
            status=ParserStatus.PARTIAL if warnings else ParserStatus.SUCCEEDED,
            observations=tuple(observations),
            warnings=tuple(warnings),
            duration_ms=self._duration_ms(started),
            embedded_documents=embedded_documents,
        )

    def _metadata_evidence(
        self,
        pairs: _JsonObjectPairs,
        document_paths: dict[str, str],
        source_sha256: str,
    ) -> tuple[tuple[EvidenceObservation, ...], tuple[EmbeddedDocumentReport, ...]]:
        observations: list[EvidenceObservation] = []
        embedded_observations: dict[str, list[EvidenceObservation]] = {}
        for raw_name, raw_value in pairs:
            if (
                raw_name in _IGNORED_TAGS
                or raw_name.endswith(":Warning")
                or raw_name == "Warning"
            ):
                continue
            observation = self._observation(raw_name, raw_value, document_paths)
            if observation.source_kind == "exiftool_embedded_tag":
                embedded_observations.setdefault(observation.location, []).append(
                    observation
                )
            else:
                observations.append(observation)
        children = tuple(
            EmbeddedDocumentReport(
                resource_id=self._unresolved_resource_id(source_sha256, path),
                parent_id=source_sha256,
                depth=1,
                path=path,
                content_type="application/octet-stream",
                size_bytes=0,
                sha256="",
                parser_names=(self.parser_name,),
                observations=tuple(values),
                warnings=("embedded_descriptor_unresolved",),
            )
            for path, values in sorted(
                embedded_observations.items(),
                key=lambda item: item[0].casefold(),
            )
        )
        return tuple(observations), children

    @staticmethod
    def _unresolved_resource_id(parent_id: str, path: str) -> str:
        normalized_path = path.replace("\\", "/").lstrip("/").casefold()
        payload = f"{parent_id}\0{normalized_path}\0exiftool-unresolved".encode()
        return sha256(payload).hexdigest()

    def _reported_error(
        self,
        pairs: _JsonObjectPairs,
        started: float,
        *,
        password_used: bool,
    ) -> ParserRun | None:
        error_values = tuple(
            str(value)
            for key, value in pairs
            if key.endswith(":Error") or key == "Error"
        )
        if not error_values:
            return None
        combined = " ".join(error_values).casefold()
        if "password" in combined or "encrypted" in combined:
            code = (
                ErrorCode.WRONG_PASSWORD
                if password_used
                else ErrorCode.PASSWORD_REQUIRED
            )
            message = (
                "ExifTool did not accept the supplied document password."
                if password_used
                else "ExifTool requires a document password."
            )
            return self._failure(code, started, message)
        return self._failure(
            ErrorCode.INVALID_DOCUMENT,
            started,
            "ExifTool could not inspect this document.",
        )

    def _observation(
        self,
        raw_name: str,
        raw_value: object,
        document_paths: dict[str, str],
    ) -> EvidenceObservation:
        raw = self._json_value(raw_value)
        canonical_name = self._canonical_name(raw_name)
        group = raw_name.partition(":")[0]
        embedded_location: str | None = None
        internal_location: str | None = None
        if _DOCUMENT_GROUP.fullmatch(group) is not None:
            documented_path = document_paths.get(group)
            normalized_path = (
                documented_path.replace("\\", "/").lstrip("/").casefold()
                if documented_path is not None
                else None
            )
            if normalized_path in _ROOT_OFFICE_METADATA_PARTS:
                pass
            elif self._looks_like_embedded_path(documented_path):
                embedded_location = documented_path or group
            else:
                internal_location = documented_path or group
        if embedded_location is not None:
            embedded_name = canonical_name.removeprefix("exiftool.")
            canonical_name = f"exiftool.embedded.{embedded_name}"
        elif internal_location is not None:
            internal_name = canonical_name.removeprefix("exiftool.")
            canonical_name = f"exiftool.internal_part.{internal_name}"
        return EvidenceObservation(
            canonical_name=canonical_name,
            raw_name=raw_name,
            raw_value=raw,
            normalized_value=normalize_evidence_value(canonical_name, raw),
            value_type=self._value_type(raw),
            source_kind=(
                "exiftool_embedded_tag"
                if embedded_location is not None
                else (
                    "exiftool_internal_part_tag"
                    if internal_location is not None
                    else "exiftool_grouped_tag"
                )
            ),
            location=embedded_location or internal_location or group or "ExifTool",
            parser_name=self.parser_name,
            parser_version=self.version,
        )

    @staticmethod
    def _looks_like_embedded_path(path: str | None) -> bool:
        if path is None:
            return True
        normalized = path.replace("\\", "/").lstrip("/").casefold()
        if not normalized or normalized.endswith("/"):
            return False
        parts = frozenset(part for part in normalized.split("/") if part)
        if parts & _EMBEDDED_PATH_SEGMENTS:
            return True
        return Path(normalized).suffix in _EMBEDDED_DOCUMENT_SUFFIXES

    @staticmethod
    def _canonical_name(raw_name: str) -> str:
        tag_name = raw_name.rpartition(":")[2]
        compact = re.sub(r"[^a-z0-9]", "", tag_name.casefold())
        tag_group = raw_name.rpartition(":")[0].rpartition(":")[2]
        if compact == "creator" and tag_group.casefold() == "pdf":
            return "application"
        if compact in _CANONICAL_TAGS:
            return _CANONICAL_TAGS[compact]
        safe_name = re.sub(r"[^a-z0-9]+", "_", raw_name.casefold()).strip("_")
        return f"exiftool.{safe_name or 'unknown'}"

    @classmethod
    def _json_value(cls, value: object) -> JsonValue:
        if value is None or isinstance(value, (str, bool, int)):
            return value
        if isinstance(value, float):
            return value
        if isinstance(value, _JsonObjectPairs):
            pairs = value
            names = [name for name, _ in pairs]
            if len(set(names)) == len(names):
                return {name: cls._json_value(item) for name, item in pairs}
            return tuple(
                {"name": name, "value": cls._json_value(item)} for name, item in pairs
            )
        if isinstance(value, list):
            sequence = cast("list[object]", value)
            return tuple(cls._json_value(item) for item in sequence)
        msg = "unsupported ExifTool JSON value"
        raise ValueError(msg)

    @staticmethod
    def _value_type(value: JsonValue) -> str:
        if isinstance(value, tuple):
            result = "array"
        elif isinstance(value, dict):
            result = "structure"
        elif value is None:
            result = "null"
        elif isinstance(value, bool):
            result = "boolean"
        elif isinstance(value, int):
            result = "integer"
        elif isinstance(value, float):
            result = "number"
        else:
            result = "string"
        return result

    @staticmethod
    def _reject_json_constant(value: str) -> object:
        del value
        msg = "non-finite JSON number"
        raise ValueError(msg)

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
                ExifToolWorker._kill(process)
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


__all__ = ("ExifToolWorker",)
