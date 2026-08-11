"""Windows x64 embedded-runtime assembly contracts."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import TYPE_CHECKING, cast
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from scripts import windows_embedded_runtime
from scripts.windows_embedded_runtime import (
    WindowsRuntimeSources,
    assemble_windows_embedded_runtime,
    verify_runtime_inventory,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path


def _write(path: Path, contents: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_bytes(contents)
    return path


def _project(root: Path) -> Path:
    project = root / "project"
    _ = _write(
        project / "src/document_metadata_inspector/cli.py",
        b"def main(): pass\n",
    )
    _ = _write(project / "src/document_metadata_inspector/__init__.py", b"")
    _ = _write(project / "src/xlsx_metadata_forensics/__init__.py", b"")
    _ = _write(project / "THIRD_PARTY_NOTICES.md", b"controlled notices\n")
    manifest: dict[str, object] = {
        "schema_version": "1",
        "exiftool": {
            "version": "13.55",
            "official_source": {
                "url": "https://example.invalid/exiftool.tar.gz",
                "sha256": "0" * 64,
                "directory": "tools/vendor/exiftool/13.55/source",
                "tree_sha256": "1" * 64,
            },
            "packaged": {
                "windows-x86_64": {
                    "available": False,
                    "command": [],
                    "files": {},
                }
            },
        },
        "apache_worker": {
            "tika_version": "3.3.2",
            "java_major_version": 21,
            "java_vendor": "Eclipse Adoptium",
            "java_runtime_version": "21.0.12+8",
            "packaged": {
                "windows-x86_64": {
                    "available": False,
                    "java": "",
                    "worker_jar": "",
                    "files": {},
                }
            },
        },
    }
    _ = _write(
        project / "tools/manifest.json",
        (json.dumps(manifest) + "\n").encode(),
    )
    return project


def _sources(root: Path) -> WindowsRuntimeSources:
    python = root / "python"
    _ = _write(python / "python.exe", b"controlled amd64 python")
    _ = _write(python / "python312.dll", b"controlled python dll")
    _ = _write(python / "Lib/site-packages/dependency.pyd", b"controlled wheel")
    jdk = root / "jdk"
    _ = _write(jdk / "bin/java.exe", b"controlled amd64 java")
    _ = _write(
        jdk / "release",
        b'IMPLEMENTOR="Eclipse Adoptium"\nJAVA_RUNTIME_VERSION="21.0.12+8"\n',
    )
    exiftool = root / "exiftool"
    _ = _write(exiftool / "exiftool.exe", b"controlled amd64 exiftool")
    _ = _write(exiftool / "exiftool_files/lib.pm", b"controlled support")
    return WindowsRuntimeSources(
        python_home=python,
        java_home=jdk,
        worker_jar=_write(root / "worker.jar", b"controlled worker"),
        exiftool_home=exiftool,
    )


def test_assembles_every_runtime_inside_the_application_resources(
    tmp_path: Path,
) -> None:
    """Dropping any Python/app/Java/Worker/ExifTool input must break inventory."""
    project = _project(tmp_path)
    destination = tmp_path / "docmeta-runtime"

    result = assemble_windows_embedded_runtime(
        project,
        destination,
        _sources(tmp_path),
    )

    assert result == destination
    assert (result / "python.exe").read_bytes() == b"controlled amd64 python"
    assert (result / "python312.dll").read_bytes() == b"controlled python dll"
    assert (
        result / "app/src/document_metadata_inspector/cli.py"
    ).read_bytes() == b"def main(): pass\n"
    assert (result / "app/src/xlsx_metadata_forensics/__init__.py").is_file()
    assert (
        result / "app/tools/packaged/windows-x86_64/apache/jdk/bin/java.exe"
    ).read_bytes() == b"controlled amd64 java"
    assert (
        result / "app/tools/packaged/windows-x86_64/apache/worker.jar"
    ).read_bytes() == b"controlled worker"
    assert (
        result / "app/tools/packaged/windows-x86_64/exiftool/exiftool.exe"
    ).read_bytes() == b"controlled amd64 exiftool"
    assert (result / "Lib/site-packages/docmeta-app.pth").read_text(
        encoding="utf-8"
    ) == "../../app/src\n"
    expected_python_hash = sha256(b"controlled amd64 python").hexdigest()
    assert (result / "SHA256SUMS").read_text(
        encoding="utf-8"
    ) == f"{expected_python_hash}  python.exe\n"
    assert verify_runtime_inventory(result) > 10


def test_release_local_tool_manifest_hashes_the_copied_resources(
    tmp_path: Path,
) -> None:
    """Wrong manifest paths or hashes would make all parser engines unavailable."""
    runtime = assemble_windows_embedded_runtime(
        _project(tmp_path),
        tmp_path / "runtime",
        _sources(tmp_path),
    )

    payload = cast(
        "Mapping[str, object]",
        json.loads((runtime / "app/tools/manifest.json").read_text(encoding="utf-8")),
    )
    apache = cast("Mapping[str, object]", payload["apache_worker"])
    apache_packaged = cast("Mapping[str, object]", apache["packaged"])
    windows_apache = cast("Mapping[str, object]", apache_packaged["windows-x86_64"])
    exiftool = cast("Mapping[str, object]", payload["exiftool"])
    exiftool_packaged = cast("Mapping[str, object]", exiftool["packaged"])
    windows_exiftool = cast("Mapping[str, object]", exiftool_packaged["windows-x86_64"])

    assert windows_apache["available"] is True
    assert (
        windows_apache["java"]
        == "tools/packaged/windows-x86_64/apache/jdk/bin/java.exe"
    )
    assert (
        windows_apache["worker_jar"]
        == "tools/packaged/windows-x86_64/apache/worker.jar"
    )
    apache_files = cast("Mapping[str, str]", windows_apache["files"])
    assert (
        apache_files["tools/packaged/windows-x86_64/apache/worker.jar"]
        == sha256(b"controlled worker").hexdigest()
    )
    assert windows_exiftool["available"] is True
    assert windows_exiftool["command"] == [
        "tools/packaged/windows-x86_64/exiftool/exiftool.exe"
    ]
    exiftool_files = cast("Mapping[str, str]", windows_exiftool["files"])
    assert (
        exiftool_files["tools/packaged/windows-x86_64/exiftool/exiftool.exe"]
        == sha256(b"controlled amd64 exiftool").hexdigest()
    )


def test_rejects_a_symlink_without_publishing_a_partial_runtime(tmp_path: Path) -> None:
    """Following a source link could copy files outside the approved inputs."""
    project = _project(tmp_path)
    sources = _sources(tmp_path)
    outside = _write(tmp_path / "outside.txt", b"outside")
    (sources.java_home / "linked-license").symlink_to(outside)
    destination = tmp_path / "runtime"

    with pytest.raises(RuntimeError, match="symbolic link"):
        _ = assemble_windows_embedded_runtime(project, destination, sources)

    assert not destination.exists()


def test_inventory_verification_detects_a_modified_dependency(tmp_path: Path) -> None:
    """Changing any covered runtime byte after assembly must be detected."""
    runtime = assemble_windows_embedded_runtime(
        _project(tmp_path),
        tmp_path / "runtime",
        _sources(tmp_path),
    )
    _ = (runtime / "Lib/site-packages/dependency.pyd").write_bytes(b"tampered")

    with pytest.raises(RuntimeError, match="inventory"):
        _ = verify_runtime_inventory(runtime)


def test_locates_only_the_exact_uv_windows_python_layout(tmp_path: Path) -> None:
    """Selecting a wrong or ambiguous interpreter would silently change the target."""
    expected = tmp_path / "cpython-3.12.13-windows-x86_64-none"
    _ = _write(expected / "python.exe", b"python")
    _ = _write(expected / "python312.dll", b"dll")
    (expected / "Lib").mkdir()

    assert (
        windows_embedded_runtime._find_windows_python_home(tmp_path)  # pyright: ignore[reportPrivateUsage]
        == expected
    )
    second = tmp_path / "unexpected"
    _ = _write(second / "python.exe", b"other")
    _ = _write(second / "python312.dll", b"dll")
    (second / "Lib").mkdir()

    with pytest.raises(RuntimeError, match="exactly one"):
        _ = windows_embedded_runtime._find_windows_python_home(  # pyright: ignore[reportPrivateUsage]
            tmp_path
        )


def test_copies_uv_windows_python_without_its_broken_host_launcher(
    tmp_path: Path,
) -> None:
    """uv's Mac-side launcher symlink is not part of the Windows runtime."""
    source = tmp_path / "python-source"
    _ = _write(source / "python.exe", b"controlled Windows python")
    _ = _write(source / "python312.dll", b"controlled Windows DLL")
    _ = _write(source / "Lib/os.py", b"controlled standard library")
    (source / "python").symlink_to(source / "python3.12")
    destination = tmp_path / "python-copy"

    windows_embedded_runtime._copy_windows_python_tree(  # pyright: ignore[reportPrivateUsage]
        source,
        destination,
    )

    assert (destination / "python.exe").read_bytes() == b"controlled Windows python"
    assert (destination / "Lib/os.py").is_file()
    assert not (destination / "python").exists()
    assert not list(destination.rglob("*.pyc"))


