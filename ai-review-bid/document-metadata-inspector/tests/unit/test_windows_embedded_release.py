"""Mac-side Windows x64 application and installer packaging contracts."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import TYPE_CHECKING
from zipfile import ZipFile

import pytest
from scripts import windows_embedded_release
from scripts.windows_embedded_release import (
    build_windows_embedded_release,
    compile_windows_installer,
    create_portable_zip,
    require_amd64_pe,
    verify_packaged_windows_application,
    verify_windows_release_directory,
)

if TYPE_CHECKING:
    from pathlib import Path


def _pe(machine: int) -> bytes:
    payload = bytearray(256)
    payload[0:2] = b"MZ"
    payload[0x3C:0x40] = (0x80).to_bytes(4, "little")
    payload[0x80:0x84] = b"PE\0\0"
    payload[0x84:0x86] = machine.to_bytes(2, "little")
    return bytes(payload)


def _packaged_application(root: Path) -> Path:
    application = root / "application"
    runtime = application / "resources/docmeta-runtime"
    files = {
        "python.exe": _pe(0x8664),
        "python312.dll": _pe(0x8664),
        "Lib/site-packages/dependency.pyd": _pe(0x8664),
        "app/src/document_metadata_inspector/cli.py": b"def main(): pass\n",
        "app/tools/manifest.json": b"{}\n",
        "app/tools/packaged/windows-x86_64/apache/jdk/bin/java.exe": _pe(0x8664),
        "app/tools/packaged/windows-x86_64/apache/worker.jar": b"worker",
        "app/tools/packaged/windows-x86_64/exiftool/exiftool.exe": _pe(0x8664),
        "SHA256SUMS": b"controlled\n",
        "RUNTIME-INFO.json": b"{}\n",
    }
    for relative, contents in files.items():
        path = runtime / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_bytes(contents)
    inventory = {
        "schema_version": "1",
        "files": {
            relative: sha256(contents).hexdigest()
            for relative, contents in sorted(files.items())
        },
    }
    _ = (runtime / "RUNTIME-SHA256SUMS.json").write_text(
        json.dumps(inventory) + "\n",
        encoding="utf-8",
    )
    _ = (application / "docmeta-review.exe").write_bytes(_pe(0x8664))
    return application


def test_pe_gate_accepts_amd64_and_rejects_i386(tmp_path: Path) -> None:
    """An accidental 32-bit application binary must not be labeled Windows x64."""
    amd64 = tmp_path / "amd64.exe"
    _ = amd64.write_bytes(_pe(0x8664))
    i386 = tmp_path / "i386.exe"
    _ = i386.write_bytes(_pe(0x014C))

    require_amd64_pe(amd64)
    with pytest.raises(RuntimeError, match="AMD64"):
        require_amd64_pe(i386)


def test_packaged_application_requires_complete_inventory_and_amd64_binaries(
    tmp_path: Path,
) -> None:
    """A valid shell without its embedded engines must never pass release gating."""
    application = _packaged_application(tmp_path)

    assert verify_packaged_windows_application(application) == 6

    dependency = (
        application / "resources/docmeta-runtime/Lib/site-packages/dependency.pyd"
    )
    _ = dependency.write_bytes(_pe(0x014C))
    with pytest.raises(RuntimeError, match=r"inventory|AMD64"):
        _ = verify_packaged_windows_application(application)


def test_portable_zip_contains_one_complete_top_level_application(
    tmp_path: Path,
) -> None:
    """Flattening or omitting resources would make the portable app unusable."""
    application = tmp_path / "application"
    (application / "resources/docmeta-runtime").mkdir(parents=True)
    _ = (application / "docmeta-review.exe").write_bytes(_pe(0x8664))
    _ = (application / "resources/docmeta-runtime/python.exe").write_bytes(_pe(0x8664))
    archive = tmp_path / "portable.zip"

    _ = create_portable_zip(application, archive, "DocumentMetadataInspector-0.1.0")

    with ZipFile(archive) as package:
        assert package.namelist() == [
            "DocumentMetadataInspector-0.1.0/docmeta-review.exe",
            "DocumentMetadataInspector-0.1.0/resources/docmeta-runtime/python.exe",
        ]
        assert package.read(
            "DocumentMetadataInspector-0.1.0/resources/docmeta-runtime/python.exe"
        ) == _pe(0x8664)


def test_native_makensis_wraps_the_exact_prebuilt_application(tmp_path: Path) -> None:
    """Installer compilation must receive the complete app directory and output path."""
    application = tmp_path / "application with spaces"
    application.mkdir()
    _ = (application / "docmeta-review.exe").write_bytes(_pe(0x8664))
    script = tmp_path / "windows-x64.nsi"
    _ = script.write_text("controlled NSIS script\n", encoding="utf-8")
    icon = tmp_path / "icon.ico"
    _ = icon.write_bytes(b"controlled icon")
    arguments = tmp_path / "makensis-arguments.txt"
    compiler_target = tmp_path / "Cellar/makensis"
    compiler_lines = (
        "#!/bin/sh",
        f": > '{arguments}'",
        'for argument in "$@"; do',
        f"  printf '%s\\n' \"$argument\" >> '{arguments}'",
        '  case "$argument" in',
        "    -DOUTPUT_FILE=*) output=${argument#-DOUTPUT_FILE=} ;;",
        "  esac",
        "done",
        "printf 'controlled setup' > \"$output\"",
    )
    compiler_target.parent.mkdir()
    _ = compiler_target.write_text(
        "\n".join(compiler_lines) + "\n",
        encoding="utf-8",
    )
    compiler_target.chmod(0o755)
    compiler = tmp_path / "bin/makensis"
    compiler.parent.mkdir()
    compiler.symlink_to(compiler_target)
    output = tmp_path / "DocumentMetadataInspector-0.1.0-win-x64-Setup.exe"

    _ = compile_windows_installer(
        application,
        output,
        script,
        icon,
        makensis=compiler,
    )

    assert output.read_bytes() == b"controlled setup"
    observed = arguments.read_text(encoding="utf-8").splitlines()
    assert f"-DAPP_SOURCE={application}" in observed
    assert f"-DOUTPUT_FILE={output}" in observed
    assert f"-DICON_FILE={icon}" in observed
    assert str(script) == observed[-1]


def test_release_orchestrator_publishes_installer_portable_and_hashes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful build must publish the complete fixed release set together."""
    project = tmp_path / "project"
    (project / "desktop/build/icons").mkdir(parents=True)
    (project / "desktop/installer").mkdir(parents=True)
    _ = (project / "desktop/package.json").write_text(
        json.dumps({"version": "0.1.0"}) + "\n",
        encoding="utf-8",
    )
    _ = (project / "desktop/build/icons/icon.ico").write_bytes(b"icon")
    _ = (project / "desktop/installer/windows-x64.nsi").write_text(
        "script\n",
        encoding="utf-8",
    )
    _ = (project / "THIRD_PARTY_NOTICES.md").write_text(
        "notices\n",
        encoding="utf-8",
    )
    application = _packaged_application(tmp_path)

    def build_runtime(
        _project_root: Path,
        destination: Path,
        _cache: Path,
    ) -> Path:
        destination.mkdir(parents=True)
        return destination

    def package_electron(_project_root: Path) -> Path:
        return application

    def compile_installer(
        _application: Path,
        output: Path,
        _script: Path,
        _icon: Path,
        *,
        makensis: Path,
    ) -> Path:
        assert makensis.name == "makensis"
        _ = output.write_bytes(b"controlled installer")
        return output

    monkeypatch.setattr(
        windows_embedded_release,
        "build_windows_embedded_runtime",
        build_runtime,
    )
    monkeypatch.setattr(
        windows_embedded_release,
        "_package_electron",
        package_electron,
    )
    monkeypatch.setattr(
        windows_embedded_release,
        "compile_windows_installer",
        compile_installer,
    )
    output = tmp_path / "release/windows-x64"

    result = build_windows_embedded_release(
        project,
        output,
        tmp_path / "cache",
        makensis=tmp_path / "makensis",
    )

    assert result == output
    assert sorted(path.name for path in result.iterdir()) == [
        "BUILD-INFO.json",
        "DocumentMetadataInspector-0.1.0-win-x64-Portable.zip",
        "DocumentMetadataInspector-0.1.0-win-x64-Setup.exe",
        "SHA256SUMS",
        "THIRD_PARTY_NOTICES.md",
    ]
    assert verify_windows_release_directory(result) == 4
    with ZipFile(
        result / "DocumentMetadataInspector-0.1.0-win-x64-Portable.zip"
    ) as package:
        assert (
            "DocumentMetadataInspector-0.1.0-win-x64/"
            "resources/docmeta-runtime/python.exe"
        ) in package.namelist()
