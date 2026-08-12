"""Bounded batch orchestration for native, Apache and ExifTool evidence."""

from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from hashlib import sha256
from os import cpu_count
from pathlib import Path  # noqa: TC003 - Pydantic resolves ScanRequest at runtime.
from threading import Lock
from time import monotonic
from typing import TYPE_CHECKING, Protocol

from pydantic import Field, field_validator

from document_metadata_inspector.errors import ErrorCode, InspectionError
from document_metadata_inspector.formats import (
    SUPPORTED_SUFFIXES,
    DocumentFamily,
    FormatIdentity,
    FormatIdentityStatus,
    identify_declared_format,
    identify_format,
)
from document_metadata_inspector.merge import merge_parser_results
from document_metadata_inspector.models import (
    DocumentReport,
    DocumentStatus,
    EmbeddedDocumentReport,
    FrozenModel,
    InspectionLimits,
    ParserRun,
    ParserStatus,
    ScanReport,
)
from document_metadata_inspector.native import extract_native_office
from document_metadata_inspector.native.pdf import extract_native_pdf
from document_metadata_inspector.source import SourceSnapshot, open_source_snapshot

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    type PasswordProvider = Callable[[str], str | None]

_HEADER_BYTES = 1024
_MAX_CONCURRENCY = 32
_ENCRYPTION_ERRORS = frozenset(
    {
        ErrorCode.ENCRYPTED_DOCUMENT.value,
        ErrorCode.PASSWORD_REQUIRED.value,
        ErrorCode.WRONG_PASSWORD.value,
        ErrorCode.UNSUPPORTED_ENCRYPTION.value,
    }
)


def _merge_embedded_documents(
    runs: tuple[ParserRun, ...],
) -> tuple[EmbeddedDocumentReport, ...]:
    children = tuple(child for run in runs for child in run.embedded_documents)
    resolved_by_location: dict[tuple[str, int, str], set[str]] = {}
    resolved_by_basename: dict[tuple[str, int, str], set[str]] = {}
    for child in children:
        if child.sha256:
            resolved_by_location.setdefault(
                _embedded_location_key(child),
                set(),
            ).add(child.resource_id)
            resolved_by_basename.setdefault(
                _embedded_basename_key(child),
                set(),
            ).add(child.resource_id)

    grouped: dict[str, list[EmbeddedDocumentReport]] = {}
    for child in children:
        resource_id = child.resource_id
        if not child.sha256:
            candidates = resolved_by_location.get(_embedded_location_key(child), set())
            if not candidates:
                candidates = resolved_by_basename.get(
                    _embedded_basename_key(child),
                    set(),
                )
            if len(candidates) == 1:
                resource_id = next(iter(candidates))
        grouped.setdefault(resource_id, []).append(child)

    merged: list[EmbeddedDocumentReport] = []
    for resource_id, children in grouped.items():
        ordered = sorted(
            children,
            key=lambda child: (
                not bool(child.sha256),
                child.parser_names,
                child.path.casefold(),
            ),
        )
        base = ordered[0]
        descriptors = {
            (
                child.parent_id,
                child.depth,
                child.path,
                child.content_type,
                child.size_bytes,
                child.sha256,
            )
            for child in ordered
            if child.sha256
        }
        warnings = {warning for child in ordered for warning in child.warnings}
        if descriptors:
            warnings.discard("embedded_descriptor_unresolved")
        if len(descriptors) > 1:
            warnings.add("embedded_descriptor_conflict")
        unique_observations = {
            observation.model_dump_json(): observation
            for child in ordered
            for observation in child.observations
        }
        merged.append(
            base.model_copy(
                update={
                    "resource_id": resource_id,
                    "parser_names": tuple(
                        sorted(
                            {
                                parser
                                for child in ordered
                                for parser in child.parser_names
                            }
                        )
                    ),
                    "observations": tuple(
                        unique_observations[key] for key in sorted(unique_observations)
                    ),
                    "warnings": tuple(sorted(warnings)),
                }
            )
        )
    return tuple(
        sorted(
            merged,
            key=lambda child: (
                child.depth,
                child.path.casefold(),
                child.resource_id,
            ),
        )
    )