def test_windows_zip_extraction_rejects_traversal_before_writing(
    tmp_path: Path,
) -> None:
    """A pinned archive must still be rejected if its member paths escape staging."""
    archive = tmp_path / "unsafe.zip"
    with ZipFile(archive, "w", ZIP_DEFLATED) as package:
        package.writestr("safe/file.txt", b"safe")
        package.writestr("../outside.txt", b"outside")
    destination = tmp_path / "extracted"

    with pytest.raises(RuntimeError, match="unsafe"):
        windows_embedded_runtime._extract_windows_zip(  # pyright: ignore[reportPrivateUsage]
            archive,
            destination,
        )

    assert not destination.exists()
    assert not (tmp_path / "outside.txt").exists()


def test_locates_the_pinned_windows_jdk_without_executing_it(tmp_path: Path) -> None:
    """Mac assembly must validate Windows JDK provenance without launching java.exe."""
    home = tmp_path / "jdk-21.0.12+8"
    _ = _write(home / "bin/java.exe", b"controlled Windows java")
    _ = _write(home / "bin/jlink.exe", b"controlled Windows jlink")
    _ = _write(
        home / "release",
        b'IMPLEMENTOR="Eclipse Adoptium"\nJAVA_RUNTIME_VERSION="21.0.12+8-LTS"\n',
    )

    assert (
        windows_embedded_runtime._find_windows_jdk_home(  # pyright: ignore[reportPrivateUsage]
            tmp_path,
            "21.0.12+8",
        )
        == home
    )
    _ = (home / "release").write_text(
        'IMPLEMENTOR="Other"\nJAVA_RUNTIME_VERSION="21.0.12+8"\n',
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="Temurin"):
        _ = windows_embedded_runtime._find_windows_jdk_home(  # pyright: ignore[reportPrivateUsage]
            tmp_path,
            "21.0.12+8",
        )


