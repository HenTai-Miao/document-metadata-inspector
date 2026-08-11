from __future__ import annotations

import json
import os
import stat
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import BinaryIO, cast
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

import pytest
from scripts import assemble_windows_release as assemble_windows_release_cli
from scripts import windows_release as windows_release_module
from scripts.windows_release import assemble_windows_release


def _write_file(path: Path, contents: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_bytes(contents)
    return path


_CLI_ROOT = "document-metadata-inspector-windows-x86_64"


def _is_staged_release_directory(path: Path) -> bool:
    return path.name == "windows-x64" or path.name.startswith(".windows-x64-staged-")


def _write_cli_archive(
    path: Path,
    *,
    core: bytes = b"trusted core",
    checksum: bytes | None = None,
    notices: bytes = b"controlled notices\n",
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    checksum_bytes = checksum or f"{sha256(core).hexdigest()}  docmeta.exe\n".encode()
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr(f"{_CLI_ROOT}/docmeta.exe", core)
        archive.writestr(f"{_CLI_ROOT}/SHA256SUMS", checksum_bytes)
        archive.writestr(
            f"{_CLI_ROOT}/THIRD_PARTY_NOTICES.md",
            notices,
        )
    return path


def _corrupt_zip_member(path: Path, member_name: str) -> None:
    with ZipFile(path, "r") as archive:
        member = archive.getinfo(member_name)
    archive_bytes = bytearray(path.read_bytes())
    name_length = int.from_bytes(
        archive_bytes[member.header_offset + 26 : member.header_offset + 28],
        "little",
    )
    extra_length = int.from_bytes(
        archive_bytes[member.header_offset + 28 : member.header_offset + 30],
        "little",
    )
    data_offset = member.header_offset + 30 + name_length + extra_length
    archive_bytes[data_offset + member.compress_size // 2] ^= 0xFF
    _ = path.write_bytes(archive_bytes)


def _project(tmp_path: Path) -> tuple[Path, Path, Path]:
    project = tmp_path / "project"
    _ = _write_file(
        project / "pyproject.toml",
        b'[project]\nname = "document-metadata-inspector"\nversion = "0.1.0"\n',
    )
    _ = _write_file(project / ".python-version", b"3.12.13\n")
    desktop_package = {
        "version": "0.1.0",
        "devDependencies": {
            "electron": "43.3.0",
            "@electron-forge/cli": "7.11.2",
            "@electron-forge/maker-squirrel": "7.11.2",
            "@electron-forge/maker-zip": "7.11.2",
        },
    }
    _ = _write_file(
        project / "desktop/package.json",
        json.dumps(desktop_package).encode("utf-8"),
    )
    manifest = {
        "exiftool": {"version": "13.55"},
        "windows_exiftool": {"version": "13.55"},
        "apache_worker": {"java_runtime_version": "21.0.12+8"},
        "temurin_jdk": {"version": "21.0.12+8"},
    }
    _ = _write_file(
        project / "tools/manifest.json",
        json.dumps(manifest).encode("utf-8"),
    )
    _ = _write_file(project / "THIRD_PARTY_NOTICES.md", b"controlled notices\n")
    core = _write_file(
        project / "dist/windows-x86_64/onefile/docmeta.exe",
        b"trusted core",
    )
    _ = _write_file(
        core.parent / "SHA256SUMS",
        f"{sha256(core.read_bytes()).hexdigest()}  docmeta.exe\n".encode(),
    )
    forge = project / "desktop/out/make"
    _ = _write_file(
        forge / "squirrel.windows/x64/DocumentMetadataInspector-0.1.0 Setup.exe",
        b"setup",
    )
    _ = _write_file(
        forge / "zip/win32/x64/docmeta-review-win32-x64-0.1.0.zip",
        b"portable",
    )
    cli_release = project / "release"
    _ = _write_cli_archive(
        cli_release / "document-metadata-inspector-windows-x86_64.zip",
    )
    return project, forge, cli_release


def test_assembles_a_normalized_checksummed_windows_release(tmp_path: Path) -> None:
    project, forge, cli_release = _project(tmp_path)
    output = project / "release/windows-x64"

    result = assemble_windows_release(
        project,
        forge,
        cli_release,
        output,
        git_commit="a" * 40,
        built_at_utc=datetime(2026, 8, 11, 1, 2, 3, tzinfo=UTC),
    )

    assert result == output
    expected_names = {
        "DocumentMetadataInspector-0.1.0-win-x64-Setup.exe",
        "DocumentMetadataInspector-0.1.0-win-x64-Portable.zip",
        "DocumentMetadataInspector-0.1.0-win-x64-CLI.zip",
        "SHA256SUMS",
        "BUILD-INFO.json",
        "THIRD_PARTY_NOTICES.md",
    }
    assert {path.name for path in output.iterdir()} == expected_names
    build_info = cast(
        "object",
        json.loads((output / "BUILD-INFO.json").read_text(encoding="utf-8")),
    )
    assert build_info == {
        "schema_version": "1",
        "product_version": "0.1.0",
        "git_commit": "a" * 40,
        "target_platform": "windows-x86_64",
        "core_sha256": sha256(b"trusted core").hexdigest(),
        "built_at_utc": "2026-08-11T01:02:03Z",
        "versions": {
            "python": "3.12.13",
            "java_runtime": "21.0.12+8",
            "exiftool": "13.55",
            "electron": "43.3.0",
            "electron_forge": "7.11.2",
        },
    }
    checksum_lines = (output / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    assert len(checksum_lines) == 5
    assert checksum_lines == sorted(
        checksum_lines, key=lambda line: line.split("  ", 1)[1]
    )
    for line in checksum_lines:
        expected, filename = line.split("  ", 1)
        assert sha256((output / filename).read_bytes()).hexdigest() == expected


def test_rejects_mismatched_python_and_desktop_versions(tmp_path: Path) -> None:
    project, forge, cli_release = _project(tmp_path)
    package_path = project / "desktop/package.json"
    package = cast(
        "dict[str, object]", json.loads(package_path.read_text(encoding="utf-8"))
    )
    package["version"] = "0.2.0"
    _ = package_path.write_text(json.dumps(package), encoding="utf-8")

    with pytest.raises(RuntimeError, match="product versions must match"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            project / "release/windows-x64",
            git_commit="b" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )


def test_rejects_java_build_and_runtime_version_drift(tmp_path: Path) -> None:
    project, forge, cli_release = _project(tmp_path)
    manifest_path = project / "tools/manifest.json"
    manifest = cast(
        "dict[str, object]", json.loads(manifest_path.read_text(encoding="utf-8"))
    )
    temurin_jdk = cast("dict[str, object]", manifest["temurin_jdk"])
    temurin_jdk["version"] = "21.0.11+9"
    _ = manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(RuntimeError, match="Java runtime versions must match"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            project / "release/windows-x64",
            git_commit="b" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )


def test_rejects_windows_exiftool_version_drift(tmp_path: Path) -> None:
    project, forge, cli_release = _project(tmp_path)
    manifest_path = project / "tools/manifest.json"
    manifest = cast(
        "dict[str, object]", json.loads(manifest_path.read_text(encoding="utf-8"))
    )
    windows_exiftool = cast("dict[str, object]", manifest["windows_exiftool"])
    windows_exiftool["version"] = "13.54"
    _ = manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(RuntimeError, match="ExifTool versions must match"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            project / "release/windows-x64",
            git_commit="b" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )


def test_rejects_forge_component_version_drift(tmp_path: Path) -> None:
    project, forge, cli_release = _project(tmp_path)
    package_path = project / "desktop/package.json"
    package = cast(
        "dict[str, object]", json.loads(package_path.read_text(encoding="utf-8"))
    )
    dependencies = cast("dict[str, object]", package["devDependencies"])
    dependencies["@electron-forge/maker-zip"] = "7.10.2"
    _ = package_path.write_text(json.dumps(package), encoding="utf-8")

    with pytest.raises(RuntimeError, match="Electron Forge versions must match"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            project / "release/windows-x64",
            git_commit="b" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )


@pytest.mark.parametrize(
    "unsafe_version",
    [
        "",
        "0.1.0 beta",
        "0.1.0/evil",
        "0.1.0\\evil",
        "https://example.invalid/release",
        "^0.1.0",
        "0.1.0;echo",
        "0.1.0\nnext",
        "a" * 65,
    ],
)
def test_rejects_unsafe_product_version_tokens_and_preserves_existing_output(
    tmp_path: Path,
    unsafe_version: str,
) -> None:
    project, forge, cli_release = _project(tmp_path)
    _ = (project / "pyproject.toml").write_text(
        "\n".join(
            (
                "[project]",
                'name = "document-metadata-inspector"',
                f"version = {json.dumps(unsafe_version)}",
                "",
            )
        ),
        encoding="utf-8",
    )
    package_path = project / "desktop/package.json"
    package = cast(
        "dict[str, object]", json.loads(package_path.read_text(encoding="utf-8"))
    )
    package["version"] = unsafe_version
    _ = package_path.write_text(json.dumps(package), encoding="utf-8")
    output = project / "release/windows-x64"
    output.mkdir()
    _ = (output / "previous.txt").write_text("previous", encoding="utf-8")

    with pytest.raises(RuntimeError, match="safe fixed tokens"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            output,
            git_commit="7" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )

    assert {path.name for path in output.iterdir()} == {"previous.txt"}


@pytest.mark.parametrize(
    ("component", "unsafe_version"),
    [
        ("python", ">=3.12"),
        ("electron", "43.3.0 || calc"),
        ("java", "21.0.12+8/../../x"),
        ("exiftool", "13.55:evil"),
        ("forge", "^7.11.2"),
        ("electron", "a" * 65),
    ],
)
def test_rejects_unsafe_component_version_tokens_and_preserves_existing_output(
    tmp_path: Path,
    component: str,
    unsafe_version: str,
) -> None:
    project, forge, cli_release = _project(tmp_path)
    package_path = project / "desktop/package.json"
    package = cast(
        "dict[str, object]", json.loads(package_path.read_text(encoding="utf-8"))
    )
    dependencies = cast("dict[str, object]", package["devDependencies"])
    manifest_path = project / "tools/manifest.json"
    manifest = cast(
        "dict[str, object]", json.loads(manifest_path.read_text(encoding="utf-8"))
    )
    if component == "python":
        _ = (project / ".python-version").write_text(
            f"{unsafe_version}\n", encoding="utf-8"
        )
    elif component == "electron":
        dependencies["electron"] = unsafe_version
    elif component == "java":
        cast("dict[str, object]", manifest["apache_worker"])["java_runtime_version"] = (
            unsafe_version
        )
        cast("dict[str, object]", manifest["temurin_jdk"])["version"] = unsafe_version
    elif component == "exiftool":
        cast("dict[str, object]", manifest["exiftool"])["version"] = unsafe_version
        cast("dict[str, object]", manifest["windows_exiftool"])["version"] = (
            unsafe_version
        )
    else:
        dependencies["@electron-forge/cli"] = unsafe_version
        dependencies["@electron-forge/maker-squirrel"] = unsafe_version
        dependencies["@electron-forge/maker-zip"] = unsafe_version
    _ = package_path.write_text(json.dumps(package), encoding="utf-8")
    _ = manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    output = project / "release/windows-x64"
    output.mkdir()
    _ = (output / "previous.txt").write_text("previous", encoding="utf-8")

    with pytest.raises(RuntimeError, match="safe fixed tokens"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            output,
            git_commit="8" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )

    assert {path.name for path in output.iterdir()} == {"previous.txt"}


def test_accepts_bounded_version_tokens_with_common_safe_separators(
    tmp_path: Path,
) -> None:
    project, forge, cli_release = _project(tmp_path)
    product_version = "0.1.0-rc1"
    _ = (project / "pyproject.toml").write_text(
        "\n".join(
            (
                "[project]",
                'name = "document-metadata-inspector"',
                f'version = "{product_version}"',
                "",
            )
        ),
        encoding="utf-8",
    )
    package_path = project / "desktop/package.json"
    package = cast(
        "dict[str, object]", json.loads(package_path.read_text(encoding="utf-8"))
    )
    package["version"] = product_version
    dependencies = cast("dict[str, object]", package["devDependencies"])
    dependencies["electron"] = "43.3.0-vendor_1"
    for name in (
        "@electron-forge/cli",
        "@electron-forge/maker-squirrel",
        "@electron-forge/maker-zip",
    ):
        dependencies[name] = "7.11.2-vendor_1"
    _ = package_path.write_text(json.dumps(package), encoding="utf-8")
    _ = (project / ".python-version").write_text("3.12.13_vendor-1\n", encoding="utf-8")
    manifest_path = project / "tools/manifest.json"
    manifest = cast(
        "dict[str, object]", json.loads(manifest_path.read_text(encoding="utf-8"))
    )
    for name in ("exiftool", "windows_exiftool"):
        cast("dict[str, object]", manifest[name])["version"] = "13.55_vendor-1"
    cast("dict[str, object]", manifest["apache_worker"])["java_runtime_version"] = (
        "21.0.12+8_vendor-1"
    )
    cast("dict[str, object]", manifest["temurin_jdk"])["version"] = "21.0.12+8_vendor-1"
    _ = manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    setup = forge / "squirrel.windows/x64/DocumentMetadataInspector-0.1.0 Setup.exe"
    _ = setup.replace(
        setup.with_name(f"DocumentMetadataInspector-{product_version} Setup.exe")
    )
    portable = forge / "zip/win32/x64/docmeta-review-win32-x64-0.1.0.zip"
    _ = portable.replace(
        portable.with_name(f"docmeta-review-win32-x64-{product_version}.zip")
    )

    output = assemble_windows_release(
        project,
        forge,
        cli_release,
        project / "release/windows-x64",
        git_commit="9" * 40,
        built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
    )

    build_info = cast(
        "dict[str, object]",
        json.loads((output / "BUILD-INFO.json").read_text(encoding="utf-8")),
    )
    assert build_info["product_version"] == product_version
    assert build_info["versions"] == {
        "python": "3.12.13_vendor-1",
        "java_runtime": "21.0.12+8_vendor-1",
        "exiftool": "13.55_vendor-1",
        "electron": "43.3.0-vendor_1",
        "electron_forge": "7.11.2-vendor_1",
    }


def test_rejects_untraceable_commit_or_naive_build_time(tmp_path: Path) -> None:
    project, forge, cli_release = _project(tmp_path)
    output = project / "release/windows-x64"

    with pytest.raises(RuntimeError, match="Git commit must be a full lowercase SHA"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            output,
            git_commit="short",
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )
    with pytest.raises(RuntimeError, match="build time must be UTC-aware"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            output,
            git_commit="b" * 40,
            built_at_utc=datetime(2026, 8, 11),  # noqa: DTZ001 - invalid input probe
        )


def test_rejects_duplicate_setup_outputs(tmp_path: Path) -> None:
    project, forge, cli_release = _project(tmp_path)
    _ = _write_file(forge / "squirrel.windows/x64/duplicate Setup.exe", b"duplicate")

    with pytest.raises(RuntimeError, match="exactly one regular file"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            project / "release/windows-x64",
            git_commit="c" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )


def test_rejects_a_stale_portable_version(tmp_path: Path) -> None:
    project, forge, cli_release = _project(tmp_path)
    portable = forge / "zip/win32/x64/docmeta-review-win32-x64-0.1.0.zip"
    stale = portable.with_name("docmeta-review-win32-x64-0.0.9.zip")
    _ = portable.replace(stale)

    with pytest.raises(RuntimeError, match="Maker output version does not match"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            project / "release/windows-x64",
            git_commit="c" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )


def test_rejects_a_symlinked_cli_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, forge, cli_release = _project(tmp_path)
    cli = cli_release / "document-metadata-inspector-windows-x86_64.zip"
    original_is_symlink = Path.is_symlink

    def controlled_is_symlink(path: Path) -> bool:
        return path == cli or original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", controlled_is_symlink)

    with pytest.raises(RuntimeError, match="regular file"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            project / "release/windows-x64",
            git_commit="d" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )


def test_publication_failure_restores_the_previous_complete_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, forge, cli_release = _project(tmp_path)
    output = project / "release/windows-x64"
    output.mkdir(parents=True)
    _ = (output / "previous.txt").write_text("previous", encoding="utf-8")
    original_replace = Path.replace

    def fail_staged_publication(source: Path, target: Path) -> Path:
        if (
            _is_staged_release_directory(source)
            and target == output
            and source != output
        ):
            message = "controlled publication failure"
            raise OSError(message)
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", fail_staged_publication)

    with pytest.raises(OSError, match="controlled publication failure"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            output,
            git_commit="e" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )

    assert {path.name for path in output.iterdir()} == {"previous.txt"}
    assert (output / "previous.txt").read_text(encoding="utf-8") == "previous"


def test_post_rename_failure_quarantines_new_release_and_restores_previous(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, forge, cli_release = _project(tmp_path)
    output = project / "release/windows-x64"
    output.mkdir(parents=True)
    _ = (output / "previous.txt").write_text("previous", encoding="utf-8")
    original_replace = Path.replace

    def fail_after_staged_rename(source: Path, target: Path) -> Path:
        if (
            _is_staged_release_directory(source)
            and target == output
            and source != output
        ):
            _ = original_replace(source, target)
            message = "controlled post-rename publication failure"
            raise OSError(message)
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", fail_after_staged_rename)

    with pytest.raises(OSError, match="controlled post-rename publication failure"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            output,
            git_commit="f" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )

    assert {path.name for path in output.iterdir()} == {"previous.txt"}
    assert (output / "previous.txt").read_text(encoding="utf-8") == "previous"
    assert list(output.parent.glob(".windows-x64-recovery-*")) == []
    assert list(output.parent.glob(".windows-x64-failed-*")) == []


def test_old_output_rename_uses_a_same_parent_recovery_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, forge, cli_release = _project(tmp_path)
    output = project / "release/windows-x64"
    output.mkdir(parents=True)
    _ = (output / "previous.txt").write_text("previous", encoding="utf-8")
    original_replace = Path.replace
    attempted_backups: list[Path] = []

    def fail_old_output_rename(source: Path, target: Path) -> Path:
        if source == output:
            attempted_backups.append(target)
            message = "controlled old-output rename failure"
            raise OSError(message)
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", fail_old_output_rename)

    with pytest.raises(OSError, match="controlled old-output rename failure"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            output,
            git_commit="1" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )

    assert len(attempted_backups) == 1
    assert attempted_backups[0].parent == output.parent
    assert (output / "previous.txt").read_text(encoding="utf-8") == "previous"


def test_quarantine_failure_still_attempts_previous_release_restoration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, forge, cli_release = _project(tmp_path)
    output = project / "release/windows-x64"
    output.mkdir(parents=True)
    _ = (output / "previous.txt").write_text("previous", encoding="utf-8")
    original_replace = Path.replace
    restoration_attempted = False

    def fail_quarantine(source: Path, target: Path) -> Path:
        nonlocal restoration_attempted
        if (
            _is_staged_release_directory(source)
            and target == output
            and source != output
        ):
            _ = original_replace(source, target)
            message = "controlled staged publication failure"
            raise OSError(message)
        if source == output and target.name.startswith(".windows-x64-failed-"):
            message = "controlled quarantine failure"
            raise OSError(message)
        if source.name.startswith(".windows-x64-recovery-") and target == output:
            restoration_attempted = True
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", fail_quarantine)

    with pytest.raises(
        RuntimeError,
        match=r"publication.*quarantine.*recovery.*\.windows-x64-recovery-",
    ):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            output,
            git_commit="2" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )

    assert restoration_attempted
    backups = list(output.parent.glob(".windows-x64-recovery-*"))
    assert len(backups) == 1
    assert (backups[0] / "previous.txt").read_text(encoding="utf-8") == "previous"


def test_restoration_failure_retains_the_previous_release_at_recovery_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, forge, cli_release = _project(tmp_path)
    output = project / "release/windows-x64"
    output.mkdir(parents=True)
    _ = (output / "previous.txt").write_text("previous", encoding="utf-8")
    original_replace = Path.replace

    def fail_restoration(source: Path, target: Path) -> Path:
        if (
            _is_staged_release_directory(source)
            and target == output
            and source != output
        ):
            message = "controlled staged publication failure"
            raise OSError(message)
        if source.name.startswith(".windows-x64-recovery-") and target == output:
            message = "controlled restoration failure"
            raise OSError(message)
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", fail_restoration)

    with pytest.raises(
        RuntimeError,
        match=r"publication.*restoration.*\.windows-x64-recovery-",
    ):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            output,
            git_commit="3" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )

    backups = list(output.parent.glob(".windows-x64-recovery-*"))
    assert len(backups) == 1
    assert (backups[0] / "previous.txt").read_text(encoding="utf-8") == "previous"


def test_failed_republication_restores_the_previous_release_without_unsealing_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, forge, cli_release = _project(tmp_path)
    output = project / "release/windows-x64"
    _ = assemble_windows_release(
        project,
        forge,
        cli_release,
        output,
        git_commit="3" * 40,
        built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
    )
    original_replace = Path.replace

    def fail_staged_publication(source: Path, target: Path) -> Path:
        if (
            _is_staged_release_directory(source)
            and target == output
            and source != output
        ):
            message = "controlled staged publication failure"
            raise OSError(message)
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", fail_staged_publication)

    with pytest.raises(OSError, match="controlled staged publication failure"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            output,
            git_commit="4" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )

    build_info = cast(
        "dict[str, object]",
        json.loads((output / "BUILD-INFO.json").read_text(encoding="utf-8")),
    )
    assert build_info["git_commit"] == "3" * 40
    write_bits = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
    for path in output.iterdir():
        file_stat = path.lstat()
        if os.name == "nt":
            attributes = cast("int", getattr(file_stat, "st_file_attributes", 0))
            readonly = cast("int", getattr(stat, "FILE_ATTRIBUTE_READONLY", 0x1))
            assert attributes & readonly
        else:
            assert file_stat.st_mode & write_bits == 0
    if os.name != "nt":
        assert output.lstat().st_mode & write_bits == 0
    assert list(output.parent.glob(".windows-x64-recovery-*")) == []


def test_partial_previous_release_cleanup_reports_accurate_post_publish_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, forge, cli_release = _project(tmp_path)
    output = project / "release/windows-x64"
    output.mkdir(parents=True)
    _ = (output / "previous.txt").write_text("previous", encoding="utf-8")

    def fail_backup_cleanup(path: Path) -> None:
        assert path.parent == output.parent
        assert path.name.startswith(".windows-x64-recovery-")
        assert (path / "previous.txt").read_text(encoding="utf-8") == "previous"
        (path / "previous.txt").unlink()
        message = "controlled partial backup cleanup failure"
        raise OSError(message)

    monkeypatch.setattr(
        windows_release_module,
        "_cleanup_recovery_directory",
        fail_backup_cleanup,
    )

    with pytest.raises(RuntimeError) as caught:
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            output,
            git_commit="4" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )

    message = str(caught.value)
    assert "publication succeeded" in message
    assert "cleanup is incomplete" in message
    assert "possibly partial" in message
    assert ".windows-x64-recovery-" in message
    assert "recoverable" not in message
    build_info = cast(
        "dict[str, object]",
        json.loads((output / "BUILD-INFO.json").read_text(encoding="utf-8")),
    )
    assert build_info["core_sha256"] == sha256(b"trusted core").hexdigest()
    backups = list(output.parent.glob(".windows-x64-recovery-*"))
    assert len(backups) == 1
    assert list(backups[0].iterdir()) == []


def test_second_publication_cleans_the_sealed_previous_release(tmp_path: Path) -> None:
    project, forge, cli_release = _project(tmp_path)
    output = project / "release/windows-x64"
    _ = assemble_windows_release(
        project,
        forge,
        cli_release,
        output,
        git_commit="5" * 40,
        built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
    )

    result = assemble_windows_release(
        project,
        forge,
        cli_release,
        output,
        git_commit="6" * 40,
        built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
    )

    assert result == output
    build_info = cast(
        "dict[str, object]",
        json.loads((output / "BUILD-INFO.json").read_text(encoding="utf-8")),
    )
    assert build_info["git_commit"] == "6" * 40
    assert list(output.parent.glob(".windows-x64-recovery-*")) == []


def test_recovery_cleanup_rejects_symlinked_entries_without_following_them(
    tmp_path: Path,
) -> None:
    project, forge, cli_release = _project(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    _ = (outside / "sentinel.txt").write_text("outside", encoding="utf-8")
    output = project / "release/windows-x64"
    output.mkdir()
    _ = (output / "previous.txt").write_text("previous", encoding="utf-8")
    (output / "unsafe-link").symlink_to(outside, target_is_directory=True)

    with pytest.raises(RuntimeError, match="cleanup is incomplete"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            output,
            git_commit="7" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )

    build_info = cast(
        "dict[str, object]",
        json.loads((output / "BUILD-INFO.json").read_text(encoding="utf-8")),
    )
    assert build_info["git_commit"] == "7" * 40
    backups = list(output.parent.glob(".windows-x64-recovery-*"))
    assert len(backups) == 1
    assert (backups[0] / "unsafe-link").is_symlink()
    assert (backups[0] / "previous.txt").read_text(encoding="utf-8") == "previous"
    assert (outside / "sentinel.txt").read_text(encoding="utf-8") == "outside"


def test_rejects_core_bytes_that_do_not_match_the_manifest(tmp_path: Path) -> None:
    project, forge, cli_release = _project(tmp_path)
    core = project / "dist/windows-x86_64/onefile/docmeta.exe"
    _ = core.write_bytes(b"modified after checksum")

    with pytest.raises(RuntimeError, match="the frozen core checksum is invalid"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            project / "release/windows-x64",
            git_commit="f" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )


@pytest.mark.parametrize(
    "checksum",
    [
        b"\xff\xfe",
        b"malformed checksum\n",
        f"{sha256(b'trusted core').hexdigest()}  docmeta.exe\nextra record\n".encode(),
    ],
)
def test_rejects_invalid_external_core_checksum_without_replacing_output(
    tmp_path: Path,
    checksum: bytes,
) -> None:
    project, forge, cli_release = _project(tmp_path)
    checksum_path = project / "dist/windows-x86_64/onefile/SHA256SUMS"
    _ = checksum_path.write_bytes(checksum)
    output = project / "release/windows-x64"
    output.mkdir()
    _ = (output / "previous.txt").write_text("previous", encoding="utf-8")

    with pytest.raises(RuntimeError, match="the frozen core checksum is invalid"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            output,
            git_commit="e" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )

    assert {path.name for path in output.iterdir()} == {"previous.txt"}
    assert (output / "previous.txt").read_text(encoding="utf-8") == "previous"


def test_reuses_the_single_validated_core_digest_for_build_info(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, forge, cli_release = _project(tmp_path)
    output = project / "release/windows-x64"
    trusted_digest = sha256(b"trusted core").hexdigest()
    changed_digest = sha256(b"changed after validation").hexdigest()
    original_hash_and_size = windows_release_module._hash_and_size  # pyright: ignore[reportPrivateUsage]
    core_hash_calls = 0

    def changing_core_hash(path: Path) -> tuple[str, int]:
        nonlocal core_hash_calls
        if path.name == "docmeta.exe" and path.parent.name == "source-evidence":
            core_hash_calls += 1
            digest = trusted_digest if core_hash_calls == 1 else changed_digest
            return digest, len(b"trusted core")
        return original_hash_and_size(path)

    monkeypatch.setattr(windows_release_module, "_hash_and_size", changing_core_hash)

    _ = assemble_windows_release(
        project,
        forge,
        cli_release,
        output,
        git_commit="d" * 40,
        built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
    )

    build_info = cast(
        "dict[str, object]",
        json.loads((output / "BUILD-INFO.json").read_text(encoding="utf-8")),
    )
    assert core_hash_calls == 1
    assert build_info["core_sha256"] == trusted_digest


@pytest.mark.parametrize("source_name", ["cli", "notices"])
def test_source_replacement_during_snapshot_copy_fails_without_replacing_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_name: str,
) -> None:
    project, forge, cli_release = _project(tmp_path)
    sources = {
        "cli": cli_release / "document-metadata-inspector-windows-x86_64.zip",
        "notices": project / "THIRD_PARTY_NOTICES.md",
    }
    replaced_source = sources[source_name]
    output = project / "release/windows-x64"
    output.mkdir()
    _ = (output / "previous.txt").write_text("previous", encoding="utf-8")
    original_discover = windows_release_module._discover_sources  # pyright: ignore[reportPrivateUsage]

    def replace_after_discovery(
        discovered_project: Path,
        discovered_forge: Path,
        discovered_cli_release: Path,
        product_version: str,
    ) -> windows_release_module._Sources:  # pyright: ignore[reportPrivateUsage]
        discovered = original_discover(
            discovered_project,
            discovered_forge,
            discovered_cli_release,
            product_version,
        )
        _ = replaced_source.write_bytes(b"concurrently replaced source")
        return discovered

    monkeypatch.setattr(
        windows_release_module,
        "_discover_sources",
        replace_after_discovery,
    )

    with pytest.raises(RuntimeError):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            output,
            git_commit="4" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )

    assert {path.name for path in output.iterdir()} == {"previous.txt"}
    assert (output / "previous.txt").read_text(encoding="utf-8") == "previous"


def test_frozen_core_replacement_during_snapshot_copy_preserves_old_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, forge, cli_release = _project(tmp_path)
    core = project / "dist/windows-x86_64/onefile/docmeta.exe"
    output = project / "release/windows-x64"
    output.mkdir()
    _ = (output / "previous.txt").write_text("previous", encoding="utf-8")
    original_discover = windows_release_module._discover_sources  # pyright: ignore[reportPrivateUsage]

    def replace_after_discovery(
        discovered_project: Path,
        discovered_forge: Path,
        discovered_cli_release: Path,
        product_version: str,
    ) -> windows_release_module._Sources:  # pyright: ignore[reportPrivateUsage]
        discovered = original_discover(
            discovered_project,
            discovered_forge,
            discovered_cli_release,
            product_version,
        )
        _ = core.write_bytes(b"concurrently replaced core")
        return discovered

    monkeypatch.setattr(
        windows_release_module,
        "_discover_sources",
        replace_after_discovery,
    )

    with pytest.raises(
        RuntimeError, match="the frozen core must remain a safe regular file"
    ):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            output,
            git_commit="5" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )

    assert {path.name for path in output.iterdir()} == {"previous.txt"}


@pytest.mark.parametrize("source_name", ["setup", "portable"])
def test_rejects_opaque_source_replaced_by_symlink_after_discovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_name: str,
) -> None:
    project, forge, cli_release = _project(tmp_path)
    arbitrary = _write_file(tmp_path / "arbitrary.exe", b"arbitrary executable")
    output = project / "release/windows-x64"
    output.mkdir()
    _ = (output / "previous.txt").write_text("previous", encoding="utf-8")
    original_discover = windows_release_module._discover_sources  # pyright: ignore[reportPrivateUsage]

    def replace_after_discovery(
        discovered_project: Path,
        discovered_forge: Path,
        discovered_cli_release: Path,
        product_version: str,
    ) -> windows_release_module._Sources:  # pyright: ignore[reportPrivateUsage]
        sources = original_discover(
            discovered_project,
            discovered_forge,
            discovered_cli_release,
            product_version,
        )
        source = cast("Path", getattr(sources, source_name))
        source.unlink()
        source.symlink_to(arbitrary)
        return sources

    monkeypatch.setattr(
        windows_release_module,
        "_discover_sources",
        replace_after_discovery,
    )

    with pytest.raises(RuntimeError, match="safe regular file"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            output,
            git_commit="3" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )

    assert {path.name for path in output.iterdir()} == {"previous.txt"}
    assert (output / "previous.txt").read_text(encoding="utf-8") == "previous"


