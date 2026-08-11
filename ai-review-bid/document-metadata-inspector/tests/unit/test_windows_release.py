from __future__ import annotations

import json
import stat
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import cast
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest
from scripts import assemble_windows_release as assemble_windows_release_cli
from scripts import windows_release as windows_release_module
from scripts.windows_release import assemble_windows_release


def _write_file(path: Path, contents: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_bytes(contents)
    return path


_CLI_ROOT = "document-metadata-inspector-windows-x86_64"


def _write_cli_archive(
    path: Path,
    *,
    core: bytes = b"trusted core",
    checksum: bytes | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    checksum_bytes = checksum or f"{sha256(core).hexdigest()}  docmeta.exe\n".encode()
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr(f"{_CLI_ROOT}/docmeta.exe", core)
        archive.writestr(f"{_CLI_ROOT}/SHA256SUMS", checksum_bytes)
        archive.writestr(
            f"{_CLI_ROOT}/THIRD_PARTY_NOTICES.md",
            b"controlled notices\n",
        )
    return path


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
        if source.name == "windows-x64" and target == output and source != output:
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
        if source.name == "windows-x64" and target == output and source != output:
            _ = original_replace(source, target)
            message = "controlled staged publication failure"
            raise OSError(message)
        if source == output and target.name == "failed-windows-x64":
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
        if source.name == "windows-x64" and target == output and source != output:
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


def test_final_backup_cleanup_failure_retains_the_previous_complete_release(
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
        message = "controlled backup cleanup failure"
        raise OSError(message)

    monkeypatch.setattr(
        windows_release_module,
        "_cleanup_recovery_directory",
        fail_backup_cleanup,
    )

    with pytest.raises(
        RuntimeError,
        match=r"cleanup.*\.windows-x64-recovery-",
    ):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            output,
            git_commit="4" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )

    assert "BUILD-INFO.json" in {path.name for path in output.iterdir()}
    backups = list(output.parent.glob(".windows-x64-recovery-*"))
    assert len(backups) == 1
    assert (backups[0] / "previous.txt").read_text(encoding="utf-8") == "previous"


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
    core = project / "dist/windows-x86_64/onefile/docmeta.exe"
    output = project / "release/windows-x64"
    trusted_digest = sha256(b"trusted core").hexdigest()
    changed_digest = sha256(b"changed after validation").hexdigest()
    original_hash = windows_release_module._hash  # pyright: ignore[reportPrivateUsage]
    core_hash_calls = 0

    def changing_core_hash(path: Path) -> str:
        nonlocal core_hash_calls
        if path == core:
            core_hash_calls += 1
            return trusted_digest if core_hash_calls == 1 else changed_digest
        return original_hash(path)

    monkeypatch.setattr(windows_release_module, "_hash", changing_core_hash)

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
    _ = _write_cli_archive(cli, core=b"different but internally valid core")

    with pytest.raises(RuntimeError, match="CLI archive core does not match"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            project / "release/windows-x64",
            git_commit="c" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )


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
