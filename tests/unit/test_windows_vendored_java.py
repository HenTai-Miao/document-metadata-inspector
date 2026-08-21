"""Regressions for vendored Windows Java release inputs."""

from __future__ import annotations

import copy
import io
import json
import os
import stat
import struct
import subprocess
import threading
import zipfile
import zlib
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, cast

import pytest
from scripts import windows_vendored_java
from scripts.windows_vendored_java import (
    VendoredWindowsJavaFiles,
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
JRE_ROOT = "jdk-21.0.12+8-jre"
type ArchiveMember = tuple[str | zipfile.ZipInfo, bytes]


class _SyntheticClock:
    values: Iterator[float]

    def __init__(self, values: tuple[float, ...]) -> None:
        self.values = iter(values)

    def monotonic(self) -> float:
        return next(self.values)


class _HangingNativeProcess:
    stdout: io.BytesIO
    waits: list[float]

    def __init__(self, waits: list[float]) -> None:
        self.stdout = io.BytesIO()
        self.waits = waits

    def wait(self, *, timeout: float) -> int:
        self.waits.append(timeout)
        return 0

    def kill(self) -> None:
        return None


class _HangingNativeThread:
    joins: ClassVar[list[float]] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        _ = args
        _ = kwargs

    def start(self) -> None:
        return None

    def join(self, timeout: float) -> None:
        _HangingNativeThread.joins.append(timeout)

    def is_alive(self) -> bool:
        return True


def test_preparation_extracts_one_verified_jre_and_preserves_legal_file(
    project: Path,
    tmp_path: Path,
) -> None:
    legal_contents = b"synthetic legal notice\r\n"
    _write_jre_archive(project, legal_contents=legal_contents)
    _write_manifest(project)

    prepared = windows_vendored_java.prepare_vendored_windows_java(
        project, tmp_path / "cache"
    )

    assert prepared.java_home == (
        tmp_path / "cache" / prepared.java_home.parents[1].name / "jre" / JRE_ROOT
    )
    assert prepared.worker_jar == prepared.java_home.parents[1] / "worker.jar"
    assert (
        prepared.java_home / "legal/java.base/LICENSE"
    ).read_bytes() == legal_contents
    assert (prepared.java_home.parents[1] / "integrity.json").is_file()


def test_extraction_rejects_raw_nul_and_backslash_member_metadata(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "crafted.zip"
    destination = tmp_path / "destination"
    raw_name = b"safe\0back\\slash"
    _write_raw_stored_zip(archive, raw_name)

    with zipfile.ZipFile(archive) as package:
        member = package.infolist()[0]

    assert member.orig_filename == raw_name.decode("ascii")
    assert member.filename == "safe"
    with pytest.raises(RuntimeError):
        _ = windows_vendored_java._extract_windows_jre(  # pyright: ignore[reportPrivateUsage]
            archive, destination
        )
    assert not destination.exists()


@pytest.mark.parametrize(
    "member_name",
    [
        "COM¹",
        "COM²",
        "COM³",
        "LPT¹",
        "LPT²",
        "LPT³",
        "COM¹.txt",
        "COM².txt",
        "COM³.txt",
        "LPT¹.txt",
        "LPT².txt",
        "LPT³.txt",
    ],
)
def test_preparation_rejects_windows_superscript_device_names(
    project: Path,
    tmp_path: Path,
    member_name: str,
) -> None:
    _write_jre_archive(project, extra_members=[(member_name, b"malicious")])
    _write_manifest(project)

    with pytest.raises(RuntimeError):
        _ = windows_vendored_java.prepare_vendored_windows_java(
            project, tmp_path / "cache"
        )


@pytest.mark.parametrize(
    "unsafe_member",
    [
        "../outside",
        "C:/outside",
        "NUL",
        f"{JRE_ROOT}/bin/java.exe.",
        f"{JRE_ROOT}/trailing /file",
    ],
)
def test_preparation_rejects_an_escaping_or_drive_archive_member(
    project: Path,
    tmp_path: Path,
    unsafe_member: str,
) -> None:
    _write_jre_archive(project, extra_members=[(unsafe_member, b"malicious")])
    _write_manifest(project)

    with pytest.raises(RuntimeError):
        _ = windows_vendored_java.prepare_vendored_windows_java(
            project, tmp_path / "cache"
        )


def test_preparation_rejects_case_insensitive_duplicate_archive_members(
    project: Path,
    tmp_path: Path,
) -> None:
    _write_jre_archive(
        project,
        extra_members=[(f"{JRE_ROOT.upper()}/BIN/JAVA.EXE", _amd64_pe())],
    )
    _write_manifest(project)

    with pytest.raises(RuntimeError):
        _ = windows_vendored_java.prepare_vendored_windows_java(
            project, tmp_path / "cache"
        )


def test_preparation_rejects_a_symbolic_link_in_the_archive(
    project: Path,
    tmp_path: Path,
) -> None:
    link = zipfile.ZipInfo(f"{JRE_ROOT}/bin/linked-java.exe")
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    _write_jre_archive(project, extra_members=[(link, b"java.exe")])
    _write_manifest(project)

    with pytest.raises(RuntimeError):
        _ = windows_vendored_java.prepare_vendored_windows_java(
            project, tmp_path / "cache"
        )


def test_preparation_rejects_archive_member_count_over_the_budget(
    project: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(windows_vendored_java, "_MAX_ZIP_ENTRIES", 4, raising=False)
    _write_jre_archive(project, extra_members=[("another-file", b"extra")])
    _write_manifest(project)

    with pytest.raises(RuntimeError):
        _ = windows_vendored_java.prepare_vendored_windows_java(
            project, tmp_path / "cache"
        )


def test_preparation_rejects_archive_expansion_over_the_budget(
    project: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        windows_vendored_java, "_MAX_ZIP_EXPANDED_BYTES", 1, raising=False
    )
    _write_jre_archive(project)
    _write_manifest(project)

    with pytest.raises(RuntimeError):
        _ = windows_vendored_java.prepare_vendored_windows_java(
            project, tmp_path / "cache"
        )


def test_preparation_rejects_missing_jre_home(project: Path, tmp_path: Path) -> None:
    members = [
        member for member in _valid_jre_members() if member[0] != f"{JRE_ROOT}/release"
    ]
    _write_jre_archive(project, members=members)
    _write_manifest(project)

    with pytest.raises(RuntimeError):
        _ = windows_vendored_java.prepare_vendored_windows_java(
            project, tmp_path / "cache"
        )


def test_preparation_rejects_duplicate_jre_homes(project: Path, tmp_path: Path) -> None:
    other_root = "another-jre"
    members = _valid_jre_members()
    members.extend(
        (_archive_member_path(path).replace(JRE_ROOT, other_root, 1), contents)
        for path, contents in _valid_jre_members()
    )
    _write_jre_archive(project, members=members)
    _write_manifest(project)

    with pytest.raises(RuntimeError):
        _ = windows_vendored_java.prepare_vendored_windows_java(
            project, tmp_path / "cache"
        )


def test_preparation_rejects_non_amd64_java_executable(
    project: Path,
    tmp_path: Path,
) -> None:
    members = _valid_jre_members()
    _replace_member(members, f"{JRE_ROOT}/bin/java.exe", _amd64_pe(0x14C))
    _write_jre_archive(project, members=members)
    _write_manifest(project)

    with pytest.raises(RuntimeError):
        _ = windows_vendored_java.prepare_vendored_windows_java(
            project, tmp_path / "cache"
        )


@pytest.mark.parametrize(
    "marker",
    [
        "IMPLEMENTOR",
        "JAVA_RUNTIME_VERSION",
        "OS_ARCH",
        "OS_NAME",
        "IMAGE_TYPE",
    ],
)
def test_preparation_rejects_wrong_release_markers(
    project: Path,
    tmp_path: Path,
    marker: str,
) -> None:
    _write_jre_archive(project, release_markers={marker: "wrong"})
    _write_manifest(project)

    with pytest.raises(RuntimeError):
        _ = windows_vendored_java.prepare_vendored_windows_java(
            project, tmp_path / "cache"
        )


def test_preparation_rebuilds_a_tampered_cache_from_the_verified_archive(
    project: Path,
    tmp_path: Path,
) -> None:
    _write_jre_archive(project)
    _write_manifest(project)
    cache = tmp_path / "cache"

    first = windows_vendored_java.prepare_vendored_windows_java(project, cache)
    java = first.java_home / "bin/java.exe"
    _ = java.write_bytes(b"tampered")

    second = windows_vendored_java.prepare_vendored_windows_java(project, cache)

    assert second.java_home == first.java_home
    assert (second.java_home / "bin/java.exe").read_bytes() == _amd64_pe()


def test_preparation_rejects_a_jre_archive_swapped_after_verification(
    project: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_jre_archive(project, legal_contents=b"verified JRE")
    _write_manifest(project)
    files = verify_vendored_windows_java_files(project)
    _write_jre_archive(project, legal_contents=b"swapped JRE")

    def verifier(_project_root: Path) -> VendoredWindowsJavaFiles:
        return files

    monkeypatch.setattr(
        windows_vendored_java, "verify_vendored_windows_java_files", verifier
    )

    with pytest.raises(RuntimeError):
        _ = windows_vendored_java.prepare_vendored_windows_java(
            project, tmp_path / "cache"
        )


def test_preparation_rejects_a_worker_jar_swapped_after_verification(
    project: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_jre_archive(project)
    _write_manifest(project)
    files = verify_vendored_windows_java_files(project)
    _ = (project / WORKER_RELATIVE_PATH).write_bytes(b"swapped worker JAR")

    def verifier(_project_root: Path) -> VendoredWindowsJavaFiles:
        return files

    monkeypatch.setattr(
        windows_vendored_java, "verify_vendored_windows_java_files", verifier
    )

    with pytest.raises(RuntimeError):
        _ = windows_vendored_java.prepare_vendored_windows_java(
            project, tmp_path / "cache"
        )


def test_preparation_returns_a_verified_worker_snapshot(
    project: Path,
    tmp_path: Path,
) -> None:
    _write_jre_archive(project)
    _write_manifest(project)
    prepared = windows_vendored_java.prepare_vendored_windows_java(
        project, tmp_path / "cache"
    )

    assert prepared.worker_jar == prepared.java_home.parents[1] / "worker.jar"
    assert (
        prepared.worker_jar.read_bytes()
        == (project / WORKER_RELATIVE_PATH).read_bytes()
    )


def test_preparation_rejects_a_symlinked_cache_root_on_a_cache_hit(
    project: Path,
    tmp_path: Path,
) -> None:
    _write_jre_archive(project)
    _write_manifest(project)
    external_cache = tmp_path / "external-cache"
    _ = windows_vendored_java.prepare_vendored_windows_java(project, external_cache)
    cache = tmp_path / "cache-link"
    cache.symlink_to(external_cache, target_is_directory=True)

    with pytest.raises(RuntimeError):
        _ = windows_vendored_java.prepare_vendored_windows_java(project, cache)


def test_preparation_rejects_a_symlinked_cache_ancestor_on_a_cache_hit(
    project: Path,
    tmp_path: Path,
) -> None:
    _write_jre_archive(project)
    _write_manifest(project)
    external_parent = tmp_path / "external-parent"
    external_cache = external_parent / "cache"
    _ = windows_vendored_java.prepare_vendored_windows_java(project, external_cache)
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(external_parent, target_is_directory=True)

    with pytest.raises(RuntimeError):
        _ = windows_vendored_java.prepare_vendored_windows_java(
            project, linked_parent / "cache"
        )


def test_repository_relative_output_rejects_a_symlinked_cache_ancestor(
    project: Path,
    tmp_path: Path,
) -> None:
    external = tmp_path / "external"
    external.mkdir()
    linked = project / "linked-cache-parent"
    linked.symlink_to(external, target_is_directory=True)

    with pytest.raises(RuntimeError):
        _ = windows_vendored_java._repository_relative_path(  # pyright: ignore[reportPrivateUsage]
            project, linked / "cache" / "jre"
        )


def test_preparation_rebuilds_a_cache_with_a_forged_integrity_record(
    project: Path,
    tmp_path: Path,
) -> None:
    _write_jre_archive(project)
    _write_manifest(project)
    cache = tmp_path / "cache"
    first = windows_vendored_java.prepare_vendored_windows_java(project, cache)
    java = first.java_home / "bin/java.exe"
    poisoned = _amd64_pe() + b"poisoned cache entry"
    _ = java.write_bytes(poisoned)

    integrity_path = first.java_home.parents[1] / "integrity.json"
    integrity = cast(
        "dict[str, object]", json.loads(integrity_path.read_text(encoding="utf-8"))
    )
    records = cast("list[dict[str, object]]", integrity["files"])
    java_path = java.relative_to(first.java_home.parents[1]).as_posix()
    for record in records:
        if record["path"] == java_path:
            record["sha256"] = sha256(poisoned).hexdigest()
            record["size"] = len(poisoned)
            break
    else:
        msg = "synthetic cache integrity lacks java.exe"
        raise AssertionError(msg)
    _ = integrity_path.write_text(json.dumps(integrity), encoding="utf-8")

    second = windows_vendored_java.prepare_vendored_windows_java(project, cache)

    assert second.java_home == first.java_home
    assert (second.java_home / "bin/java.exe").read_bytes() == _amd64_pe()


def test_preparation_preserves_an_explicit_empty_archive_directory(
    project: Path,
    tmp_path: Path,
) -> None:
    empty_directory = zipfile.ZipInfo(f"{JRE_ROOT}/empty/")
    empty_directory.external_attr = (stat.S_IFDIR | 0o755) << 16
    _write_jre_archive(project, extra_members=[(empty_directory, b"")])
    _write_manifest(project)

    prepared = windows_vendored_java.prepare_vendored_windows_java(
        project, tmp_path / "cache"
    )

    assert (prepared.java_home / "empty").is_dir()


def test_preparation_uses_a_new_cache_path_when_the_input_changes(
    project: Path,
    tmp_path: Path,
) -> None:
    _write_jre_archive(project, legal_contents=b"first legal notice")
    _write_manifest(project)
    cache = tmp_path / "cache"
    first = windows_vendored_java.prepare_vendored_windows_java(project, cache)

    _write_jre_archive(project, legal_contents=b"changed legal notice")
    _write_manifest(project)
    second = windows_vendored_java.prepare_vendored_windows_java(project, cache)

    assert second.java_home.parents[1] != first.java_home.parents[1]
    assert first.java_home.is_dir()
    assert second.java_home.is_dir()


def test_preparation_runs_the_native_windows_probe_with_bounded_output(
    project: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_jre_archive(project)
    _write_manifest(project)
    observed: dict[str, object] = {}

    class Process:
        stdout: io.BytesIO
        returncode: int

        def __init__(self) -> None:
            self.stdout = io.BytesIO(
                b"".join(
                    (
                        b"java.vendor = Eclipse Adoptium\n",
                        b"java.runtime.version = 21.0.12+8-LTS\n",
                    )
                )
            )
            self.returncode = 0

        def wait(self, *, timeout: float) -> int:
            observed["timeout"] = timeout
            return self.returncode

        def kill(self) -> None:
            msg = "the successful probe must not be killed"
            raise AssertionError(msg)

    def popen(command: tuple[str, ...], **kwargs: object) -> Process:
        observed["command"] = command
        observed["kwargs"] = kwargs
        return Process()

    monkeypatch.setattr(windows_vendored_java, "_is_native_windows", lambda: True)
    monkeypatch.setattr(subprocess, "Popen", popen)

    prepared = windows_vendored_java.prepare_vendored_windows_java(
        project, tmp_path / "cache"
    )

    assert observed["command"] == (
        str(prepared.java_home / "bin/java.exe"),
        "-XshowSettings:properties",
        "-version",
    )
    assert 0 < cast("float", observed["timeout"]) <= 15
    assert observed["kwargs"] == {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
    }


def test_native_windows_probe_rejects_more_than_64_kib_of_output(
    project: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_jre_archive(project)
    _write_manifest(project)

    class Process:
        stdout: io.BytesIO
        returncode: int

        def __init__(self) -> None:
            self.stdout = io.BytesIO(b"x" * (64 * 1024 + 1))
            self.returncode = 0

        def wait(self, *, timeout: float) -> int:
            _ = timeout
            return self.returncode

        def kill(self) -> None:
            return None

    monkeypatch.setattr(windows_vendored_java, "_is_native_windows", lambda: True)

    def popen(*_args: object, **_kwargs: object) -> Process:
        return Process()

    monkeypatch.setattr(subprocess, "Popen", popen)

    with pytest.raises(RuntimeError):
        _ = windows_vendored_java.prepare_vendored_windows_java(
            project, tmp_path / "cache"
        )


def test_native_windows_probe_uses_one_15_second_deadline(
    project: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_jre_archive(project)
    _write_manifest(project)
    observed: dict[str, float] = {}

    class Clock:
        values: Iterator[float]

        def __init__(self) -> None:
            self.values = iter((100.0, 100.0, 114.5))

        def monotonic(self) -> float:
            return next(self.values)

    class Process:
        stdout: io.BytesIO
        returncode: int

        def __init__(self) -> None:
            self.stdout = io.BytesIO(
                b"".join(
                    (
                        b"java.vendor = Eclipse Adoptium\n",
                        b"java.runtime.version = 21.0.12+8-LTS\n",
                    )
                )
            )
            self.returncode = 0

        def wait(self, *, timeout: float) -> int:
            observed["timeout"] = timeout
            return self.returncode

        def kill(self) -> None:
            msg = "the successful probe must not be killed"
            raise AssertionError(msg)

    def popen(*_args: object, **_kwargs: object) -> Process:
        return Process()

    monkeypatch.setattr(windows_vendored_java, "_is_native_windows", lambda: True)
    monkeypatch.setattr(windows_vendored_java, "time", Clock(), raising=False)
    monkeypatch.setattr(subprocess, "Popen", popen)

    _ = windows_vendored_java.prepare_vendored_windows_java(project, tmp_path / "cache")

    assert observed["timeout"] == 0.5


def test_native_windows_probe_does_not_extend_the_deadline_during_cleanup(
    project: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_jre_archive(project)
    _write_manifest(project)
    thread_joins: list[float] = []
    process_waits: list[float] = []

    def popen(*_args: object, **_kwargs: object) -> _HangingNativeProcess:
        return _HangingNativeProcess(process_waits)

    monkeypatch.setattr(windows_vendored_java, "_is_native_windows", lambda: True)
    monkeypatch.setattr(
        windows_vendored_java, "time", _SyntheticClock((100.0, 115.0, 115.0, 115.0))
    )
    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setattr(_HangingNativeThread, "joins", thread_joins)
    monkeypatch.setattr(threading, "Thread", _HangingNativeThread)

    with pytest.raises(RuntimeError):
        _ = windows_vendored_java.prepare_vendored_windows_java(
            project, tmp_path / "cache"
        )

    assert thread_joins == [0.0, 0.0]
    assert process_waits == []


def test_static_macos_validation_never_runs_a_subprocess(
    project: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_jre_archive(project)
    _write_manifest(project)
    monkeypatch.setattr(windows_vendored_java, "_is_native_windows", lambda: False)

    def unexpected_process(*_args: object, **_kwargs: object) -> None:
        msg = "static validation must not run a subprocess"
        raise AssertionError(msg)

    monkeypatch.setattr(subprocess, "Popen", unexpected_process)

    prepared = windows_vendored_java.prepare_vendored_windows_java(
        project, tmp_path / "cache"
    )

    assert prepared.java_home.is_dir()


@pytest.fixture
def project(tmp_path: Path) -> Path:
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
        _ = stream.truncate(2 * 1024 * 1024)
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
    manifest: dict[str, object] = {
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
    loaded = cast("object", json.loads((project / "tools/manifest.json").read_text()))
    if not isinstance(loaded, dict):
        msg = "synthetic manifest must be an object"
        raise TypeError(msg)
    return copy.deepcopy(cast("dict[str, object]", loaded))


def _worker(manifest: dict[str, object]) -> dict[str, object]:
    apache = cast("dict[str, object]", manifest["apache_worker"])
    vendored = cast("dict[str, object]", apache["vendored"])
    return cast("dict[str, object]", vendored["windows-x86_64"])


def _jre(manifest: dict[str, object]) -> dict[str, object]:
    temurin = cast("dict[str, object]", manifest["temurin_jre"])
    archives = cast("dict[str, object]", temurin["archives"])
    return cast("dict[str, object]", archives["windows-x86_64"])


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


def _write_jre_archive(
    project: Path,
    *,
    legal_contents: bytes = b"synthetic legal notice\n",
    release_markers: dict[str, str] | None = None,
    extra_members: list[ArchiveMember] | None = None,
    members: list[ArchiveMember] | None = None,
) -> None:
    archive_path = project / JRE_RELATIVE_PATH
    archive_path.unlink(missing_ok=True)
    archive_members = (
        _valid_jre_members(legal_contents, release_markers)
        if members is None
        else members
    )
    if extra_members is not None:
        archive_members.extend(extra_members)
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_STORED) as archive:
        for member, contents in archive_members:
            archive.writestr(member, contents)


def _valid_jre_members(
    legal_contents: bytes = b"synthetic legal notice\n",
    release_markers: dict[str, str] | None = None,
) -> list[ArchiveMember]:
    markers = {
        "IMPLEMENTOR": "Eclipse Adoptium",
        "JAVA_RUNTIME_VERSION": "21.0.12+8-LTS",
        "OS_ARCH": "x86_64",
        "OS_NAME": "Windows",
        "IMAGE_TYPE": "JRE",
    }
    if release_markers is not None:
        markers.update(release_markers)
    release = "".join(f'{name}="{value}"\n' for name, value in markers.items())
    return [
        (f"{JRE_ROOT}/bin/java.exe", _amd64_pe()),
        (f"{JRE_ROOT}/bin/server/jvm.dll", _amd64_pe()),
        (f"{JRE_ROOT}/release", release.encode("utf-8")),
        (f"{JRE_ROOT}/legal/java.base/LICENSE", legal_contents),
    ]


def _replace_member(
    members: list[ArchiveMember],
    path: str,
    contents: bytes,
) -> None:
    for index, (member_path, _member_contents) in enumerate(members):
        if isinstance(member_path, str) and member_path == path:
            members[index] = (member_path, contents)
            return
    msg = f"missing synthetic ZIP member: {path}"
    raise AssertionError(msg)


def _archive_member_path(member: str | zipfile.ZipInfo) -> str:
    if isinstance(member, str):
        return member
    msg = "synthetic member must be a path string"
    raise AssertionError(msg)


def _amd64_pe(machine: int = 0x8664) -> bytes:
    executable = bytearray(0x46)
    executable[:2] = b"MZ"
    executable[0x3C:0x40] = (0x40).to_bytes(4, "little")
    executable[0x40:0x44] = b"PE\0\0"
    executable[0x44:0x46] = machine.to_bytes(2, "little")
    return bytes(executable)


def _write_raw_stored_zip(path: Path, member_name: bytes) -> None:
    """Write a one-member ZIP whose raw central-directory name is deliberate."""
    contents = b"x"
    checksum = zlib.crc32(contents) & 0xFFFFFFFF
    local_header = struct.pack(
        "<IHHHHHIIIHH",
        0x04034B50,
        20,
        0,
        0,
        0,
        0,
        checksum,
        len(contents),
        len(contents),
        len(member_name),
        0,
    )
    central_header = struct.pack(
        "<IHHHHHHIIIHHHHHII",
        0x02014B50,
        0x0314,
        20,
        0,
        0,
        0,
        0,
        checksum,
        len(contents),
        len(contents),
        len(member_name),
        0,
        0,
        0,
        0,
        0,
        0,
    )
    central_offset = len(local_header) + len(member_name) + len(contents)
    end_record = struct.pack(
        "<IHHHHIIH",
        0x06054B50,
        0,
        0,
        1,
        1,
        len(central_header) + len(member_name),
        central_offset,
        0,
    )
    _ = path.write_bytes(
        local_header
        + member_name
        + contents
        + central_header
        + member_name
        + end_record
    )
