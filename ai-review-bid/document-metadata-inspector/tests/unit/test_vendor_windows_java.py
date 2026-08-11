"""Regressions for transactional Windows Java artifact vendoring."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import cast

import pytest
from scripts import vendor_windows_java
from scripts.windows_vendored_java import VendoredWindowsJavaFiles

_TARGET_KEY = "windows-x86_64"
_JRE_RELATIVE_PATH = Path(
    "tools/prebuilt/windows-x86_64/OpenJDK21U-jre_x64_windows_hotspot_21.0.12_8.zip"
)
_WORKER_RELATIVE_PATH = Path(
    "tools/prebuilt/windows-x86_64/document-metadata-apache-worker.jar"
)
_JRE_URL = (
    "https://github.com/adoptium/temurin21-binaries/releases/"
    "download/jdk-21.0.12%2B8/"
    "OpenJDK21U-jre_x64_windows_hotspot_21.0.12_8.zip"
)


def test_vendor_publishes_verified_artifacts_and_complete_manifest_atomically(
    project: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Replacing a staged artifact or manifest must publish the exact new bytes."""
    _write_prior_files(project)
    downloaded = b"official Windows JRE ZIP"
    worker = tmp_path / "worker.jar"
    _ = worker.write_bytes(b"verified shaded worker JAR")
    source_hash = sha256(b"worker source inputs").hexdigest()
    _write_manifest(project, sha256(downloaded).hexdigest())
    previous = _target_bytes(project)
    _configure_success(
        monkeypatch,
        downloaded=downloaded,
        worker=worker,
        source_hash=source_hash,
    )
    verified: list[Path] = []

    def verify(root: Path) -> VendoredWindowsJavaFiles:
        verified.append(root)
        return _verified_files()

    monkeypatch.setattr(
        vendor_windows_java,
        "verify_vendored_windows_java_files",
        verify,
    )

    _ = vendor_windows_java.vendor_windows_java(project, tmp_path / "cache")

    jre = project / _JRE_RELATIVE_PATH
    worker_target = project / _WORKER_RELATIVE_PATH
    manifest_path = project / "tools/manifest.json"
    manifest = _read_manifest(manifest_path)
    vendored_worker = _mapping(_mapping(manifest["apache_worker"])["vendored"])[
        _TARGET_KEY
    ]
    vendored_jre = _mapping(_mapping(manifest["temurin_jre"])["archives"])[_TARGET_KEY]

    assert jre.read_bytes() == downloaded
    assert worker_target.read_bytes() == b"verified shaded worker JAR"
    assert _mapping(vendored_worker) == {
        "path": _WORKER_RELATIVE_PATH.as_posix(),
        "size": len(b"verified shaded worker JAR"),
        "sha256": sha256(b"verified shaded worker JAR").hexdigest(),
        "source_tree_sha256": source_hash,
        "artifact_version": "0.1.0",
        "build_java_runtime_version": "21.0.12+8",
        "build_command": ["mvnw", "--batch-mode", "--no-transfer-progress", "verify"],
    }
    assert _mapping(vendored_jre)["vendored_path"] == _JRE_RELATIVE_PATH.as_posix()
    assert _mapping(vendored_jre)["size"] == len(downloaded)
    assert _mapping(vendored_jre)["sha256"] == sha256(downloaded).hexdigest()
    assert verified == [project]
    assert all(path.read_bytes() != previous[path] for path in previous)


