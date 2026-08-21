"""Build the Apache Java worker with a controlled Java runtime."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_BUILD_TIMEOUT_SECONDS = 1200


def _maven_command() -> tuple[str, ...]:
    worker = _PROJECT_ROOT / "java-worker"
    if os.name == "nt":
        wrapper = worker / "mvnw.cmd"
        if not wrapper.is_file():
            msg = "the Maven Wrapper command is missing"
            raise RuntimeError(msg)
        return (
            os.environ.get("COMSPEC", "cmd.exe"),
            "/d",
            "/s",
            "/c",
            str(wrapper),
            "--batch-mode",
            "--no-transfer-progress",
            "verify",
        )
    wrapper = worker / "mvnw"
    if not wrapper.is_file():
        msg = "the Maven Wrapper command is missing"
        raise RuntimeError(msg)
    return ("sh", str(wrapper), "--batch-mode", "--no-transfer-progress", "verify")


def build_worker(java_home: Path) -> Path:
    """Build and return the regular Apache Java worker JAR."""
    environment = {
        **os.environ,
        "JAVA_HOME": str(java_home),
        "PATH": f"{java_home / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}",
    }
    result = subprocess.run(  # noqa: S603
        _maven_command(),
        cwd=_PROJECT_ROOT / "java-worker",
        env=environment,
        check=False,
        timeout=_BUILD_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        msg = "the Apache Java worker build failed"
        raise RuntimeError(msg)
    output = _PROJECT_ROOT / "java-worker/target/document-metadata-apache-worker.jar"
    try:
        metadata = output.lstat()
    except OSError as error:
        msg = "the Apache Java worker JAR is missing"
        raise RuntimeError(msg) from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        msg = "the Apache Java worker JAR is missing"
        raise RuntimeError(msg)
    return output