@pytest.mark.parametrize("source_name", ["setup", "portable"])
def test_rejects_opaque_source_replaced_by_regular_file_after_discovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_name: str,
) -> None:
    project, forge, cli_release = _project(tmp_path)
    output = project / "release/windows-x64"
    output.mkdir()
    _ = (output / "previous.txt").write_text("previous", encoding="utf-8")
    original_discover = windows_release_module._discover_sources  # pyright: ignore[reportPrivateUsage]

    def replace_after_discovery(
        discovered_project: Path,
        discovered_forge: Path,
        discovered_cli_release: Path,
        product_version: str,
    ) -> windows_release_module._Sources:  # pyright: ignore[reportPrivateUsage]
        sources = original_discover(
            discovered_project,
            discovered_forge,
            discovered_cli_release,
            product_version,
        )
        source = cast("Path", getattr(sources, source_name))
        source.unlink()
        _ = source.write_bytes(b"replacement regular executable")
        return sources

    monkeypatch.setattr(
        windows_release_module,
        "_discover_sources",
        replace_after_discovery,
    )

    with pytest.raises(RuntimeError, match="safe regular file"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            output,
            git_commit="8" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )

    assert {path.name for path in output.iterdir()} == {"previous.txt"}


def test_rejects_setup_replaced_by_symlink_between_lstat_and_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, forge, cli_release = _project(tmp_path)
    setup = forge / "squirrel.windows/x64/DocumentMetadataInspector-0.1.0 Setup.exe"
    arbitrary = _write_file(tmp_path / "arbitrary.exe", b"arbitrary executable")
    output = project / "release/windows-x64"
    output.mkdir()
    _ = (output / "previous.txt").write_text("previous", encoding="utf-8")
    original_open = windows_release_module.os.open  # pyright: ignore[reportPrivateLocalImportUsage]
    replaced = False

    def replace_between_lstat_and_open(
        path: str | bytes | Path,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal replaced
        if Path(os.fsdecode(path)) == setup and not replaced:
            setup.unlink()
            setup.symlink_to(arbitrary)
            replaced = True
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(
        windows_release_module.os,  # pyright: ignore[reportPrivateLocalImportUsage]
        "open",
        replace_between_lstat_and_open,
    )

    with pytest.raises(RuntimeError, match="safe regular file"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            output,
            git_commit="b" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )

    assert replaced
    assert {path.name for path in output.iterdir()} == {"previous.txt"}


def test_source_replacement_after_snapshot_hash_cannot_change_published_notices(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, forge, cli_release = _project(tmp_path)
    notices = project / "THIRD_PARTY_NOTICES.md"
    original_notices = notices.read_bytes()
    replacement = b"concurrently replaced notices\n"
    original_hash_and_size = windows_release_module._hash_and_size  # pyright: ignore[reportPrivateUsage]

    def replace_source_after_hash(path: Path) -> tuple[str, int]:
        evidence = original_hash_and_size(path)
        if path.name == "THIRD_PARTY_NOTICES.md":
            _ = notices.write_bytes(replacement)
        return evidence

    monkeypatch.setattr(
        windows_release_module,
        "_hash_and_size",
        replace_source_after_hash,
    )

    output = assemble_windows_release(
        project,
        forge,
        cli_release,
        project / "release/windows-x64",
        git_commit="6" * 40,
        built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
    )

    assert notices.read_bytes() == replacement
    assert (output / "THIRD_PARTY_NOTICES.md").read_bytes() == original_notices


def test_cli_source_replacement_after_snapshot_validation_cannot_change_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, forge, cli_release = _project(tmp_path)
    cli = cli_release / "document-metadata-inspector-windows-x86_64.zip"
    original_cli = cli.read_bytes()
    replacement = b"concurrently replaced CLI archive"
    original_validate = windows_release_module._validate_cli_archive  # pyright: ignore[reportPrivateUsage]

    def replace_source_after_validation(
        snapshot_cli: BinaryIO,
        *,
        external_core_sha256: str,
        external_core_size: int,
        external_notices_sha256: str,
        external_notices_size: int,
    ) -> None:
        original_validate(
            snapshot_cli,
            external_core_sha256=external_core_sha256,
            external_core_size=external_core_size,
            external_notices_sha256=external_notices_sha256,
            external_notices_size=external_notices_size,
        )
        _ = cli.write_bytes(replacement)

    monkeypatch.setattr(
        windows_release_module,
        "_validate_cli_archive",
        replace_source_after_validation,
    )

    output = assemble_windows_release(
        project,
        forge,
        cli_release,
        project / "release/windows-x64",
        git_commit="1" * 40,
        built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
    )

    assert cli.read_bytes() == replacement
    assert (
        output / "DocumentMetadataInspector-0.1.0-win-x64-CLI.zip"
    ).read_bytes() == original_cli


def test_rejects_cli_archive_path_swapped_between_hash_and_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, forge, cli_release = _project(tmp_path)
    cli = cli_release / "document-metadata-inspector-windows-x86_64.zip"
    valid_archive = cli.read_bytes()
    invalid_archive = b"invalid CLI archive A"
    _ = cli.write_bytes(invalid_archive)
    output = project / "release/windows-x64"
    output.mkdir()
    _ = (output / "previous.txt").write_text("previous", encoding="utf-8")
    original_validate = windows_release_module._validate_cli_archive  # pyright: ignore[reportPrivateUsage]
    swapped = False
    validation_failed = False
    restored = False

    def swap_path_while_stable_handle_remains_open(
        snapshot_cli: BinaryIO,
        *,
        external_core_sha256: str,
        external_core_size: int,
        external_notices_sha256: str,
        external_notices_size: int,
    ) -> None:
        nonlocal restored, swapped, validation_failed
        staged_cli = Path(snapshot_cli.name)
        valid_path = staged_cli.with_name("valid-archive-B.zip")
        _ = valid_path.write_bytes(valid_archive)
        _ = valid_path.replace(staged_cli)
        swapped = True
        try:
            original_validate(
                snapshot_cli,
                external_core_sha256=external_core_sha256,
                external_core_size=external_core_size,
                external_notices_sha256=external_notices_sha256,
                external_notices_size=external_notices_size,
            )
        except RuntimeError:
            validation_failed = True
            raise
        finally:
            invalid_path = staged_cli.with_name("invalid-archive-A.zip")
            _ = invalid_path.write_bytes(invalid_archive)
            _ = invalid_path.replace(staged_cli)
            restored = True

    monkeypatch.setattr(
        windows_release_module,
        "_validate_cli_archive",
        swap_path_while_stable_handle_remains_open,
    )

    with pytest.raises(RuntimeError):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            output,
            git_commit="a" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )

    assert {path.name for path in output.iterdir()} == {"previous.txt"}
    assert (output / "previous.txt").read_text(encoding="utf-8") == "previous"
    assert swapped
    assert validation_failed
    assert restored


@pytest.mark.parametrize(
    "cached_artifact",
    [
        "DocumentMetadataInspector-0.1.0-win-x64-CLI.zip",
        "THIRD_PARTY_NOTICES.md",
    ],
)
def test_final_rehash_rejects_changes_to_cached_staged_digests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cached_artifact: str,
) -> None:
    project, forge, cli_release = _project(tmp_path)
    output = project / "release/windows-x64"
    output.mkdir()
    _ = (output / "previous.txt").write_text("previous", encoding="utf-8")
    original_hash = windows_release_module._hash  # pyright: ignore[reportPrivateUsage]
    changed = False

    def change_cached_artifact_before_final_rehash(path: Path) -> str:
        nonlocal changed
        if not changed and path.name.endswith("-Portable.zip"):
            _ = (path.parent / cached_artifact).write_bytes(b"changed after validation")
            changed = True
        return original_hash(path)

    monkeypatch.setattr(
        windows_release_module,
        "_hash",
        change_cached_artifact_before_final_rehash,
    )

    with pytest.raises(
        RuntimeError, match="the staged Windows release checksum is invalid"
    ):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            output,
            git_commit="2" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )

    assert changed
    assert {path.name for path in output.iterdir()} == {"previous.txt"}


