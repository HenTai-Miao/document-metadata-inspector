from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

from document_metadata_inspector.resources import platform_key
from document_metadata_inspector.runtime import (
    RuntimeComponentStatus,
    create_runtime,
)
from document_metadata_inspector.workers.apache import ApacheWorker
from document_metadata_inspector.workers.exiftool import ExifToolWorker

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _write_unbundled_manifest(root: Path) -> None:
    path = root / "tools/manifest.json"
    path.parent.mkdir(parents=True)
    key = platform_key()
    payload: dict[str, object] = {
        "schema_version": "1",
        "exiftool": {
            "version": "13.55",
            "official_source": {
                "url": "https://invalid.example.test/exiftool.tar.gz",
                "sha256": "0" * 64,
                "directory": "tools/vendor/exiftool/13.55/source",
                "tree_sha256": "1" * 64,
            },
            "packaged": {key: {"available": False}},
        },
        "apache_worker": {
            "tika_version": "3.3.2",
            "java_major_version": 21,
            "packaged": {key: {"available": False}},
        },
    }
    _ = path.write_text(json.dumps(payload), encoding="utf-8")


def _tool_version(
    args: tuple[str, ...],
    **kwargs: object,
) -> subprocess.CompletedProcess[bytes]:
    del kwargs
    if args[-1] == "-ver":
        return subprocess.CompletedProcess(args, 0, b"13.55\n", b"")
    return subprocess.CompletedProcess(
        args,
        0,
        b"",
        b'java version "21.0.11" 2026-04-21 LTS\n',
    )


def test_development_runtime_finds_locked_project_local_resources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_unbundled_manifest(tmp_path)
    exiftool = tmp_path / "tools/vendor/exiftool/13.55/source/exiftool"
    exiftool.parent.mkdir(parents=True)
    _ = exiftool.write_bytes(b"#!/usr/bin/perl\n")
    worker_jar = tmp_path / "java-worker/target/document-metadata-apache-worker.jar"
    worker_jar.parent.mkdir(parents=True)
    _ = worker_jar.write_bytes(b"controlled jar")
    java_home = tmp_path / "jdk"
    java = java_home / "bin/java"
    java.parent.mkdir(parents=True)
    _ = java.write_bytes(b"controlled java")
    perl = tmp_path / "perl"
    _ = perl.write_bytes(b"controlled perl")
    monkeypatch.setattr(subprocess, "run", _tool_version)

    runtime = create_runtime(
        root=tmp_path,
        development=True,
        environment={"JAVA_HOME": str(java_home), "DOCMETA_PERL": str(perl)},
    )

    assert isinstance(runtime.scanner.apache_worker, ApacheWorker)
    assert isinstance(runtime.scanner.exiftool_worker, ExifToolWorker)
    assert {item.status for item in runtime.components} == {
        RuntimeComponentStatus.READY
    }


def test_release_runtime_reports_missing_bundles_without_system_fallback(
    tmp_path: Path,
) -> None:
    _write_unbundled_manifest(tmp_path)

    runtime = create_runtime(
        root=tmp_path,
        development=False,
        environment={
            "DOCMETA_EXIFTOOL": str(tmp_path / "not-used-exiftool"),
            "DOCMETA_JAVA": str(tmp_path / "not-used-java"),
            "DOCMETA_APACHE_WORKER_JAR": str(tmp_path / "not-used-worker.jar"),
        },
    )

    assert runtime.scanner.apache_worker is None
    assert runtime.scanner.exiftool_worker is None
    assert {item.status for item in runtime.components} == {
        RuntimeComponentStatus.UNAVAILABLE
    }
