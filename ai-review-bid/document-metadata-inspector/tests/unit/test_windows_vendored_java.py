"""Regressions for vendored Windows Java release inputs."""

from __future__ import annotations

import copy
import json
import os
import stat
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
from scripts.windows_vendored_java import (
    verify_vendored_windows_java_files,
    worker_inputs_sha256,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


JRE_RELATIVE_PATH = Path(
    "tools/prebuilt/windows-x86_64/OpenJDK21U-jre_x64_windows_hotspot_21.0.12_8.zip"
)
WORKER_RELATIVE_PATH = Path(
    "tools/prebuilt/windows-x86_64/document-metadata-apache-worker.jar"
)


@pytest.fixture
def project(tmp_path: Path) -> Iterator[Path]:
    _write_sources(tmp_path)
    jre = tmp_path / JRE_RELATIVE_PATH
    worker = tmp_path / WORKER_RELATIVE_PATH
    jre.parent.mkdir(parents=True)
    _ = jre.write_bytes(b"synthetic Temurin JRE archive")
    _ = worker.write_bytes(b"synthetic Apache worker")
    _write_manifest(tmp_path)
    return tmp_path


@pytest.mark.parametrize(
    "relative",
    [
        Path("java-worker/pom.xml"),
        Path("java-worker/mvnw"),
        Path("java-worker/mvnw.cmd"),
        Path("java-worker/.mvn/wrapper/maven-wrapper.properties"),
        Path("java-worker/src/main/java/Worker.java"),
        Path("java-worker/src/test/java/WorkerTest.java"),
    ],
)
def test_worker_inputs_hash_changes_for_every_build_input(
    project: Path,
    relative: Path,
) -> None:
    before = worker_inputs_sha256(project)
    path = project / relative
    _ = path.write_text(
        path.read_text(encoding="utf-8") + "changed\n", encoding="utf-8"
    )

    assert worker_inputs_sha256(project) != before


def test_worker_inputs_hash_ignores_timestamps_and_target(project: Path) -> None:
    before = worker_inputs_sha256(project)
    pom = project / "java-worker/pom.xml"
    os.utime(pom, (pom.stat().st_atime + 2, pom.stat().st_mtime + 2))
    target = project / "java-worker/target"
    target.mkdir()
    _ = (target / "ignored.jar").write_bytes(b"build output")

    assert worker_inputs_sha256(project) == before


@pytest.mark.parametrize(
    "relative",
    [Path("java-worker"), Path("java-worker/src"), Path("java-worker/.mvn")],
)
def test_worker_inputs_reject_a_symlinked_ancestor(
    project: Path,
    relative: Path,
) -> None:
    source = project / relative
    external = project.parent / f"external-{'-'.join(relative.parts)}"
    _ = source.replace(external)
    source.symlink_to(external, target_is_directory=True)

    with pytest.raises(RuntimeError):
        _ = worker_inputs_sha256(project)


def test_verifier_returns_the_pinned_regular_files(project: Path) -> None:
    files = verify_vendored_windows_java_files(project)

    assert files.jre_archive == project / JRE_RELATIVE_PATH
    assert files.worker_jar == project / WORKER_RELATIVE_PATH
    assert files.java_runtime_version == "21.0.12+8"


@pytest.mark.parametrize("manifest", [None, [], {"apache_worker": []}])
def test_verifier_rejects_malformed_manifest_types(
    project: Path,
    manifest: object,
) -> None:
    _write_json(project / "tools/manifest.json", manifest)

    with pytest.raises(TypeError):
        _ = verify_vendored_windows_java_files(project)


@pytest.mark.parametrize("path", ["", "/unsafe/input", "../input"])
def test_verifier_rejects_unsafe_or_escaping_worker_paths(
    project: Path,
    path: str,
) -> None:
    manifest = _manifest(project)
    _worker(manifest)["path"] = path
    _write_json(project / "tools/manifest.json", manifest)

    with pytest.raises(RuntimeError):
        _ = verify_vendored_windows_java_files(project)


@pytest.mark.parametrize("path", ["", "/unsafe/input", "../../input"])
def test_verifier_rejects_unsafe_or_escaping_jre_paths(
    project: Path,
    path: str,
) -> None:
    manifest = _manifest(project)
    _jre(manifest)["vendored_path"] = path
    _write_json(project / "tools/manifest.json", manifest)

    with pytest.raises(RuntimeError):
        _ = verify_vendored_windows_java_files(project)


@pytest.mark.parametrize("relative", [JRE_RELATIVE_PATH, WORKER_RELATIVE_PATH])
def test_verifier_rejects_absent_empty_and_symbolic_link_files(
    project: Path,
    relative: Path,
) -> None:
    path = project / relative
    path.unlink()
    with pytest.raises(RuntimeError):
        _ = verify_vendored_windows_java_files(project)

    _ = path.write_bytes(b"")
    with pytest.raises(RuntimeError):
        _ = verify_vendored_windows_java_files(project)

    target = path.with_name(f"{path.name}.target")
    _ = target.write_bytes(b"real file")
    path.unlink()
    path.symlink_to(target.name)
    with pytest.raises(RuntimeError):
        _ = verify_vendored_windows_java_files(project)


def test_verifier_rejects_a_sparse_placeholder(project: Path) -> None:
    worker = project / WORKER_RELATIVE_PATH
    with worker.open("wb") as stream:
        stream.truncate(2 * 1024 * 1024)
    if not _is_sparse(worker.stat()):
        pytest.skip("the filesystem cannot create a sparse fixture")
    _write_manifest(project)

    with pytest.raises(RuntimeError):
        _ = verify_vendored_windows_java_files(project)


@pytest.mark.parametrize(
    ("path", "field", "value"),
    [
        (WORKER_RELATIVE_PATH, "size", 0),
        (WORKER_RELATIVE_PATH, "sha256", "0" * 64),
        (WORKER_RELATIVE_PATH, "source_tree_sha256", "0" * 64),
        (WORKER_RELATIVE_PATH, "build_java_runtime_version", "wrong"),
        (WORKER_RELATIVE_PATH, "path", "tools/prebuilt/windows-x86_64/wrong.jar"),
        (JRE_RELATIVE_PATH, "size", 0),
        (JRE_RELATIVE_PATH, "sha256", "0" * 64),
        (JRE_RELATIVE_PATH, "archive_type", "tar.gz"),
    ],
)
def test_verifier_rejects_wrong_metadata(
    project: Path,
    path: Path,
    field: str,
    value: object,
) -> None:
    manifest = _manifest(project)
    config = _worker(manifest) if path == WORKER_RELATIVE_PATH else _jre(manifest)
    config[field] = value
    _write_json(project / "tools/manifest.json", manifest)

    with pytest.raises((TypeError, RuntimeError)):
        _ = verify_vendored_windows_java_files(project)


def test_verifier_rejects_stale_worker_input_hash(project: Path) -> None:
    _ = (project / "java-worker/pom.xml").write_text("changed\n", encoding="utf-8")

    with pytest.raises(RuntimeError):
        _ = verify_vendored_windows_java_files(project)


def test_verifier_rejects_a_different_self_consistent_jre(project: Path) -> None:
    relative = Path(
        "tools/prebuilt/windows-x86_64/OpenJDK21U-jre_x64_windows_hotspot_21.0.11_9.zip"
    )
    alternate = project / relative
    _ = alternate.write_bytes(b"different synthetic Temurin JRE archive")
    manifest = _manifest(project)
    jre = _jre(manifest)
    jre["url"] = (
        "https://github.com/adoptium/temurin21-binaries/releases/"
        "download/jdk-21.0.11%2B9/"
        "OpenJDK21U-jre_x64_windows_hotspot_21.0.11_9.zip"
    )
    jre["vendored_path"] = relative.as_posix()
    jre["size"] = alternate.stat().st_size
    jre["sha256"] = _hash(alternate)
    _write_json(project / "tools/manifest.json", manifest)

    with pytest.raises(RuntimeError):
        _ = verify_vendored_windows_java_files(project)


def test_verifier_rejects_a_different_worker_artifact_version(
    project: Path,
) -> None:
    manifest = _manifest(project)
    _worker(manifest)["artifact_version"] = "0.2.0"
    _write_json(project / "tools/manifest.json", manifest)

    with pytest.raises(RuntimeError):
        _ = verify_vendored_windows_java_files(project)


def _write_sources(project: Path) -> None:
    for relative, contents in {
        "java-worker/pom.xml": "<project/>\n",
        "java-worker/mvnw": "#!/bin/sh\n",
        "java-worker/mvnw.cmd": "@echo off\n",
        "java-worker/.mvn/wrapper/maven-wrapper.properties": "wrapper\n",
        "java-worker/src/main/java/Worker.java": "class Worker {}\n",
        "java-worker/src/test/java/WorkerTest.java": "class WorkerTest {}\n",
    }.items():
        path = project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(contents, encoding="utf-8")


def _write_manifest(project: Path) -> None:
    jre = project / JRE_RELATIVE_PATH
    worker = project / WORKER_RELATIVE_PATH
    manifest = {
        "apache_worker": {
            "vendored": {
                "windows-x86_64": {
                    "path": WORKER_RELATIVE_PATH.as_posix(),
                    "size": 0,
                    "sha256": "0" * 64,
                    "source_tree_sha256": "0" * 64,
                    "artifact_version": "0.1.0",
                    "build_java_runtime_version": "21.0.12+8",
                    "build_command": [
                        "mvnw",
                        "--batch-mode",
                        "--no-transfer-progress",
                        "verify",
                    ],
                }
            }
        },
        "temurin_jre": {
            "archives": {
                "windows-x86_64": {
                    "url": (
                        "https://github.com/adoptium/temurin21-binaries/releases/"
                        "download/jdk-21.0.12%2B8/"
                        "OpenJDK21U-jre_x64_windows_hotspot_21.0.12_8.zip"
                    ),
                    "sha256": (
                        "b8aa18fef5edb69bee8618f99677d66d0873d22cb40d974c15ac9ffc"
                        "decf73ba"
                    ),
                    "archive_type": "zip",
                    "vendored_path": JRE_RELATIVE_PATH.as_posix(),
                    "size": 0,
                }
            }
        },
    }
    worker_config = _worker(manifest)
    worker_config["size"] = worker.stat().st_size
    worker_config["sha256"] = _hash(worker)
    worker_config["source_tree_sha256"] = worker_inputs_sha256(project)
    jre_config = _jre(manifest)
    jre_config["size"] = jre.stat().st_size
    jre_config["sha256"] = _hash(jre)
    _write_json(project / "tools/manifest.json", manifest)


def _manifest(project: Path) -> dict[str, object]:
    return cast(
        "dict[str, object]",
        copy.deepcopy(json.loads((project / "tools/manifest.json").read_text())),
    )


def _worker(manifest: dict[str, object]) -> dict[str, object]:
    return cast("dict[str, object]", manifest["apache_worker"])["vendored"][
        "windows-x86_64"
    ]  # type: ignore[index, return-value]


def _jre(manifest: dict[str, object]) -> dict[str, object]:
    return cast("dict[str, object]", manifest["temurin_jre"])["archives"][
        "windows-x86_64"
    ]  # type: ignore[index, return-value]


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(value), encoding="utf-8")


def _hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _is_sparse(metadata: os.stat_result) -> bool:
    if os.name == "nt":
        return bool(metadata.st_file_attributes & stat.FILE_ATTRIBUTE_SPARSE_FILE)
    return (
        hasattr(metadata, "st_blocks") and metadata.st_blocks * 512 < metadata.st_size
    )
