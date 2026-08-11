"""Regressions for native release-build orchestration."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from scripts import build_release

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
    exiftool_runtime = tmp_path / "exiftool"
    calls: list[tuple[Path, Path, tuple[str, ...], bool]] = []

    def bootstrap_exiftool(
        *,
        check_only: bool,
        allow_system_development: bool,
    ) -> Path:
        del check_only, allow_system_development
        return tmp_path / "exiftool-source"

    def ensure_jdk(cache: Path) -> Path:
        del cache
        return java_home

    def build_worker(java: Path) -> None:
        del java

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
        java: Path,
        exiftool: Path,
        command: tuple[str, ...],
        *,
        replace_existing: bool,
    ) -> Path:
        calls.append((java, exiftool, command, replace_existing))
        _ = manifest.write_bytes(packaged_manifest)
        return packaged

    monkeypatch.setattr(build_release, "prepare", prepare)
    monkeypatch.setattr(build_release, "resolve_apache_worker", resolve_resource)
    monkeypatch.setattr(build_release, "resolve_exiftool", resolve_resource)
    monkeypatch.setattr(build_release, "build_app", build_app)

    result = build_release.build_release("onefile")

    assert result == tmp_path / "docmeta"
    assert calls == [
        (java_home, exiftool_runtime, ("perl", "exiftool"), True),
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