def test_published_release_is_sealed_read_only_with_exact_inventory(
    tmp_path: Path,
) -> None:
    project, forge, cli_release = _project(tmp_path)

    output = assemble_windows_release(
        project,
        forge,
        cli_release,
        project / "release/windows-x64",
        git_commit="c" * 40,
        built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
    )

    expected_names = {
        "DocumentMetadataInspector-0.1.0-win-x64-Setup.exe",
        "DocumentMetadataInspector-0.1.0-win-x64-Portable.zip",
        "DocumentMetadataInspector-0.1.0-win-x64-CLI.zip",
        "THIRD_PARTY_NOTICES.md",
        "BUILD-INFO.json",
        "SHA256SUMS",
    }
    assert {path.name for path in output.iterdir()} == expected_names
    write_bits = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
    for path in output.iterdir():
        file_stat = path.lstat()
        assert stat.S_ISREG(file_stat.st_mode)
        assert not path.is_symlink()
        if os.name == "nt":
            attributes = cast("int", getattr(file_stat, "st_file_attributes", 0))
            readonly = cast("int", getattr(stat, "FILE_ATTRIBUTE_READONLY", 0x1))
            assert attributes & readonly
        else:
            assert file_stat.st_mode & write_bits == 0
    if os.name != "nt":
        assert output.lstat().st_mode & write_bits == 0


