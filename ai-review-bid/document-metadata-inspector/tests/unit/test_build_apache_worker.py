"""Regressions for the isolated Apache Java worker builder."""

from __future__ import annotations

import os
import subprocess
from typing import TYPE_CHECKING

import pytest
from scripts import build_apache_worker

if TYPE_CHECKING:
    from pathlib import Path


def test_windows_maven_wrapper_runs_through_command_processor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project(tmp_path, "mvnw.cmd")
    monkeypatch.setattr(build_apache_worker, "_PROJECT_ROOT", project)
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setenv("COMSPEC", r"C:\Windows\System32\cmd.exe")

    command = build_apache_worker._maven_command()  # pyright: ignore[reportPrivateUsage]

    assert command == (
        r"C:\Windows\System32\cmd.exe",
        "/d",
        "/s",
        "/c",
        str(project / "java-worker/mvnw.cmd"),
        "--batch-mode",
        "--no-transfer-progress",
        "verify",
    )


def test_unix_maven_wrapper_uses_shell(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project(tmp_path, "mvnw")
    monkeypatch.setattr(build_apache_worker, "_PROJECT_ROOT", project)
    monkeypatch.setattr(os, "name", "posix")

    assert build_apache_worker._maven_command() == (  # pyright: ignore[reportPrivateUsage]
        "sh",
        str(project / "java-worker/mvnw"),
        "--batch-mode",
        "--no-transfer-progress",
        "verify",
    )


@pytest.mark.parametrize(
    ("returncode", "expected"),
    [
        (1, "the Apache Java worker build failed"),
        (0, "the Apache Java worker JAR is missing"),
    ],
)
def test_build_worker_rejects_failed_build_or_missing_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    returncode: int,
    expected: str,
) -> None:
    project = _project(tmp_path, "mvnw")
    monkeypatch.setattr(build_apache_worker, "_PROJECT_ROOT", project)

    def run(
        *_args: object,
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(("mvnw",), returncode)

    monkeypatch.setattr(subprocess, "run", run)

    with pytest.raises(RuntimeError, match=f"^{expected}$"):
        _ = build_apache_worker.build_worker(tmp_path / "jdk")


def test_build_worker_returns_a_regular_non_symlink_output_jar(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project(tmp_path, "mvnw")
    output = project / "java-worker/target/document-metadata-apache-worker.jar"
    output.parent.mkdir()
    _ = output.write_bytes(b"worker")
    monkeypatch.setattr(build_apache_worker, "_PROJECT_ROOT", project)

    def run(
        *_args: object,
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(("mvnw",), 0)

    monkeypatch.setattr(subprocess, "run", run)

    assert build_apache_worker.build_worker(tmp_path / "jdk") == output


def _project(tmp_path: Path, wrapper: str) -> Path:
    project = tmp_path / "project"
    worker = project / "java-worker"
    worker.mkdir(parents=True)
    _ = (worker / wrapper).write_text("wrapper\n", encoding="utf-8")
    return project
