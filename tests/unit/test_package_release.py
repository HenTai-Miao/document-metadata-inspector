"""Release-archive regressions for native executable delivery."""

from __future__ import annotations

import tarfile
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile

import pytest
from scripts.package_release import package_release


def _inputs(tmp_path: Path, executable_name: str) -> tuple[Path, Path, Path]:
    executable = tmp_path / executable_name
    _ = executable.write_bytes(b"controlled executable")
    _ = executable.chmod(0o755)
    checksum = tmp_path / "SHA256SUMS"
    _ = checksum.write_text(
        f"{sha256(executable.read_bytes()).hexdigest()}  {executable.name}\n",
        encoding="utf-8",
    )
    notices = tmp_path / "THIRD_PARTY_NOTICES.md"
    _ = notices.write_text("controlled notices", encoding="utf-8")
    return executable, checksum, notices


def test_packages_unix_executable_in_permission_preserving_tar(tmp_path: Path) -> None:
    executable, checksum, notices = _inputs(tmp_path, "docmeta")

    archive = package_release(
        executable,
        checksum,
        notices,
        tmp_path / "release",
        "darwin-arm64",
    )

    assert archive.suffixes[-2:] == [".tar", ".gz"]
    with tarfile.open(archive, "r:gz") as package:
        names = package.getnames()
        member = package.getmember("document-metadata-inspector-darwin-arm64/docmeta")
    assert "document-metadata-inspector-darwin-arm64/SHA256SUMS" in names
    assert member.mode & 0o111


def test_packages_windows_executable_in_zip(tmp_path: Path) -> None:
    executable, checksum, notices = _inputs(tmp_path, "docmeta.exe")

    archive = package_release(
        executable,
        checksum,
        notices,
        tmp_path / "release",
        "windows-x86_64",
    )

    assert archive.suffix == ".zip"
    with ZipFile(archive) as package:
        names = package.namelist()
    assert "document-metadata-inspector-windows-x86_64/docmeta.exe" in names


def test_repackages_existing_archive_with_current_executable(tmp_path: Path) -> None:
    executable, checksum, notices = _inputs(tmp_path, "docmeta")
    output = tmp_path / "release"
    first = package_release(
        executable,
        checksum,
        notices,
        output,
        "darwin-arm64",
    )
    _ = executable.write_bytes(b"updated executable")
    _ = checksum.write_text(
        f"{sha256(executable.read_bytes()).hexdigest()}  {executable.name}\n",
        encoding="utf-8",
    )

    second = package_release(
        executable,
        checksum,
        notices,
        output,
        "darwin-arm64",
    )

    assert second == first
    with tarfile.open(second, "r:gz") as package:
        member = package.extractfile("document-metadata-inspector-darwin-arm64/docmeta")
        assert member is not None
        assert member.read() == b"updated executable"
    archive_checksum = second.with_name(f"{second.name}.sha256")
    assert archive_checksum.read_text(encoding="utf-8") == (
        f"{sha256(second.read_bytes()).hexdigest()}  {second.name}\n"
    )


def test_publication_failure_restores_the_previous_archive_and_checksum(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable, checksum, notices = _inputs(tmp_path, "docmeta")
    output = tmp_path / "release"
    archive = package_release(
        executable,
        checksum,
        notices,
        output,
        "darwin-arm64",
    )
    archive_checksum = archive.with_name(f"{archive.name}.sha256")
    old_archive = archive.read_bytes()
    old_checksum = archive_checksum.read_bytes()
    _ = executable.write_bytes(b"updated executable")
    _ = checksum.write_text(
        f"{sha256(executable.read_bytes()).hexdigest()}  {executable.name}\n",
        encoding="utf-8",
    )
    original_replace = Path.replace

    def fail_new_checksum(source: Path, target: Path) -> Path:
        if source.name == archive_checksum.name and source.parent != output:
            message = "controlled checksum publication failure"
            raise OSError(message)
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", fail_new_checksum)

    with pytest.raises(OSError, match="controlled checksum"):
        _ = package_release(
            executable,
            checksum,
            notices,
            output,
            "darwin-arm64",
        )

    assert archive.read_bytes() == old_archive
    assert archive_checksum.read_bytes() == old_checksum