def test_vendor_reuses_only_a_verified_official_jre_cache_entry(
    project: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A complete verified cache entry can recover a stalled fresh download."""
    downloaded = b"official Windows JRE ZIP"
    worker = tmp_path / "worker.jar"
    _ = worker.write_bytes(b"verified shaded worker JAR")
    _write_manifest(project, sha256(downloaded).hexdigest())
    cache = tmp_path / "cache"
    cached_jre = cache / "downloads" / _JRE_RELATIVE_PATH.name
    cached_jre.parent.mkdir(parents=True)
    _ = cached_jre.write_bytes(downloaded)
    _configure_success(
        monkeypatch,
        downloaded=downloaded,
        worker=worker,
        source_hash=sha256(b"worker source inputs").hexdigest(),
    )

    def unexpected_download(_url: str, _destination: Path) -> None:
        msg = "the verified JRE cache should prevent a fresh download"
        raise AssertionError(msg)

    monkeypatch.setattr(vendor_windows_java, "_download", unexpected_download)
    monkeypatch.setattr(
        vendor_windows_java,
        "verify_vendored_windows_java_files",
        _verify_without_real_project,
    )

    _ = vendor_windows_java.vendor_windows_java(project, cache)

    assert (project / _JRE_RELATIVE_PATH).read_bytes() == downloaded
    assert cached_jre.read_bytes() == downloaded


def test_vendor_keeps_prior_targets_when_official_jre_hash_is_wrong(
    project: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A changed official digest must fail before it can replace repository bytes."""
    _write_prior_files(project)
    downloaded = b"official Windows JRE ZIP"
    _write_manifest(project, "0" * 64)
    previous = _target_bytes(project)
    monkeypatch.setattr(
        vendor_windows_java,
        "_EXPECTED_JRE_SHA256",
        sha256(downloaded).hexdigest(),
    )

    with pytest.raises(RuntimeError, match="official Temurin JRE configuration"):
        _ = vendor_windows_java.vendor_windows_java(project, tmp_path / "cache")

    _assert_unchanged(previous)


def test_vendor_keeps_prior_targets_when_maven_verification_fails(
    project: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed Maven verify must not begin the publication transaction."""
    _write_prior_files(project)
    downloaded = b"official Windows JRE ZIP"
    _write_manifest(project, sha256(downloaded).hexdigest())
    previous = _target_bytes(project)
    _configure_download(monkeypatch, downloaded)

    def ensure(_cache: Path) -> Path:
        return tmp_path / "jdk"

    monkeypatch.setattr(vendor_windows_java, "ensure_jdk", ensure)

    def failed_build(_jdk: Path) -> Path:
        msg = "the Apache Java worker build failed"
        raise RuntimeError(msg)

    monkeypatch.setattr(vendor_windows_java, "build_worker", failed_build)

    with pytest.raises(RuntimeError, match="Apache Java worker build failed"):
        _ = vendor_windows_java.vendor_windows_java(project, tmp_path / "cache")

    _assert_unchanged(previous)


def test_vendor_keeps_prior_targets_when_maven_output_is_missing(
    project: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A build result without the shaded JAR must not reach publication."""
    _write_prior_files(project)
    downloaded = b"official Windows JRE ZIP"
    _write_manifest(project, sha256(downloaded).hexdigest())
    previous = _target_bytes(project)
    _configure_download(monkeypatch, downloaded)

    def ensure(_cache: Path) -> Path:
        return tmp_path / "jdk"

    def missing_worker(_jdk: Path) -> Path:
        return tmp_path / "missing-worker.jar"

    monkeypatch.setattr(vendor_windows_java, "ensure_jdk", ensure)
    monkeypatch.setattr(
        vendor_windows_java,
        "build_worker",
        missing_worker,
    )

    with pytest.raises(RuntimeError, match="Apache worker JAR is missing"):
        _ = vendor_windows_java.vendor_windows_java(project, tmp_path / "cache")

    _assert_unchanged(previous)


def test_vendor_rolls_back_all_prior_targets_when_manifest_publication_fails(
    project: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The final manifest rename must restore both binary targets on failure."""
    _write_prior_files(project)
    downloaded = b"official Windows JRE ZIP"
    worker = tmp_path / "worker.jar"
    _ = worker.write_bytes(b"verified shaded worker JAR")
    _write_manifest(project, sha256(downloaded).hexdigest())
    previous = _target_bytes(project)
    _configure_success(
        monkeypatch,
        downloaded=downloaded,
        worker=worker,
        source_hash=sha256(b"worker source inputs").hexdigest(),
    )
    manifest = project / "tools/manifest.json"
    replace = vendor_windows_java._replace  # pyright: ignore[reportPrivateUsage]

    def fail_new_manifest(source: Path, destination: Path) -> None:
        if destination == manifest and source.name == "manifest.json":
            msg = "synthetic manifest publication failure"
            raise OSError(msg)
        replace(source, destination)

    monkeypatch.setattr(vendor_windows_java, "_replace", fail_new_manifest)

    with pytest.raises(OSError, match="synthetic manifest publication failure"):
        _ = vendor_windows_java.vendor_windows_java(project, tmp_path / "cache")

    _assert_unchanged(previous)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / "tools/prebuilt/windows-x86_64").mkdir(parents=True)
    return root


def _configure_success(
    monkeypatch: pytest.MonkeyPatch,
    *,
    downloaded: bytes,
    worker: Path,
    source_hash: str,
) -> None:
    _configure_download(monkeypatch, downloaded)

    def ensure(_cache: Path) -> Path:
        return worker.parent / "jdk"

    def build(_jdk: Path) -> Path:
        return worker

    def inputs(_project: Path) -> str:
        return source_hash

    monkeypatch.setattr(vendor_windows_java, "ensure_jdk", ensure)
    monkeypatch.setattr(vendor_windows_java, "build_worker", build)
    monkeypatch.setattr(
        vendor_windows_java,
        "worker_inputs_sha256",
        inputs,
    )


def _configure_download(monkeypatch: pytest.MonkeyPatch, contents: bytes) -> None:
    def download(_url: str, destination: Path) -> None:
        _ = destination.write_bytes(contents)

    monkeypatch.setattr(vendor_windows_java, "_download", download)
    monkeypatch.setattr(
        vendor_windows_java,
        "_EXPECTED_JRE_SHA256",
        sha256(contents).hexdigest(),
    )


def _write_prior_files(project: Path) -> None:
    targets = {
        project / _JRE_RELATIVE_PATH: b"previous JRE ZIP",
        project / _WORKER_RELATIVE_PATH: b"previous worker JAR",
    }
    for path, contents in targets.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_bytes(contents)


def _target_bytes(project: Path) -> dict[Path, bytes]:
    targets = (
        project / _JRE_RELATIVE_PATH,
        project / _WORKER_RELATIVE_PATH,
        project / "tools/manifest.json",
    )
    return {path: path.read_bytes() for path in targets}


def _write_manifest(project: Path, jre_hash: str) -> None:
    payload: dict[str, object] = {
        "schema_version": "1",
        "apache_worker": {
            "tika_version": "3.3.2",
            "java_major_version": 21,
            "java_vendor": "Eclipse Adoptium",
            "java_runtime_version": "21.0.12+8",
            "packaged": {},
        },
        "temurin_jre": {
            "version": "21.0.12+8",
            "release_url": "https://example.invalid/release",
            "archives": {
                _TARGET_KEY: {
                    "url": _JRE_URL,
                    "sha256": jre_hash,
                    "archive_type": "zip",
                }
            },
        },
    }
    _ = (project / "tools/manifest.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def _verify_without_real_project(_project: Path) -> VendoredWindowsJavaFiles:
    return _verified_files()


def _verified_files() -> VendoredWindowsJavaFiles:
    return VendoredWindowsJavaFiles(
        jre_archive=Path("jre.zip"),
        worker_jar=Path("worker.jar"),
        java_runtime_version="21.0.12+8",
    )


def _read_manifest(path: Path) -> dict[str, object]:
    value = cast("object", json.loads(path.read_text(encoding="utf-8")))
    if not isinstance(value, dict):
        msg = "synthetic manifest must be an object"
        raise TypeError(msg)
    return cast("dict[str, object]", value)


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        msg = "synthetic manifest mapping is absent"
        raise TypeError(msg)
    return cast("dict[str, object]", value)


def _assert_unchanged(previous: dict[Path, bytes]) -> None:
    assert {path: path.read_bytes() for path in previous} == previous
