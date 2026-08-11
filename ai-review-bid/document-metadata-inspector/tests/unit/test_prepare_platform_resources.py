"""Security regressions for release runtime preparation."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import TYPE_CHECKING

import pytest
from scripts import prepare_platform_resources
from scripts.prepare_platform_resources import _materialize_internal_file_links  # pyright: ignore[reportPrivateUsage]

if TYPE_CHECKING:
    from pathlib import Path


def test_materializes_internal_runtime_file_links(tmp_path: Path) -> None:
    """Safe jlink legal-file aliases become independently hashable files."""
    runtime = tmp_path / "jre"
    source = runtime / "legal/java.base/LICENSE"
    source.parent.mkdir(parents=True)
    _ = source.write_text("controlled license", encoding="utf-8")
    alias = runtime / "legal/java.sql/LICENSE"
    alias.parent.mkdir(parents=True)
    alias.symlink_to("../java.base/LICENSE")

    _materialize_internal_file_links(runtime)

    assert alias.is_file()
    assert not alias.is_symlink()
    assert alias.read_text(encoding="utf-8") == "controlled license"


def test_rejects_external_runtime_link_before_mutating_tree(tmp_path: Path) -> None:
    """A link escaping the generated runtime must fail closed."""
    runtime = tmp_path / "jre"
    runtime.mkdir()
    external = tmp_path / "outside.txt"
    _ = external.write_text("outside", encoding="utf-8")
    unsafe = runtime / "unsafe"
    unsafe.symlink_to(external)

    with pytest.raises(RuntimeError, match="outside"):
        _materialize_internal_file_links(runtime)

    assert unsafe.is_symlink()


def test_prepare_copies_a_supplied_jre_and_worker_without_jlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Windows JRE must be copied verbatim rather than rebuilt with jlink."""
    packaged = tmp_path / "tools/packaged"
    manifest = tmp_path / "tools/manifest.json"
    _ = manifest.parent.mkdir(parents=True)
    _ = manifest.write_text(
        json.dumps(
            {
                "apache_worker": {"packaged": {}},
                "exiftool": {"packaged": {}},
            }
        ),
        encoding="utf-8",
    )
    prebuilt_jre = tmp_path / "prebuilt-jre"
    java = prebuilt_jre / "bin/java.exe"
    _ = java.parent.mkdir(parents=True)
    _ = java.write_bytes(b"controlled vendored java")
    _ = (prebuilt_jre / "release").write_bytes(b"controlled release markers")
    worker_jar = tmp_path / "worker.jar"
    _ = worker_jar.write_bytes(b"controlled vendored worker")
    exiftool = tmp_path / "exiftool"
    executable = exiftool / "exiftool.exe"
    _ = executable.parent.mkdir(parents=True)
    _ = executable.write_bytes(b"controlled exiftool")

    def unexpected_jlink(*_args: object, **_kwargs: object) -> Path:
        msg = "a supplied JRE must not invoke jlink"
        raise AssertionError(msg)

    monkeypatch.setattr(prepare_platform_resources, "_MANIFEST_PATH", manifest)
    monkeypatch.setattr(prepare_platform_resources, "_PACKAGED_ROOT", packaged)
    monkeypatch.setattr(
        prepare_platform_resources,
        "_platform_key",
        lambda: "windows-x86_64",
    )
    monkeypatch.setattr(prepare_platform_resources, "_build_jre", unexpected_jlink)

    result = prepare_platform_resources.prepare(
        prepare_platform_resources.ApacheRuntimeSources(
            java_home=prebuilt_jre,
            worker_jar=worker_jar,
            java_home_kind="jre",
        ),
        exiftool,
        ("exiftool.exe",),
    )

    copied_java = result / "apache/jre/bin/java.exe"
    copied_worker = result / "apache/worker.jar"
    assert copied_java.read_bytes() == b"controlled vendored java"
    assert copied_worker.read_bytes() == b"controlled vendored worker"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    apache = payload["apache_worker"]["packaged"]["windows-x86_64"]
    assert apache == {
        "available": True,
        "java": "tools/packaged/windows-x86_64/apache/jre/bin/java.exe",
        "worker_jar": "tools/packaged/windows-x86_64/apache/worker.jar",
        "files": {
            "tools/packaged/windows-x86_64/apache/jre/bin/java.exe": sha256(
                b"controlled vendored java"
            ).hexdigest(),
            "tools/packaged/windows-x86_64/apache/jre/release": sha256(
                b"controlled release markers"
            ).hexdigest(),
            "tools/packaged/windows-x86_64/apache/worker.jar": sha256(
                b"controlled vendored worker"
            ).hexdigest(),
        },
    }


def test_prepare_builds_a_jre_from_a_supplied_jdk_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Native release preparation must retain the JDK-to-JRE jlink route."""
    packaged = tmp_path / "tools/packaged"
    manifest = tmp_path / "tools/manifest.json"
    _ = manifest.parent.mkdir(parents=True)
    _ = manifest.write_text(
        json.dumps(
            {
                "apache_worker": {"packaged": {}},
                "exiftool": {"packaged": {}},
            }
        ),
        encoding="utf-8",
    )
    jdk = tmp_path / "jdk"
    _ = jdk.mkdir()
    worker_jar = tmp_path / "worker.jar"
    _ = worker_jar.write_bytes(b"controlled worker")
    exiftool = tmp_path / "exiftool"
    _ = (exiftool / "exiftool.exe").parent.mkdir(parents=True)
    _ = (exiftool / "exiftool.exe").write_bytes(b"controlled exiftool")
    builds: list[tuple[Path, Path, Path]] = []

    def build_jre(java_home: Path, destination: Path, cwd: Path) -> Path:
        builds.append((java_home, destination, cwd))
        java = destination / "bin/java"
        _ = java.parent.mkdir(parents=True)
        _ = java.write_bytes(b"controlled linked java")
        return java

    monkeypatch.setattr(prepare_platform_resources, "_MANIFEST_PATH", manifest)
    monkeypatch.setattr(prepare_platform_resources, "_PACKAGED_ROOT", packaged)
    monkeypatch.setattr(
        prepare_platform_resources,
        "_platform_key",
        lambda: "darwin-arm64",
    )
    monkeypatch.setattr(prepare_platform_resources, "_build_jre", build_jre)

    result = prepare_platform_resources.prepare(
        prepare_platform_resources.ApacheRuntimeSources(
            java_home=jdk,
            worker_jar=worker_jar,
            java_home_kind="jdk",
        ),
        exiftool,
        ("exiftool.exe",),
    )

    assert len(builds) == 1
    java_home, destination, cwd = builds[0]
    assert java_home == jdk.resolve()
    assert destination.name == "jre"
    assert destination.parent.name == "apache"
    assert cwd == destination.parents[2]
    assert (result / "apache/jre/bin/java").read_bytes() == b"controlled linked java"
    assert (result / "apache/worker.jar").read_bytes() == b"controlled worker"
