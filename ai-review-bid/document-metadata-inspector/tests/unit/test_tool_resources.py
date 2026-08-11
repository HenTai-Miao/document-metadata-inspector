from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from document_metadata_inspector.resources import (
    ToolResourceError,
    ToolResourceUnavailableError,
    file_sha256,
    platform_key,
    resolve_apache_worker,
    resolve_exiftool,
    tree_sha256,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


def _expected_hidden_creation_flags() -> int:
    if os.name == "nt":
        return subprocess.CREATE_NO_WINDOW
    return 0


def _write_manifest(
    root: Path,
    *,
    available: bool,
    command: tuple[str, ...] = (),
    files: Mapping[str, str] | None = None,
    apache: Mapping[str, object] | None = None,
) -> None:
    path = root / "tools/manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    packaged = {
        platform_key(): {
            "available": available,
            "command": list(command),
            "files": dict(files or {}),
        }
    }
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
            "packaged": packaged,
        },
    }
    if apache is not None:
        payload["apache_worker"] = apache
    _ = path.write_text(json.dumps(payload), encoding="utf-8")


def _apache_manifest_entry(  # noqa: PLR0913
    *,
    available: bool,
    java: str = "",
    worker_jar: str = "",
    files: Mapping[str, str] | None = None,
    java_vendor: str | None = None,
    java_runtime_version: str | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "tika_version": "3.3.2",
        "java_major_version": 21,
        "packaged": {
            platform_key(): {
                "available": available,
                "java": java,
                "worker_jar": worker_jar,
                "files": dict(files or {}),
            }
        },
    }
    if java_vendor is not None:
        result["java_vendor"] = java_vendor
    if java_runtime_version is not None:
        result["java_runtime_version"] = java_runtime_version
    return result


def _successful_version(
    *args: object,
    **kwargs: object,
) -> subprocess.CompletedProcess[bytes]:
    del args, kwargs
    return subprocess.CompletedProcess(
        args=("exiftool", "-ver"),
        returncode=0,
        stdout=b"13.55\n",
        stderr=b"",
    )


def _successful_java_version(
    *args: object,
    **kwargs: object,
) -> subprocess.CompletedProcess[bytes]:
    del args, kwargs
    return subprocess.CompletedProcess(
        args=("java", "-version"),
        returncode=0,
        stdout=b"",
        stderr=b'java version "21.0.11" 2026-04-21 LTS\n',
    )


def _oracle_java_version(
    *args: object,
    **kwargs: object,
) -> subprocess.CompletedProcess[bytes]:
    del args, kwargs
    return subprocess.CompletedProcess(
        args=("java", "-version"),
        returncode=0,
        stdout=b"",
        stderr=(
            b"java.vendor = Oracle Corporation\n"
            b"java.runtime.version = 21.0.12+8-LTS\n"
            b'openjdk version "21.0.12" 2026-07-21 LTS\n'
        ),
    )


def test_packaged_resource_requires_and_verifies_every_command_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = tmp_path / "tools/packaged/exiftool"
    executable.parent.mkdir(parents=True)
    _ = executable.write_bytes(b"controlled executable")
    relative = executable.relative_to(tmp_path).as_posix()
    _write_manifest(
        tmp_path,
        available=True,
        command=(relative,),
        files={relative: file_sha256(executable)},
    )
    monkeypatch.setattr(subprocess, "run", _successful_version)

    resource = resolve_exiftool(root=tmp_path)

    assert resource.command_prefix == (str(executable),)
    assert resource.source == "packaged"

    _ = executable.write_bytes(b"tampered")
    with pytest.raises(ToolResourceError):
        _ = resolve_exiftool(root=tmp_path)


def test_release_resolution_never_falls_back_to_a_system_or_environment_path(
    tmp_path: Path,
) -> None:
    _write_manifest(tmp_path, available=False)

    with pytest.raises(ToolResourceUnavailableError):
        _ = resolve_exiftool(
            root=tmp_path,
            development=False,
            environment={"DOCMETA_EXIFTOOL": "/usr/local/bin/exiftool"},
        )


