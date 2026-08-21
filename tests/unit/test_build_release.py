"""Regressions for native release-build orchestration."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import TYPE_CHECKING

from scripts import build_release
from scripts.prepare_platform_resources import ApacheRuntimeSources

from document_metadata_inspector.resources import tree_sha256

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    import pytest


def test_release_refreshes_existing_packaged_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packaged = tmp_path / "tools/packaged/darwin-arm64"
    packaged.mkdir(parents=True)
    manifest = tmp_path / "tools/manifest.json"
    source_manifest = b'{"source": true}\n'
    packaged_manifest = b'{"packaged": true}\n'
    _ = manifest.write_bytes(source_manifest)
    java_home = tmp_path / "jdk"
    worker_jar = tmp_path / "worker.jar"
    exiftool_runtime = tmp_path / "exiftool"
    jdk_calls: list[Path] = []
    worker_calls: list[Path] = []
    calls: list[tuple[ApacheRuntimeSources, Path, tuple[str, ...], bool]] = []

    def bootstrap_exiftool(
        *,
        check_only: bool,
        allow_system_development: bool,
    ) -> Path:
        del check_only, allow_system_development
        return tmp_path / "exiftool-source"

    def ensure_jdk(cache: Path) -> Path:
        del cache
        jdk_calls.append(java_home)
        return java_home

    def build_worker(java: Path) -> Path:
        worker_calls.append(java)
        return worker_jar

    def exiftool_for_platform(key: str) -> tuple[Path, tuple[str, ...]]:
        del key
        return exiftool_runtime, ("perl", "exiftool")

    def resolve_resource(
        *,
        root: Path | None = None,
        development: bool = False,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        del root, development, environment

    def build_app(mode: build_release.BuildMode) -> Path:
        del mode
        assert manifest.read_bytes() == packaged_manifest
        return tmp_path / "docmeta"

    monkeypatch.setattr(build_release, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(build_release, "bootstrap_exiftool", bootstrap_exiftool)
    monkeypatch.setattr(build_release, "ensure_jdk", ensure_jdk)
    monkeypatch.setattr(build_release, "build_worker", build_worker)
    monkeypatch.setattr(build_release, "platform_key", lambda: "darwin-arm64")
    monkeypatch.setattr(
        build_release,
        "_exiftool_runtime",
        exiftool_for_platform,
    )

    def prepare(
        apache: ApacheRuntimeSources,
        exiftool: Path,
        command: tuple[str, ...],
        *,
        replace_existing: bool,
    ) -> Path:
        assert apache.java_home_kind == "jdk"
        calls.append((apache, exiftool, command, replace_existing))
        _ = manifest.write_bytes(packaged_manifest)
        return packaged

    monkeypatch.setattr(build_release, "prepare", prepare)
    monkeypatch.setattr(build_release, "resolve_apache_worker", resolve_resource)
    monkeypatch.setattr(build_release, "resolve_exiftool", resolve_resource)
    monkeypatch.setattr(build_release, "build_app", build_app)

    result = build_release.build_release("onefile")

    assert result == tmp_path / "docmeta"
    assert jdk_calls == [java_home]
    assert worker_calls == [java_home]
    assert calls == [
        (
            ApacheRuntimeSources(java_home, worker_jar, "jdk"),
            exiftool_runtime,
            ("perl", "exiftool"),
            True,
        ),
    ]
    assert manifest.read_bytes() == source_manifest


def test_windows_release_uses_verified_vendored_java_without_a_jdk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Windows build routing must consume the verified JRE/JAR snapshot directly."""
    manifest = tmp_path / "tools/manifest.json"
    _ = manifest.parent.mkdir(parents=True)
    source_manifest = b'{"source": true}\n'
    packaged_manifest = b'{"packaged": true}\n'
    _ = manifest.write_bytes(source_manifest)
    vendored_jre = tmp_path / "vendored-jre"
    vendored_worker = tmp_path / "vendored-worker.jar"
    exiftool_runtime = tmp_path / "exiftool"
    calls: list[tuple[ApacheRuntimeSources, Path, tuple[str, ...], bool]] = []

    def unexpected_jdk(_cache: Path) -> Path:
        msg = "a Windows release must not bootstrap a JDK"
        raise AssertionError(msg)

    def unexpected_worker(_java_home: Path) -> Path:
        msg = "a Windows release must not build the Apache worker"
        raise AssertionError(msg)

    def prepare_vendored_java(
        _project_root: Path,
        _cache: Path,
    ) -> SimpleNamespace:
        return SimpleNamespace(java_home=vendored_jre, worker_jar=vendored_worker)

    def exiftool_for_platform(key: str) -> tuple[Path, tuple[str, ...]]:
        assert key == "windows-x86_64"
        return exiftool_runtime, ("exiftool.exe",)

    def prepare(
        apache: ApacheRuntimeSources,
        exiftool: Path,
        command: tuple[str, ...],
        *,
        replace_existing: bool,
    ) -> Path:
        assert apache.java_home_kind == "jre"
        calls.append((apache, exiftool, command, replace_existing))
        _ = manifest.write_bytes(packaged_manifest)
        return tmp_path / "tools/packaged/windows-x86_64"

    def resolve_resource(
        *,
        root: Path | None = None,
        development: bool = False,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        del root, development, environment

    def build_windows_app(mode: build_release.BuildMode) -> Path:
        del mode
        return tmp_path / "docmeta"

    def bootstrap_windows_exiftool(
        *,
        check_only: bool,
        allow_system_development: bool,
    ) -> Path:
        del check_only, allow_system_development
        return tmp_path / "exiftool-source"

    monkeypatch.setattr(build_release, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(build_release, "ensure_jdk", unexpected_jdk)
    monkeypatch.setattr(build_release, "build_worker", unexpected_worker)
    monkeypatch.setattr(
        build_release,
        "prepare_vendored_windows_java",
        prepare_vendored_java,
        raising=False,
    )
    monkeypatch.setattr(build_release, "platform_key", lambda: "windows-x86_64")
    monkeypatch.setattr(build_release, "_exiftool_runtime", exiftool_for_platform)
    monkeypatch.setattr(build_release, "prepare", prepare)
    monkeypatch.setattr(build_release, "resolve_apache_worker", resolve_resource)
    monkeypatch.setattr(build_release, "resolve_exiftool", resolve_resource)
    monkeypatch.setattr(build_release, "build_app", build_windows_app)
    monkeypatch.setattr(
        build_release,
        "bootstrap_exiftool",
        bootstrap_windows_exiftool,
    )

    result = build_release.build_release("onefile")

    assert result == tmp_path / "docmeta"
    assert calls == [
        (
            ApacheRuntimeSources(vendored_jre, vendored_worker, "jre"),
            exiftool_runtime,
            ("exiftool.exe",),
            False,
        ),
    ]
    assert manifest.read_bytes() == source_manifest


def test_exiftool_release_cache_is_rebuilt_when_integrity_record_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = tmp_path / "cache"
    runtime = cache / "release-exiftool/darwin-arm64"
    runtime.mkdir(parents=True)
    _ = (runtime / "stale").write_text("modified", encoding="utf-8")
    builds: list[Path] = []

    def build(output: Path, downloads: Path, jobs: int) -> Path:
        del downloads, jobs
        builds.append(output)
        output.mkdir(parents=True)
        (output / "perl/bin").mkdir(parents=True)
        (output / "exiftool-source").mkdir()
        _ = (output / "perl/bin/perl").write_text("perl", encoding="utf-8")
        _ = (output / "exiftool-source/exiftool").write_text(
            "exiftool",
            encoding="utf-8",
        )
        return output

    monkeypatch.setattr(build_release, "_BUILD_CACHE", cache)
    monkeypatch.setattr(build_release, "build_portable_exiftool", build)

    output, command = build_release._exiftool_runtime(  # pyright: ignore[reportPrivateUsage]
        "darwin-arm64"
    )

    assert builds
    assert output == runtime
    assert command == ("perl/bin/perl", "exiftool-source/exiftool")
    assert not (runtime / "stale").exists()
    assert runtime.with_name("darwin-arm64.integrity.json").is_file()


def test_exiftool_release_cache_detects_a_modified_runtime_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = tmp_path / "darwin-arm64"
    runtime.mkdir()
    executable = runtime / "exiftool"
    _ = executable.write_text("controlled", encoding="utf-8")

    def controlled_provenance(key: str) -> str:
        return key

    monkeypatch.setattr(build_release, "_runtime_provenance", controlled_provenance)
    integrity = runtime.with_name("darwin-arm64.integrity.json")
    _ = integrity.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "platform": "darwin-arm64",
                "provenance": "darwin-arm64",
                "tree_sha256": tree_sha256(runtime),
            }
        ),
        encoding="utf-8",
    )

    assert build_release._cached_runtime_is_valid(  # pyright: ignore[reportPrivateUsage]
        runtime,
        "darwin-arm64",
    )

    _ = executable.write_text("modified", encoding="utf-8")

    assert not build_release._cached_runtime_is_valid(  # pyright: ignore[reportPrivateUsage]
        runtime,
        "darwin-arm64",
    )