def _embedded_location_key(
    child: EmbeddedDocumentReport,
) -> tuple[str, int, str]:
    normalized_path = child.path.replace("\\", "/").lstrip("/").casefold()
    return child.parent_id, child.depth, normalized_path


def _embedded_basename_key(
    child: EmbeddedDocumentReport,
) -> tuple[str, int, str]:
    normalized_path = child.path.replace("\\", "/").rstrip("/").casefold()
    basename = normalized_path.rpartition("/")[2]
    return child.parent_id, child.depth, basename


class ParserWorker(Protocol):
    """Describe an isolated sidecar parser used by the scanner."""

    def scan(
        self,
        snapshot: SourceSnapshot,
        password_provider: PasswordProvider | None,
        limits: InspectionLimits,
    ) -> ParserRun:
        """Return one sanitized parser result for the immutable snapshot."""
        ...


class ScanRequest(FrozenModel):
    """Describe stable file/directory expansion and scan resource budgets."""

    paths: tuple[Path, ...]
    recursive: bool = False
    max_concurrency: int | None = None
    limits: InspectionLimits = Field(default_factory=InspectionLimits)

    @field_validator("paths")
    @classmethod
    def _require_paths(cls, value: tuple[Path, ...]) -> tuple[Path, ...]:
        if not value:
            msg = "at least one scan path is required"
            raise ValueError(msg)
        return value

    @field_validator("max_concurrency")
    @classmethod
    def _validate_concurrency(cls, value: int | None) -> int | None:
        if value is not None and not 1 <= value <= _MAX_CONCURRENCY:
            msg = f"max_concurrency must be between 1 and {_MAX_CONCURRENCY}"
            raise ValueError(msg)
        return value


@dataclass(frozen=True, slots=True)
class Scanner:
    """Coordinate independent parsers without hiding failed coverage."""

    apache_worker: ParserWorker | None
    exiftool_worker: ParserWorker | None

    def scan(
        self,
        request: ScanRequest,
        password_provider: PasswordProvider | None = None,
    ) -> ScanReport:
        """Expand inputs, inspect files concurrently and return stable order."""
        documents: list[DocumentReport] = []
        expansion_warnings = self.scan_incrementally(
            request,
            lambda document, _completed, _total: documents.append(document),
            password_provider,
        )
        return ScanReport(
            documents=tuple(documents),
            warnings=expansion_warnings,
        )

    def scan_incrementally(
        self,
        request: ScanRequest,
        on_document: Callable[[DocumentReport, int, int], None],
        password_provider: PasswordProvider | None = None,
    ) -> tuple[str, ...]:
        """Inspect a bounded number of documents and publish each terminal result."""
        paths, expansion_warnings = _expand_paths(request)
        if not paths:
            return expansion_warnings

        concurrency = request.max_concurrency or min(4, cpu_count() or 1)
        password_lock = Lock()
        inspect = partial(
            self._scan_path,
            limits=request.limits,
            password_provider=password_provider,
            password_lock=password_lock,
        )
        for completed, document in enumerate(
            _iter_bounded_documents(paths, concurrency, inspect),
            start=1,
        ):
            on_document(document, completed, len(paths))
        return expansion_warnings

    def _scan_path(
        self,
        path: Path,
        *,
        limits: InspectionLimits,
        password_provider: PasswordProvider | None,
        password_lock: Lock,
    ) -> DocumentReport:
        declared = identify_declared_format(path)
        identity = declared
        size_bytes = 0
        digest = "0" * 64
        try:
            with open_source_snapshot(path, limits) as snapshot:
                size_bytes = snapshot.size_bytes
                digest = snapshot.sha256
                header = snapshot.stream.read(_HEADER_BYTES)
                _ = snapshot.stream.seek(0)
                identity = identify_format(path, header)
                cached_provider = _CachedPasswordProvider(
                    password_provider,
                    password_lock,
                )
                runs = self._run_parsers(snapshot, identity, cached_provider)
                cached_provider.clear()
                merged = merge_parser_results(runs)
                status = _document_status(identity, runs)
                encrypted = _is_encrypted(runs, merged.observations)
                return DocumentReport(
                    display_name=path.name,
                    source_path_sha256=_path_digest(path),
                    size_bytes=snapshot.size_bytes,
                    sha256=snapshot.sha256,
                    identity=identity,
                    status=status,
                    observations=merged.observations,
                    parser_runs=runs,
                    encrypted=encrypted,
                    password_required=any(
                        run.error_code == ErrorCode.PASSWORD_REQUIRED.value
                        for run in runs
                    ),
                    warnings=merged.warnings,
                    embedded_documents=_merge_embedded_documents(runs),
                )
        except InspectionError as error:
            return _failed_document(
                path,
                _FailureState(identity, size_bytes, digest),
                error.code,
                error.message,
            )
        except (OSError, RuntimeError, ValueError):
            return _failed_document(
                path,
                _FailureState(identity, size_bytes, digest),
                ErrorCode.INTERNAL_ERROR,
                "The document inspection failed unexpectedly.",
            )

    def _run_parsers(
        self,
        snapshot: SourceSnapshot,
        identity: FormatIdentity,
        password_provider: _CachedPasswordProvider,
    ) -> tuple[ParserRun, ...]:
        provider = password_provider if password_provider.enabled else None
        if identity.family is DocumentFamily.PDF:
            native = extract_native_pdf(snapshot, identity, provider)
        else:
            native = extract_native_office(snapshot, identity, provider)
        apache = _run_worker(
            self.apache_worker,
            "apache-tika",
            snapshot,
            provider,
            snapshot.limits,
        )
        exiftool = _run_worker(
            self.exiftool_worker,
            "exiftool",
            snapshot,
            provider,
            snapshot.limits,
        )
        return (native, apache, exiftool)


