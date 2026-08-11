"""Regression checks for the native Electron release matrix."""

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_windows_forge_builds_an_installer_and_a_portable_zip() -> None:
    """Windows releases include Squirrel and a portable ZIP artifact."""
    forge_config = (_PROJECT_ROOT / "desktop/forge.config.ts").read_text(
        encoding="utf-8"
    )

    assert 'name: "@electron-forge/maker-squirrel"' in forge_config
    assert 'platforms: ["win32"]' in forge_config
    assert (
        '{ name: "@electron-forge/maker-zip", '
        'platforms: ["darwin", "win32"], config: {} }'
        in forge_config
    )


def test_release_matrix_builds_and_uploads_native_desktop_installers() -> None:
    """Every native core target must also produce its Electron deliverables."""
    workflow = (
        _PROJECT_ROOT / ".github/workflows/build-offline-releases.yml"
    ).read_text(encoding="utf-8")

    assert (
        "uses: pnpm/action-setup@0977fd99725f1db4007ccb2928dbb4e90d06cc86" in workflow
    )
    assert (
        "uses: actions/setup-node@249970729cb0ef3589644e2896645e5dc5ba9c38" in workflow
    )
    assert "working-directory: desktop" in workflow
    assert "run: pnpm install --frozen-lockfile" in workflow
    assert "run: pnpm make" in workflow
    assert "sudo apt-get install --yes fakeroot rpm" in workflow
    assert "name: docmeta-review-desktop-${{ matrix.platform }}" in workflow
    assert "path: desktop/out/make/**/*" in workflow


def test_macos_app_bundle_receives_a_complete_ad_hoc_signature() -> None:
    """Unsigned Electron's linker signature does not seal the app resources."""
    forge_config = (_PROJECT_ROOT / "desktop/forge.config.ts").read_text(
        encoding="utf-8"
    )

    assert 'identity: "-"' in forge_config
    assert "identityValidation: false" in forge_config
    assert 'execFileAsync("codesign"' in forge_config


def test_macos_signing_preserves_the_checksums_of_the_frozen_core() -> None:
    """Signing the outer app must not rewrite the already-verified core."""
    forge_config = (_PROJECT_ROOT / "desktop/forge.config.ts").read_text(
        encoding="utf-8"
    )

    assert "ignore: preserveBundledRuntimeSignature" in forge_config
    assert "verifyPackagedRuntimeHash" in forge_config


def test_electron_quit_waits_for_the_active_scan_tree() -> None:
    """Closing the last window must not bypass asynchronous tree cleanup."""
    main_source = (_PROJECT_ROOT / "desktop/src/main/main.ts").read_text(
        encoding="utf-8"
    )

    assert 'app.on("before-quit"' in main_source
    assert "scanService.isRunning" in main_source
    assert "event.preventDefault()" in main_source
    assert 'process.platform === "darwin"' in main_source
    assert ".stop().catch" in main_source


def test_folder_selection_errors_are_sanitized_before_crossing_ipc() -> None:
    """Filesystem exception text can contain private absolute paths."""
    main_source = (_PROJECT_ROOT / "desktop/src/main/main.ts").read_text(
        encoding="utf-8"
    )

    assert "无法读取所选目录" in main_source
    assert "请确认权限后重新选择" in main_source


def test_runtime_copy_reparses_the_copied_checksum_manifest() -> None:
    """The exact manifest shipped to the app must pass the strict parser."""
    prepare_source = (_PROJECT_ROOT / "desktop/scripts/prepare-runtime.mjs").read_text(
        encoding="utf-8"
    )

    assert "copiedExpectedSha256" in prepare_source