def test_development_override_is_explicit_and_version_locked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_manifest(tmp_path, available=False)
    executable = tmp_path / "dev-exiftool"
    _ = executable.write_bytes(b"controlled executable")
    monkeypatch.setattr(subprocess, "run", _successful_version)

    resource = resolve_exiftool(
        root=tmp_path,
        development=True,
        environment={"DOCMETA_EXIFTOOL": str(executable)},
    )

    assert resource.command_prefix == (str(executable),)
    assert resource.version == "13.55"


def test_exiftool_version_probe_suppresses_windows_console(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_manifest(tmp_path, available=False)
    executable = tmp_path / "dev-exiftool"
    _ = executable.write_bytes(b"controlled executable")
    observed: dict[str, object] = {}

    def successful_version(
        *args: object,
        **kwargs: object,
    ) -> subprocess.CompletedProcess[bytes]:
        observed.update(kwargs)
        return _successful_version(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", successful_version)

    _ = resolve_exiftool(
        root=tmp_path,
        development=True,
        environment={"DOCMETA_EXIFTOOL": str(executable)},
    )

    assert observed.get("creationflags") == _expected_hidden_creation_flags()


def test_vendored_exiftool_tree_matches_the_locked_manifest() -> None:
    root = Path(__file__).resolve().parents[2]
    payload = cast(
        "object",
        json.loads((root / "tools/manifest.json").read_text(encoding="utf-8")),
    )
    assert isinstance(payload, dict)
    payload_map = cast("dict[str, object]", payload)
    exiftool = payload_map["exiftool"]
    assert isinstance(exiftool, dict)
    exiftool_map = cast("dict[str, object]", exiftool)
    official_source = exiftool_map["official_source"]
    assert isinstance(official_source, dict)
    source_map = cast("dict[str, object]", official_source)
    expected = source_map["tree_sha256"]
    assert isinstance(expected, str)
    source = root / "tools/vendor/exiftool/13.55/source"

    assert tree_sha256(source) == expected


def test_source_manifest_does_not_advertise_ignored_packaged_runtimes() -> None:
    root = Path(__file__).resolve().parents[2]
    payload = cast(
        "object",
        json.loads((root / "tools/manifest.json").read_text(encoding="utf-8")),
    )
    assert isinstance(payload, dict)
    payload_map = cast("dict[str, object]", payload)
    expected_platforms = {
        "darwin-arm64",
        "darwin-x86_64",
        "linux-arm64",
        "linux-x86_64",
        "windows-arm64",
        "windows-x86_64",
    }

    for section_name in ("exiftool", "apache_worker"):
        section = payload_map[section_name]
        assert isinstance(section, dict)
        packaged = cast("dict[str, object]", section)["packaged"]
        assert isinstance(packaged, dict)
        packaged_map = cast("dict[str, object]", packaged)
        assert set(packaged_map) == expected_platforms
        for entry in packaged_map.values():
            assert isinstance(entry, dict)
            entry_map = cast("dict[str, object]", entry)
            assert entry_map["available"] is False
            assert entry_map["files"] == {}


def test_packaged_apache_worker_verifies_java_and_jar_hashes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    java = tmp_path / "runtime/java/bin/java"
    worker_jar = tmp_path / "runtime/apache/worker.jar"
    java.parent.mkdir(parents=True)
    worker_jar.parent.mkdir(parents=True)
    _ = java.write_bytes(b"controlled java")
    _ = worker_jar.write_bytes(b"controlled worker")
    java_relative = java.relative_to(tmp_path).as_posix()
    jar_relative = worker_jar.relative_to(tmp_path).as_posix()
    hashes = {
        java_relative: file_sha256(java),
        jar_relative: file_sha256(worker_jar),
    }
    _write_manifest(
        tmp_path,
        available=False,
        apache=_apache_manifest_entry(
            available=True,
            java=java_relative,
            worker_jar=jar_relative,
            files=hashes,
        ),
    )
    monkeypatch.setattr(subprocess, "run", _successful_java_version)

    resource = resolve_apache_worker(root=tmp_path)

    assert resource.java_executable == java
    assert resource.worker_jar == worker_jar
    assert resource.source == "packaged"

    _ = worker_jar.write_bytes(b"tampered")
    with pytest.raises(ToolResourceError):
        _ = resolve_apache_worker(root=tmp_path)


def test_packaged_apache_worker_rejects_wrong_jdk_vendor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    java = tmp_path / "runtime/java/bin/java"
    worker_jar = tmp_path / "runtime/apache/worker.jar"
    java.parent.mkdir(parents=True)
    worker_jar.parent.mkdir(parents=True)
    _ = java.write_bytes(b"controlled java")
    _ = worker_jar.write_bytes(b"controlled worker")
    java_relative = java.relative_to(tmp_path).as_posix()
    jar_relative = worker_jar.relative_to(tmp_path).as_posix()
    _write_manifest(
        tmp_path,
        available=False,
        apache=_apache_manifest_entry(
            available=True,
            java=java_relative,
            worker_jar=jar_relative,
            files={
                java_relative: file_sha256(java),
                jar_relative: file_sha256(worker_jar),
            },
            java_vendor="Eclipse Adoptium",
            java_runtime_version="21.0.12+8",
        ),
    )
    monkeypatch.setattr(subprocess, "run", _oracle_java_version)

    with pytest.raises(ToolResourceError, match="vendor"):
        _ = resolve_apache_worker(root=tmp_path)


def test_release_apache_resolution_never_uses_development_paths(
    tmp_path: Path,
) -> None:
    _write_manifest(
        tmp_path,
        available=False,
        apache=_apache_manifest_entry(available=False),
    )

    with pytest.raises(ToolResourceUnavailableError):
        _ = resolve_apache_worker(
            root=tmp_path,
            development=False,
            environment={
                "DOCMETA_JAVA": str(tmp_path / "not-used-java"),
                "DOCMETA_APACHE_WORKER_JAR": str(tmp_path / "not-used-worker.jar"),
            },
        )


def test_development_apache_override_is_explicit_and_version_locked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    java = tmp_path / "java"
    worker_jar = tmp_path / "worker.jar"
    _ = java.write_bytes(b"controlled java")
    _ = worker_jar.write_bytes(b"controlled worker")
    _write_manifest(
        tmp_path,
        available=False,
        apache=_apache_manifest_entry(available=False),
    )
    monkeypatch.setattr(subprocess, "run", _successful_java_version)

    resource = resolve_apache_worker(
        root=tmp_path,
        development=True,
        environment={
            "DOCMETA_JAVA": str(java),
            "DOCMETA_APACHE_WORKER_JAR": str(worker_jar),
        },
    )

    assert resource.java_executable == java
    assert resource.worker_jar == worker_jar
    assert resource.java_major_version == 21


def test_java_version_probe_suppresses_windows_console(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    java = tmp_path / "java"
    worker_jar = tmp_path / "worker.jar"
    _ = java.write_bytes(b"controlled java")
    _ = worker_jar.write_bytes(b"controlled worker")
    _write_manifest(
        tmp_path,
        available=False,
        apache=_apache_manifest_entry(available=False),
    )
    observed: dict[str, object] = {}

    def successful_version(
        *args: object,
        **kwargs: object,
    ) -> subprocess.CompletedProcess[bytes]:
        observed.update(kwargs)
        return _successful_java_version(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", successful_version)

    _ = resolve_apache_worker(
        root=tmp_path,
        development=True,
        environment={
            "DOCMETA_JAVA": str(java),
            "DOCMETA_APACHE_WORKER_JAR": str(worker_jar),
        },
    )

    assert observed.get("creationflags") == _expected_hidden_creation_flags()