def test_seal_blocks_setup_change_during_later_portable_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, forge, cli_release = _project(tmp_path)
    output = project / "release/windows-x64"
    output.mkdir()
    _ = (output / "previous.txt").write_text("previous", encoding="utf-8")
    original_open = windows_release_module.os.open  # pyright: ignore[reportPrivateLocalImportUsage]
    setup_verified = False
    mutation_attempted = False

    def mutate_setup_when_portable_is_verified(
        path: str | bytes | Path,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal mutation_attempted, setup_verified
        candidate = Path(os.fsdecode(path))
        read_open = not flags & (os.O_WRONLY | os.O_RDWR | os.O_EXCL)
        if (
            candidate.parent.name == "windows-x64"
            or candidate.parent.name.startswith(".windows-x64-staged-")
        ) and read_open:
            if candidate.name.endswith("-Setup.exe"):
                setup_verified = True
            elif candidate.name.endswith("-Portable.zip"):
                assert setup_verified
                mutation_attempted = True
                setup = candidate.with_name(
                    "DocumentMetadataInspector-0.1.0-win-x64-Setup.exe"
                )
                _ = setup.write_bytes(b"changed after setup verification")
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(
        windows_release_module.os,  # pyright: ignore[reportPrivateLocalImportUsage]
        "open",
        mutate_setup_when_portable_is_verified,
    )

    with pytest.raises((OSError, RuntimeError)):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            output,
            git_commit="d" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )

    assert mutation_attempted
    assert {path.name for path in output.iterdir()} == {"previous.txt"}