def _iter_bounded_documents(
    paths: tuple[Path, ...],
    concurrency: int,
    inspect: Callable[[Path], DocumentReport],
) -> Iterator[DocumentReport]:
    if len(paths) == 1 or concurrency == 1:
        for path in paths:
            yield inspect(path)
        return

    worker_count = min(concurrency, len(paths))
    path_iterator = iter(paths)
    with ThreadPoolExecutor(
        max_workers=worker_count,
        thread_name_prefix="docmeta-scan",
    ) as executor:
        pending = deque(
            executor.submit(inspect, path)
            for path in (next(path_iterator) for _ in range(worker_count))
        )
        for path in path_iterator:
            yield pending.popleft().result()
            pending.append(executor.submit(inspect, path))
        while pending:
            yield pending.popleft().result()


@dataclass(slots=True)
class _CachedPasswordProvider:
    provider: PasswordProvider | None
    shared_lock: Lock
    _loaded: bool = False
    _value: str | None = None

    @property
    def enabled(self) -> bool:
        """Report whether the caller supplied a password callback."""
        return self.provider is not None

    def __call__(self, source_name: str) -> str | None:
        """Prompt once per file and retain the value in memory only for this scan."""
        if not self._loaded:
            with self.shared_lock:
                if not self._loaded:
                    self._value = (
                        self.provider(source_name)
                        if self.provider is not None
                        else None
                    )
                    self._loaded = True
        return self._value

    def clear(self) -> None:
        """Release the cached password reference after all parsers return."""
        self._value = None
        self._loaded = False


def _run_worker(
    worker: ParserWorker | None,
    parser_name: str,
    snapshot: SourceSnapshot,
    password_provider: PasswordProvider | None,
    limits: InspectionLimits,
) -> ParserRun:
    if worker is None:
        return ParserRun(
            parser_name=parser_name,
            parser_version="not-bundled",
            status=ParserStatus.SKIPPED,
            warnings=("The required parser is not bundled.",),
            error_code=ErrorCode.PARSER_UNAVAILABLE.value,
        )
    started = monotonic()
    try:
        return worker.scan(snapshot, password_provider, limits)
    except (OSError, RuntimeError, ValueError):
        return ParserRun(
            parser_name=parser_name,
            parser_version="unknown",
            status=ParserStatus.FAILED,
            warnings=("The isolated parser failed unexpectedly.",),
            error_code=ErrorCode.PARSER_CRASHED.value,
            duration_ms=max(0, round((monotonic() - started) * 1_000)),
        )