def test_build_orchestrator_publishes_only_acquired_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Skipping any acquisition step would publish an incomplete application."""
    project = _project(tmp_path)
    sources = _sources(tmp_path)

    def acquire_python(_project_root: Path, _cache: Path) -> Path:
        return sources.python_home

    def prepare_python(
        _project_root: Path,
        _source: Path,
        _destination: Path,
        _cache: Path,
    ) -> Path:
        return sources.python_home

    def acquire_jdk(_project_root: Path, _cache: Path) -> Path:
        return sources.java_home

    def build_worker(_project_root: Path, _cache: Path) -> Path:
        return sources.worker_jar

    def acquire_exiftool(_project_root: Path, _cache: Path) -> Path:
        return sources.exiftool_home

    monkeypatch.setattr(
        windows_embedded_runtime,
        "_acquire_windows_python",
        acquire_python,
    )
    monkeypatch.setattr(
        windows_embedded_runtime,
        "_prepare_windows_python",
        prepare_python,
    )
    monkeypatch.setattr(
        windows_embedded_runtime,
        "_acquire_windows_jdk",
        acquire_jdk,
    )
    monkeypatch.setattr(
        windows_embedded_runtime,
        "_build_apache_worker",
        build_worker,
    )
    monkeypatch.setattr(
        windows_embedded_runtime,
        "_acquire_windows_exiftool",
        acquire_exiftool,
    )

    result = windows_embedded_runtime.build_windows_embedded_runtime(
        project,
        tmp_path / "runtime",
        tmp_path / "cache",
    )

    assert (result / "python.exe").read_bytes() == b"controlled amd64 python"
    assert (
        result / "app/tools/packaged/windows-x86_64/apache/worker.jar"
    ).read_bytes() == b"controlled worker"
    assert verify_runtime_inventory(result) > 10


def test_windows_wheel_install_uses_uv_binary_only_without_conflicting_flags(
    tmp_path: Path,
) -> None:
    """uv rejects combining --only-binary with --no-build before resolution."""
    command = windows_embedded_runtime._windows_wheel_install_command(  # pyright: ignore[reportPrivateUsage]
        tmp_path / "requirements.txt",
        tmp_path / "site-packages",
        tmp_path / "cache",
    )

    assert command.count("--only-binary") == 1
    assert ":all:" in command
    assert "--no-build" not in command
    assert command[command.index("--python-platform") + 1] == ("x86_64-pc-windows-msvc")