def test_sealed_release_reverification_rejects_a_reordered_checksum_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, forge, cli_release = _project(tmp_path)
    output = project / "release/windows-x64"
    output.mkdir()
    _ = (output / "previous.txt").write_text("previous", encoding="utf-8")
    original_seal = windows_release_module._seal_staged_release  # pyright: ignore[reportPrivateUsage]
    manifest_reordered = False

    def reorder_manifest_before_seal(staged: Path, expected_names: set[str]) -> None:
        nonlocal manifest_reordered
        manifest = staged / "SHA256SUMS"
        lines = manifest.read_text(encoding="utf-8").splitlines()
        _ = manifest.write_text(
            f"{'\n'.join(reversed(lines))}\n",
            encoding="utf-8",
        )
        manifest_reordered = True
        original_seal(staged, expected_names)

    monkeypatch.setattr(
        windows_release_module,
        "_seal_staged_release",
        reorder_manifest_before_seal,
    )

    with pytest.raises(
        RuntimeError,
        match="the staged Windows release checksum is invalid",
    ):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            output,
            git_commit="f" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )

    assert manifest_reordered
    assert {path.name for path in output.iterdir()} == {"previous.txt"}


def test_post_seal_verification_failure_preserves_error_and_cleans_temp_trees(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, forge, cli_release = _project(tmp_path)
    output = project / "release/windows-x64"
    output.mkdir()
    _ = (output / "previous.txt").write_text("previous", encoding="utf-8")
    original_stable_hash = windows_release_module._stable_hash  # pyright: ignore[reportPrivateUsage]

    def fail_after_seal(path: Path, description: str) -> str:
        if path.name.endswith("-Portable.zip"):
            message = "controlled post-seal verification failure"
            raise RuntimeError(message)
        return original_stable_hash(path, description)

    monkeypatch.setattr(
        windows_release_module,
        "_stable_hash",
        fail_after_seal,
    )

    with pytest.raises(
        RuntimeError, match=r"^controlled post-seal verification failure$"
    ):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            output,
            git_commit="e" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )

    assert {path.name for path in output.iterdir()} == {"previous.txt"}
    assert list(output.parent.glob(".windows-x64-staged-*")) == []
    assert list(output.parent.glob(".windows-release-evidence-*")) == []