def _document_status(
    identity: FormatIdentity,
    runs: tuple[ParserRun, ...],
) -> DocumentStatus:
    if identity.status is not FormatIdentityStatus.CONFIRMED:
        return DocumentStatus.FAILED
    native = runs[0]
    if native.error_code in _ENCRYPTION_ERRORS:
        return DocumentStatus.ENCRYPTED_UNREADABLE
    if all(run.status is ParserStatus.SUCCEEDED for run in runs):
        return DocumentStatus.COMPLETE
    if any(
        run.status in {ParserStatus.SUCCEEDED, ParserStatus.PARTIAL} for run in runs
    ):
        return DocumentStatus.PARTIAL
    return DocumentStatus.FAILED


def _is_encrypted(
    runs: tuple[ParserRun, ...],
    observations: tuple[object, ...],
) -> bool:
    if any(run.error_code in _ENCRYPTION_ERRORS for run in runs):
        return True
    return any(
        getattr(item, "canonical_name", None) == "pdf_encrypted"
        and getattr(item, "raw_value", None) is True
        for item in observations
    )


@dataclass(frozen=True, slots=True)
class _FailureState:
    identity: FormatIdentity
    size_bytes: int
    digest: str


def _failed_document(
    path: Path,
    state: _FailureState,
    code: ErrorCode,
    message: str,
) -> DocumentReport:
    run = ParserRun(
        parser_name="source-boundary",
        parser_version="1",
        status=ParserStatus.FAILED,
        warnings=(message,),
        error_code=code.value,
    )
    return DocumentReport(
        display_name=path.name,
        source_path_sha256=_path_digest(path),
        size_bytes=state.size_bytes,
        sha256=state.digest,
        identity=state.identity,
        status=DocumentStatus.FAILED,
        parser_runs=(run,),
        warnings=(f"source_status:{code.value}",),
    )


def _path_digest(path: Path) -> str:
    resolved = str(path.resolve(strict=False)).encode("utf-8", errors="surrogatepass")
    return sha256(resolved).hexdigest()


def _expand_paths(request: ScanRequest) -> tuple[tuple[Path, ...], tuple[str, ...]]:
    candidates: list[Path] = []
    warnings: set[str] = set()
    for requested in request.paths:
        try:
            if requested.is_symlink():
                warnings.add("symbolic_link_input_skipped")
            elif requested.is_file():
                if requested.suffix.casefold() in SUPPORTED_SUFFIXES:
                    candidates.append(requested)
                else:
                    warnings.add("unsupported_input_skipped")
            elif requested.is_dir():
                iterator = (
                    requested.rglob("*") if request.recursive else requested.iterdir()
                )
                candidates.extend(
                    item
                    for item in iterator
                    if not item.is_symlink()
                    and item.is_file()
                    and item.suffix.casefold() in SUPPORTED_SUFFIXES
                )
            else:
                warnings.add("missing_input_skipped")
        except OSError:
            warnings.add("unreadable_input_skipped")

    unique: dict[str, Path] = {}
    for candidate in candidates:
        key = str(candidate.resolve(strict=False))
        _ = unique.setdefault(key, candidate)
    ordered = tuple(
        sorted(
            unique.values(),
            key=lambda path: (path.name.casefold(), str(path).casefold()),
        )
    )
    return ordered, tuple(sorted(warnings))


def scan_documents(
    request: ScanRequest,
    *,
    apache_worker: ParserWorker | None = None,
    exiftool_worker: ParserWorker | None = None,
    password_provider: PasswordProvider | None = None,
) -> ScanReport:
    """Convenience entry point for callers that do not retain a Scanner instance."""
    return Scanner(
        apache_worker=apache_worker,
        exiftool_worker=exiftool_worker,
    ).scan(request, password_provider)


__all__ = ("ParserWorker", "ScanRequest", "Scanner", "scan_documents")
