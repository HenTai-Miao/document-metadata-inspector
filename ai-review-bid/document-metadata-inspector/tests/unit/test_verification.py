from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from document_metadata_inspector.models import (
    EvidenceObservation,
    InspectionLimits,
    ParserRun,
    ParserStatus,
)
from document_metadata_inspector.normalization import normalize_identity_text
from document_metadata_inspector.runtime import (
    RuntimeComponent,
    RuntimeComponentStatus,
    RuntimeEnvironment,
)
from document_metadata_inspector.scanner import Scanner
from document_metadata_inspector.verification import VerificationStatus, verify_runtime

if TYPE_CHECKING:
    from document_metadata_inspector.source import SourceSnapshot


class _ControlledWorker:
    parser_name: str

    def __init__(self, parser_name: str) -> None:
        self.parser_name = parser_name

    def scan(
        self,
        snapshot: SourceSnapshot,
        password_provider: object,
        limits: InspectionLimits,
    ) -> ParserRun:
        del password_provider, limits
        author = {
            ".pdf": "Verification PDF",
            ".docx": "Verification Word",
            ".xlsx": "Verification Excel",
        }[Path(snapshot.name).suffix]
        observation = EvidenceObservation(
            canonical_name="author",
            raw_name="Author",
            raw_value=author,
            normalized_value=normalize_identity_text(author),
            value_type="string",
            source_kind="controlled_verification_worker",
            location="root",
            parser_name=self.parser_name,
            parser_version="test",
        )
        return ParserRun(
            parser_name=self.parser_name,
            parser_version="test",
            status=ParserStatus.SUCCEEDED,
            observations=(observation,),
        )


def _runtime(status: RuntimeComponentStatus) -> RuntimeEnvironment:
    components = tuple(
        RuntimeComponent(name=name, version=version, status=status)
        for name, version in (("apache-tika", "3.3.2"), ("exiftool", "13.55"))
    )
    ready = status is RuntimeComponentStatus.READY
    return RuntimeEnvironment(
        scanner=Scanner(
            apache_worker=_ControlledWorker("apache-tika") if ready else None,
            exiftool_worker=_ControlledWorker("exiftool") if ready else None,
        ),
        components=components,
    )


def test_verify_runtime_executes_all_three_major_document_families() -> None:
    report = verify_runtime(_runtime(RuntimeComponentStatus.READY))

    assert report.passed is True
    assert {
        check.name for check in report.checks if check.name.startswith("sample:")
    } == {
        "sample:pdf",
        "sample:word",
        "sample:excel",
        "sample:source-integrity",
    }
    assert all(check.status is VerificationStatus.PASS for check in report.checks)


def test_verify_runtime_fails_explicitly_when_bundled_engines_are_missing() -> None:
    report = verify_runtime(_runtime(RuntimeComponentStatus.UNAVAILABLE))

    assert report.passed is False
    assert any(
        check.name == "component:apache-tika"
        and check.status is VerificationStatus.FAIL
        for check in report.checks
    )