def test_rejects_a_malformed_cli_zip_and_preserves_existing_output(
    tmp_path: Path,
) -> None:
    project, forge, cli_release = _project(tmp_path)
    cli = cli_release / "document-metadata-inspector-windows-x86_64.zip"
    _ = cli.write_bytes(b"not a zip")
    output = project / "release/windows-x64"
    output.mkdir()
    _ = (output / "previous.txt").write_text("previous", encoding="utf-8")

    with pytest.raises(RuntimeError, match="the CLI archive is invalid"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            output,
            git_commit="5" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )

    assert (output / "previous.txt").read_text(encoding="utf-8") == "previous"


def test_rejects_duplicate_cli_zip_members(tmp_path: Path) -> None:
    project, forge, cli_release = _project(tmp_path)
    cli = cli_release / "document-metadata-inspector-windows-x86_64.zip"
    with (
        pytest.warns(UserWarning, match="Duplicate name"),
        ZipFile(cli, "a", ZIP_DEFLATED) as archive,
    ):
        archive.writestr(f"{_CLI_ROOT}/docmeta.exe", b"duplicate")

    with pytest.raises(RuntimeError, match="the CLI archive is invalid"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            project / "release/windows-x64",
            git_commit="6" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )


@pytest.mark.parametrize(
    "unsafe_name",
    [
        "/absolute.txt",
        "C:/drive.txt",
        f"{_CLI_ROOT}\\backslash.txt",
        f"{_CLI_ROOT}/../escape.txt",
    ],
)
def test_rejects_unsafe_cli_zip_member_names(
    tmp_path: Path,
    unsafe_name: str,
) -> None:
    project, forge, cli_release = _project(tmp_path)
    cli = cli_release / "document-metadata-inspector-windows-x86_64.zip"
    with ZipFile(cli, "a", ZIP_DEFLATED) as archive:
        archive.writestr(unsafe_name, b"unsafe")

    with pytest.raises(RuntimeError, match="the CLI archive is invalid"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            project / "release/windows-x64",
            git_commit="7" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )


@pytest.mark.parametrize("mutation", ["missing", "extra", "directory"])
def test_rejects_unexpected_cli_zip_inventory(
    tmp_path: Path,
    mutation: str,
) -> None:
    project, forge, cli_release = _project(tmp_path)
    cli = cli_release / "document-metadata-inspector-windows-x86_64.zip"
    if mutation == "missing":
        with ZipFile(cli, "w", ZIP_DEFLATED) as archive:
            archive.writestr(f"{_CLI_ROOT}/docmeta.exe", b"trusted core")
            archive.writestr(
                f"{_CLI_ROOT}/SHA256SUMS",
                f"{sha256(b'trusted core').hexdigest()}  docmeta.exe\n",
            )
    else:
        with ZipFile(cli, "a", ZIP_DEFLATED) as archive:
            name = "unexpected.txt" if mutation == "extra" else f"{_CLI_ROOT}/nested/"
            archive.writestr(name, b"")

    with pytest.raises(RuntimeError, match="the CLI archive is invalid"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            project / "release/windows-x64",
            git_commit="8" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )


@pytest.mark.parametrize("member_type", [stat.S_IFLNK, stat.S_IFDIR])
def test_rejects_a_non_regular_cli_core_member(
    tmp_path: Path,
    member_type: int,
) -> None:
    project, forge, cli_release = _project(tmp_path)
    cli = cli_release / "document-metadata-inspector-windows-x86_64.zip"
    core = ZipInfo(f"{_CLI_ROOT}/docmeta.exe")
    core.create_system = 3
    core.external_attr = (member_type | 0o777) << 16
    with ZipFile(cli, "w", ZIP_DEFLATED) as archive:
        archive.writestr(core, b"trusted core")
        archive.writestr(
            f"{_CLI_ROOT}/SHA256SUMS",
            f"{sha256(b'trusted core').hexdigest()}  docmeta.exe\n",
        )
        archive.writestr(
            f"{_CLI_ROOT}/THIRD_PARTY_NOTICES.md",
            b"controlled notices\n",
        )

    with pytest.raises(RuntimeError, match="the CLI archive is invalid"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            project / "release/windows-x64",
            git_commit="9" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )


def test_rejects_an_encrypted_cli_zip_member(tmp_path: Path) -> None:
    project, forge, cli_release = _project(tmp_path)
    cli = cli_release / "document-metadata-inspector-windows-x86_64.zip"
    archive_bytes = bytearray(cli.read_bytes())
    start = 0
    while (offset := archive_bytes.find(b"PK\x03\x04", start)) != -1:
        archive_bytes[offset + 6] |= 1
        start = offset + 4
    start = 0
    while (offset := archive_bytes.find(b"PK\x01\x02", start)) != -1:
        archive_bytes[offset + 8] |= 1
        start = offset + 4
    _ = cli.write_bytes(archive_bytes)

    with pytest.raises(RuntimeError, match="the CLI archive is invalid"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            project / "release/windows-x64",
            git_commit="a" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )


@pytest.mark.parametrize(
    "stored_member",
    ["docmeta.exe", "SHA256SUMS", "THIRD_PARTY_NOTICES.md"],
)
def test_rejects_a_cli_member_that_is_not_deflated(
    tmp_path: Path,
    stored_member: str,
) -> None:
    project, forge, cli_release = _project(tmp_path)
    cli = cli_release / "document-metadata-inspector-windows-x86_64.zip"
    entries = {
        "docmeta.exe": b"trusted core",
        "SHA256SUMS": (
            f"{sha256(b'trusted core').hexdigest()}  docmeta.exe\n".encode()
        ),
        "THIRD_PARTY_NOTICES.md": b"controlled notices\n",
    }
    with ZipFile(cli, "w") as archive:
        for name, contents in entries.items():
            compression = ZIP_STORED if name == stored_member else ZIP_DEFLATED
            archive.writestr(
                f"{_CLI_ROOT}/{name}",
                contents,
                compress_type=compression,
            )

    with pytest.raises(RuntimeError, match="the CLI archive is invalid"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            project / "release/windows-x64",
            git_commit="2" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )


@pytest.mark.parametrize("member", ["docmeta.exe", "SHA256SUMS"])
def test_rejects_corrupt_deflated_cli_members_without_replacing_output(
    tmp_path: Path,
    member: str,
) -> None:
    project, forge, cli_release = _project(tmp_path)
    cli = cli_release / "document-metadata-inspector-windows-x86_64.zip"
    _corrupt_zip_member(cli, f"{_CLI_ROOT}/{member}")
    output = project / "release/windows-x64"
    output.mkdir()
    _ = (output / "previous.txt").write_text("previous", encoding="utf-8")

    with pytest.raises(RuntimeError, match="the CLI archive is invalid"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            output,
            git_commit="3" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )

    assert {path.name for path in output.iterdir()} == {"previous.txt"}


@pytest.mark.parametrize(
    "checksum",
    [
        b"\xff\xfe",
        b"0" * 64 + b"  docmeta.exe\nextra record\n",
        b"0" * 64 + b"  docmeta.exe\n",
    ],
)
def test_rejects_an_invalid_cli_internal_checksum(
    tmp_path: Path,
    checksum: bytes,
) -> None:
    project, forge, cli_release = _project(tmp_path)
    cli = cli_release / "document-metadata-inspector-windows-x86_64.zip"
    _ = _write_cli_archive(cli, checksum=checksum)

    with pytest.raises(RuntimeError, match="the CLI archive is invalid"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            project / "release/windows-x64",
            git_commit="b" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )


def test_rejects_a_valid_cli_archive_with_a_different_core(tmp_path: Path) -> None:
    project, forge, cli_release = _project(tmp_path)
    cli = cli_release / "document-metadata-inspector-windows-x86_64.zip"
    _ = _write_cli_archive(cli, core=b"altered core")

    with pytest.raises(RuntimeError, match="CLI archive core does not match"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            project / "release/windows-x64",
            git_commit="c" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )


@pytest.mark.parametrize(
    ("core", "notices"),
    [
        (b"trusted core plus one byte", b"controlled notices\n"),
        (b"trusted core", b"controlled notices plus one byte\n"),
    ],
)
def test_rejects_cli_members_with_external_size_mismatch(
    tmp_path: Path,
    core: bytes,
    notices: bytes,
) -> None:
    project, forge, cli_release = _project(tmp_path)
    cli = cli_release / "document-metadata-inspector-windows-x86_64.zip"
    _ = _write_cli_archive(cli, core=core, notices=notices)

    with pytest.raises(RuntimeError, match="the CLI archive is invalid"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            project / "release/windows-x64",
            git_commit="f" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )


def test_rejects_cli_notices_with_the_wrong_external_digest(tmp_path: Path) -> None:
    project, forge, cli_release = _project(tmp_path)
    cli = cli_release / "document-metadata-inspector-windows-x86_64.zip"
    _ = _write_cli_archive(cli, notices=b"Controlled notices\n")

    with pytest.raises(RuntimeError, match="the CLI archive is invalid"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            project / "release/windows-x64",
            git_commit="0" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )


def test_rejects_corrupt_cli_notices_and_preserves_existing_output(
    tmp_path: Path,
) -> None:
    project, forge, cli_release = _project(tmp_path)
    cli = cli_release / "document-metadata-inspector-windows-x86_64.zip"
    _corrupt_zip_member(cli, f"{_CLI_ROOT}/THIRD_PARTY_NOTICES.md")
    output = project / "release/windows-x64"
    output.mkdir()
    _ = (output / "previous.txt").write_text("previous", encoding="utf-8")

    with pytest.raises(RuntimeError, match="the CLI archive is invalid"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            output,
            git_commit="1" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )

    assert {path.name for path in output.iterdir()} == {"previous.txt"}


def test_cli_accepts_native_windows_amd64(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        assemble_windows_release_cli.platform,  # pyright: ignore[reportPrivateLocalImportUsage]
        "system",
        lambda: "Windows",
    )
    monkeypatch.setattr(
        assemble_windows_release_cli.platform,  # pyright: ignore[reportPrivateLocalImportUsage]
        "machine",
        lambda: "AMD64",
    )

    assemble_windows_release_cli._require_windows_x64()  # pyright: ignore[reportPrivateUsage]


@pytest.mark.parametrize(
    ("system", "machine"),
    (("Darwin", "arm64"), ("Windows", "arm64")),  # noqa: PT007 - specified matrix
)
def test_cli_rejects_non_windows_x64_hosts(
    monkeypatch: pytest.MonkeyPatch,
    system: str,
    machine: str,
) -> None:
    monkeypatch.setattr(
        assemble_windows_release_cli.platform,  # pyright: ignore[reportPrivateLocalImportUsage]
        "system",
        lambda: system,
    )
    monkeypatch.setattr(
        assemble_windows_release_cli.platform,  # pyright: ignore[reportPrivateLocalImportUsage]
        "machine",
        lambda: machine,
    )

    with pytest.raises(RuntimeError, match="requires native Windows x64"):
        assemble_windows_release_cli._require_windows_x64()  # pyright: ignore[reportPrivateUsage]
