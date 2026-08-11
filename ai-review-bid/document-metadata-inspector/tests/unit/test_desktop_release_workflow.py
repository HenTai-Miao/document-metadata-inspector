"""Regression checks for the native Electron release matrix."""

import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path
from typing import cast

import pytest
import yaml

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_WINDOWS_CONDITION = "matrix.platform == 'windows-x86_64'"
_NON_WINDOWS_CONDITION = "matrix.platform != 'windows-x86_64'"
_WINDOWS_VERIFIER = "powershell.exe -NoProfile -File scripts/verify_windows_release.ps1"
_WINDOWS_VERIFIER_ARGUMENTS = "-ReleaseDirectory release/windows-x64 -Mode All"
_UPLOAD_ACTION = "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
_NATIVE_ARTIFACT_NAME = "document-metadata-inspector-${{ matrix.platform }}"
_DESKTOP_ARTIFACT_NAME = "docmeta-review-desktop-${{ matrix.platform }}"
_WINDOWS_POWERSHELL = shutil.which("powershell.exe") if os.name == "nt" else None

type YamlMapping = dict[object, object]
type WorkflowStep = dict[str, object]
type IndexedStep = tuple[int, WorkflowStep]


def _yaml_mapping(value: object) -> YamlMapping:
    assert isinstance(value, dict)
    return cast("YamlMapping", value)


def _workflow_step(value: object) -> WorkflowStep:
    mapping = _yaml_mapping(value)
    assert all(isinstance(key, str) for key in mapping)
    return cast("WorkflowStep", mapping)


def _release_steps() -> list[WorkflowStep]:
    raw_workflow = cast(
        "object",
        yaml.safe_load(
            (_PROJECT_ROOT / ".github/workflows/build-offline-releases.yml").read_text(
                encoding="utf-8"
            )
        ),
    )
    workflow = _yaml_mapping(raw_workflow)
    jobs = _yaml_mapping(workflow.get("jobs"))
    release = _yaml_mapping(jobs.get("release"))
    raw_steps_value = release.get("steps")
    assert isinstance(raw_steps_value, list)
    raw_steps = cast("list[object]", raw_steps_value)
    return [_workflow_step(step) for step in raw_steps]


def _steps_matching(
    steps: list[WorkflowStep], expected: dict[str, str]
) -> list[IndexedStep]:
    return [
        (index, step)
        for index, step in enumerate(steps)
        if all(step.get(field) == value for field, value in expected.items())
    ]


def _single_step(items: list[IndexedStep]) -> IndexedStep:
    assert len(items) == 1
    return items[0]


def _upload_config(step: WorkflowStep) -> WorkflowStep:
    return _workflow_step(step.get("with"))


def _artifact_name(step: WorkflowStep) -> str:
    name = _upload_config(step).get("name")
    assert isinstance(name, str)
    return name


def _is_artifact_upload(step: WorkflowStep) -> bool:
    uses = step.get("uses")
    return isinstance(uses, str) and uses.startswith("actions/upload-artifact@")


def _assert_native_upload(step: WorkflowStep) -> None:
    assert step.get("uses") == _UPLOAD_ACTION
    assert "if" not in step
    upload_config = _upload_config(step)
    assert upload_config.get("name") == _NATIVE_ARTIFACT_NAME
    assert (
        upload_config.get("path")
        == "release/document-metadata-inspector-${{ matrix.platform }}*"
    )


def _assert_desktop_upload(step: WorkflowStep, *, condition: str, path: str) -> None:
    assert step.get("uses") == _UPLOAD_ACTION
    assert step.get("if") == condition
    upload_config = _upload_config(step)
    assert upload_config.get("name") == _DESKTOP_ARTIFACT_NAME
    assert upload_config.get("path") == path


def _windows_release_verifier_source() -> str:
    return (_PROJECT_ROOT / "scripts/verify_windows_release.ps1").read_text(
        encoding="utf-8"
    )


def _run_git(repository: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    git = shutil.which("git")
    assert git is not None
    return subprocess.run(  # noqa: S603
        (git, *arguments),
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_windows_powershell_function(
    source_path: Path,
    function_name: str,
    assertions: str,
) -> subprocess.CompletedProcess[str]:
    assert _WINDOWS_POWERSHELL is not None
    command = f"""
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $env:DOCMETA_POWERSHELL_SOURCE,
    [ref]$tokens,
    [ref]$parseErrors
)
if ($parseErrors.Count -ne 0) {{ throw "PowerShell source did not parse" }}
$definition = $ast.Find({{
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -ceq "{function_name}"
}}, $true)
if ($null -eq $definition) {{ throw "PowerShell function is missing" }}
Invoke-Expression $definition.Extent.Text
{assertions}
"""
    environment = os.environ.copy()
    environment["DOCMETA_POWERSHELL_SOURCE"] = str(source_path)
    return subprocess.run(  # noqa: S603
        (
            _WINDOWS_POWERSHELL,
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            command,
        ),
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        timeout=30,
    )


def test_windows_one_command_build_uses_uv_nvm_and_vendored_java() -> None:
    """The target-machine entry must not provision or depend on a JDK."""
    build_script = _PROJECT_ROOT / "scripts/build_windows_x64.ps1"

    assert build_script.is_file()
    source = build_script.read_text(encoding="utf-8")
    for required in (
        "Set-StrictMode -Version Latest",
        '$ErrorActionPreference = "Stop"',
        "Get-Command git -ErrorAction Stop",
        "Get-Command uv",
        "Get-Command nvm",
        '"install", "24"',
        '"use", "24"',
        "pnpm@11.10.0",
        '"python", "install", "3.12.13"',
        "windows_vendored_java.py",
        '"pnpm", "make"',
        "assemble_windows_release.py",
        "verify_windows_release.ps1",
        '"All"',
    ):
        assert required in source
    assert source.index("Get-Command git -ErrorAction Stop") < source.index(
        '$LastStage = "Node.js 24 setup"'
    )
    assert "mvnw" not in source
    assert "JAVA_HOME" not in source
    assert "bootstrap_jdk.py" not in source

    workflow_path = _PROJECT_ROOT / ".github/workflows/build-offline-releases.yml"
    workflow = workflow_path.read_text(encoding="utf-8")
    assert "powershell.exe -NoProfile -File" in workflow


def test_ruff_exclusions_are_limited_to_named_prototype_generators() -> None:
    """The release gate skips only non-product prototype generators."""
    raw_config = cast(
        "object",
        tomllib.loads((_PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")),
    )
    config = _yaml_mapping(raw_config)
    tool = _yaml_mapping(config.get("tool"))
    ruff = _yaml_mapping(tool.get("ruff"))

    assert ruff.get("extend-exclude") == [
        "scripts/gen_10pages.py",
        "scripts/gen_5layouts.py",
        "scripts/gen_app_prototype.py",
        "scripts/gen_docmeta_10layouts.py",
        "scripts/gen_prototypes.py",
        "scripts/gen_research_prototypes.py",
        "scripts/gen_spec_prototype.py",
        "scripts/gen_test_bids.py",
    ]


def test_windows_scripts_support_powershell_51() -> None:
    """Both Windows scripts must stay runnable in built-in PowerShell 5.1."""
    verifier = _windows_release_verifier_source()
    assert "-NoEnumerate" not in verifier

    build_script = _PROJECT_ROOT / "scripts/build_windows_x64.ps1"
    assert build_script.is_file()
    forbidden_ternary = re.compile(r"(?m)^[^#\r\n]*\?\s+[^:\r\n]+\s*:\s*[^#\r\n]+$")
    for source in (build_script.read_text(encoding="utf-8"), verifier):
        for unsupported in ("-NoEnumerate", "ForEach-Object -Parallel", "??", "?."):
            assert unsupported not in source
        assert forbidden_ternary.search(source) is None


def test_windows_build_failure_messages_delimit_variables_before_colons() -> None:
    """PowerShell 5.1 must not parse message colons as variable scopes."""
    source = (_PROJECT_ROOT / "scripts/build_windows_x64.ps1").read_text(
        encoding="utf-8"
    )

    assert "${exitCode}: $FilePath" in source
    assert "${LastStage}: $($_.Exception.Message)" in source


def test_windows_release_verifier_guards_both_raw_json_object_boundaries() -> None:
    """Singleton arrays must be rejected before PowerShell 5.1 unwraps them."""
    verifier = _windows_release_verifier_source()
    assert "function Test-TopLevelJsonObject" in verifier

    report_start = verifier.index("$jsonText = Invoke-BoundedProcess")
    report_guard = verifier.index("Test-TopLevelJsonObject $jsonText", report_start)
    report_parse = verifier.index(
        "ConvertFrom-Json -InputObject $jsonText", report_start
    )
    assert report_guard < report_parse

    build_info_start = verifier.index("$buildInfoText = Get-Content")
    build_info_guard = verifier.index(
        "Test-TopLevelJsonObject $buildInfoText", build_info_start
    )
    build_info_parse = verifier.index(
        "ConvertFrom-Json -InputObject $buildInfoText", build_info_start
    )
    assert build_info_guard < build_info_parse


@pytest.mark.skipif(
    _WINDOWS_POWERSHELL is None,
    reason="requires built-in Windows PowerShell",
)
def test_powershell_51_rejects_singleton_arrays_at_both_json_boundaries() -> None:
    """Run the verifier's real raw-shape predicate in Windows PowerShell 5.1."""
    result = _run_windows_powershell_function(
        _PROJECT_ROOT / "scripts/verify_windows_release.ps1",
        "Test-TopLevelJsonObject",
        """
if (Test-TopLevelJsonObject '[{"schema_version":"1.0"}]') {
    throw "singleton frozen-report array was accepted"
}
if (Test-TopLevelJsonObject '[{"schema_version":"1"}]') {
    throw "singleton BUILD-INFO array was accepted"
}
if (-not (Test-TopLevelJsonObject '{"schema_version":"1"}')) {
    throw "top-level object was rejected"
}
""",
    )

    assert result.returncode == 0, result.stderr


def test_windows_build_preflight_requires_windows_10_or_11_client_x64() -> None:
    """Unsupported Windows versions, servers, and CPU architectures fail early."""
    source = (_PROJECT_ROOT / "scripts/build_windows_x64.ps1").read_text(
        encoding="utf-8"
    )
    for required in (
        "function Test-Windows10Or11X64Client",
        "Win32_OperatingSystem",
        "Win32_Processor",
        "ProductType",
        "Architecture",
        '"process.arch"',
        '-cne "x64"',
    ):
        assert required in source

    host_query = source.index("Win32_OperatingSystem")
    dependency_check = source.index("Get-Command uv")
    dependency_install = source.index('"install", "24"')
    assert host_query < dependency_check < dependency_install
    node_use = source.index('"use", "24"')
    node_architecture = source.index('"process.arch"')
    assert node_use < node_architecture


@pytest.mark.skipif(
    _WINDOWS_POWERSHELL is None,
    reason="requires built-in Windows PowerShell",
)
def test_powershell_51_rejects_unsupported_windows_host_shapes() -> None:
    """Run the build entry's real host classifier on supported and rejected data."""
    result = _run_windows_powershell_function(
        _PROJECT_ROOT / "scripts/build_windows_x64.ps1",
        "Test-Windows10Or11X64Client",
        """
$windows10 = [pscustomobject]@{ Version = "10.0.19045"; ProductType = 1 }
$windows11 = [pscustomobject]@{ Version = "10.0.26100"; ProductType = 1 }
$windows7 = [pscustomobject]@{ Version = "6.1.7601"; ProductType = 1 }
$server = [pscustomobject]@{ Version = "10.0.20348"; ProductType = 3 }
$x64 = @([pscustomobject]@{ Architecture = 9 })
$arm64 = @([pscustomobject]@{ Architecture = 12 })
if (-not (Test-Windows10Or11X64Client $windows10 $x64)) {
    throw "Windows 10 x64 client was rejected"
}
if (-not (Test-Windows10Or11X64Client $windows11 $x64)) {
    throw "Windows 11 x64 client was rejected"
}
if (Test-Windows10Or11X64Client $windows7 $x64) {
    throw "Windows 7 was accepted"
}
if (Test-Windows10Or11X64Client $server $x64) {
    throw "Windows Server was accepted"
}
if (Test-Windows10Or11X64Client $windows11 $arm64) {
    throw "Windows ARM64 was accepted"
}
""",
    )

    assert result.returncode == 0, result.stderr


def test_windows_forge_builds_an_installer_and_a_portable_zip() -> None:
    """Windows releases include Squirrel and a portable ZIP artifact."""
    forge_config = (_PROJECT_ROOT / "desktop/forge.config.ts").read_text(
        encoding="utf-8"
    )

    assert 'name: "@electron-forge/maker-squirrel"' in forge_config
    assert 'platforms: ["win32"]' in forge_config
    zip_maker_name = '{ name: "@electron-forge/maker-zip", '
    zip_maker_platforms = 'platforms: ["darwin", "win32"], config: {} }'
    assert f"{zip_maker_name}{zip_maker_platforms}" in forge_config


def test_release_matrix_builds_and_uploads_native_desktop_installers() -> None:
    """Every native core target must also produce its Electron deliverables."""
    release_steps = _release_steps()
    _ = _single_step(
        _steps_matching(
            release_steps,
            {"uses": "pnpm/action-setup@0977fd99725f1db4007ccb2928dbb4e90d06cc86"},
        )
    )
    _ = _single_step(
        _steps_matching(
            release_steps,
            {"uses": "actions/setup-node@249970729cb0ef3589644e2896645e5dc5ba9c38"},
        )
    )
    _ = _single_step(
        _steps_matching(
            release_steps,
            {
                "name": "Install locked desktop environment",
                "working-directory": "desktop",
                "run": "pnpm install --frozen-lockfile",
            },
        )
    )
    _, linux_maker_tools = _single_step(
        _steps_matching(
            release_steps,
            {"name": "Install Linux desktop maker tools"},
        )
    )
    assert linux_maker_tools.get("if") == "runner.os == 'Linux'"
    linux_maker_tools_run = linux_maker_tools.get("run")
    assert isinstance(linux_maker_tools_run, str)
    assert "sudo apt-get install --yes fakeroot rpm" in linux_maker_tools_run

    maker_index, _ = _single_step(
        _steps_matching(
            release_steps,
            {
                "name": "Build native Electron installers",
                "working-directory": "desktop",
                "run": "pnpm make",
            },
        )
    )
    package_release_index, package_release = _single_step(
        _steps_matching(
            release_steps,
            {"run": "uv run python scripts/package_release.py"},
        )
    )
    assert package_release.get("name") == "Create checksummed delivery archive"
    assert "if" not in package_release
    assembly_index, assembly = _single_step(
        _steps_matching(
            release_steps,
            {
                "name": "Assemble Windows x64 delivery",
                "run": "uv run python scripts/assemble_windows_release.py",
            },
        )
    )
    verifier_index, verifier = _single_step(
        _steps_matching(
            release_steps,
            {
                "name": "Verify Windows x64 delivery",
                "run": f"{_WINDOWS_VERIFIER} {_WINDOWS_VERIFIER_ARGUMENTS}",
            },
        )
    )
    assert maker_index < package_release_index < assembly_index < verifier_index
    assert assembly.get("if") == _WINDOWS_CONDITION
    assert verifier.get("if") == _WINDOWS_CONDITION

    uploads = [
        (index, step)
        for index, step in enumerate(release_steps)
        if _is_artifact_upload(step)
    ]
    assert len(uploads) == 3
    assert all(step.get("uses") == _UPLOAD_ACTION for _, step in uploads)

    native_uploads = [
        (index, step)
        for index, step in uploads
        if _artifact_name(step) == _NATIVE_ARTIFACT_NAME
    ]
    desktop_uploads = [
        (index, step)
        for index, step in uploads
        if _artifact_name(step) == _DESKTOP_ARTIFACT_NAME
    ]
    assert len(native_uploads) == 1
    assert len(desktop_uploads) == 2
    assert sorted(_artifact_name(step) for _, step in uploads) == sorted(
        [_NATIVE_ARTIFACT_NAME, _DESKTOP_ARTIFACT_NAME, _DESKTOP_ARTIFACT_NAME]
    )

    native_upload_index, native_upload = native_uploads[0]
    _assert_native_upload(native_upload)

    windows_upload_index, windows_upload = _single_step(
        [
            (index, step)
            for index, step in desktop_uploads
            if step.get("if") == _WINDOWS_CONDITION
        ]
    )
    non_windows_upload_index, non_windows_upload = _single_step(
        [
            (index, step)
            for index, step in desktop_uploads
            if step.get("if") == _NON_WINDOWS_CONDITION
        ]
    )
    _assert_desktop_upload(
        windows_upload, condition=_WINDOWS_CONDITION, path="release/windows-x64/**/*"
    )
    _assert_desktop_upload(
        non_windows_upload,
        condition=_NON_WINDOWS_CONDITION,
        path="desktop/out/make/**/*",
    )

    assert verifier_index < native_upload_index
    assert verifier_index < windows_upload_index
    assert verifier_index < non_windows_upload_index


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
    assert (
        "await verifyPackagedRuntimeHash(applicationPath, result.platform)"
        in forge_config
    )


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


def test_electron_uses_the_approved_custom_window_frame() -> None:
    """The app must not fall back to Electron's native title or default menu."""
    main_source = (_PROJECT_ROOT / "desktop/src/main/main.ts").read_text(
        encoding="utf-8"
    )

    assert "frame: false" in main_source
    assert "Menu.setApplicationMenu(null)" in main_source
    assert "registerWindowControlHandlers" in main_source
    assert 'window.on("maximize"' in main_source
    assert 'window.on("unmaximize"' in main_source
    assert "WINDOW_CONTROL_CHANNELS.stateChanged" in main_source


def test_custom_titlebar_marks_drag_and_control_regions() -> None:
    """Only the titlebar background may drag; every control stays clickable."""
    styles = (_PROJECT_ROOT / "desktop/src/renderer/styles.css").read_text(
        encoding="utf-8"
    )

    assert "-webkit-app-region: drag" in styles
    assert "\n  app-region: drag;" in styles
    assert "-webkit-app-region: no-drag" in styles
    assert "\n  app-region: no-drag;" in styles
    assert ".window-control--close:hover" in styles
    assert "#c42b35" in styles


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


def test_windows_release_verifier_checks_hashes_portable_and_installed_cores() -> None:
    verifier = _windows_release_verifier_source()

    assert "Get-FileHash -Algorithm SHA256" in verifier
    assert "Expand-Archive" in verifier
    assert '"文档元数据核验 portable "' in verifier
    assert "ConvertFrom-Json" in verifier
    assert "checks.Count -ne 6" in verifier
    assert 'ArgumentList "--silent"' in verifier
    assert 'ArgumentList "--uninstall", "-s"' in verifier
    assert "Test-CleanInstallRoot $installRoot" in verifier


def test_windows_release_verifier_rejects_manifest_duplicates_and_wrong_sets() -> None:
    verifier = _windows_release_verifier_source()

    assert "Dictionary[string, object]" in verifier
    assert "OrdinalIgnoreCase" in verifier
    assert "if ($line -cnotmatch" in verifier
    assert "$manifest.ContainsKey($filename)" in verifier
    assert "SHA256SUMS contains a duplicate filename" in verifier
    assert "Get-ManifestKind $filename" in verifier
    assert 'if ($Filename -ceq "BUILD-INFO.json")' in verifier
    assert 'if ($Filename -ceq "THIRD_PARTY_NOTICES.md")' in verifier
    assert "$setupRecords.Count -ne 1" in verifier
    assert "$portableRecords.Count -ne 1" in verifier
    assert "$cliRecords.Count -ne 1" in verifier
    assert "SHA256SUMS does not contain the exact release file set" in verifier


def test_windows_release_verifier_binds_artifacts_to_validated_records() -> None:
    verifier = _windows_release_verifier_source()

    assert "$setup = $setupRecord.Path" in verifier
    assert "$portable = $portableRecord.Path" in verifier
    assert "Get-SingleFile" not in verifier
    assert "foreach ($record in $manifest.Values)" in verifier
    assert verifier.index("$buildInfoText = Get-Content") > verifier.index(
        "foreach ($record in $manifest.Values)"
    )
    assert "$expectedSetupName" in verifier
    assert "$expectedPortableName" in verifier
    assert "$expectedCliName" in verifier
    assert "$setupRecord.Name -cne $expectedSetupName" in verifier
    assert "$portableRecord.Name -cne $expectedPortableName" in verifier
    assert "$cliRecord.Name -cne $expectedCliName" in verifier


def test_windows_release_verifier_validates_exact_build_info_contract() -> None:
    verifier = _windows_release_verifier_source()

    assert "$requiredBuildInfoKeys" in verifier
    assert "$requiredVersionKeys" in verifier
    assert "$buildInfo.PSObject.Properties.Name" in verifier
    assert "$buildInfo.versions.PSObject.Properties.Name" in verifier
    assert '$buildInfo.schema_version -cne "1"' in verifier
    assert '$buildInfo.target_platform -cne "windows-x86_64"' in verifier
    assert "^[0-9a-f]{40}$" in verifier
    assert "^[0-9a-f]{64}$" in verifier
    assert "yyyy-MM-ddTHH:mm:ssZ" in verifier
    assert "Test-NonEmptyString $buildInfo.product_version" in verifier
    assert "Test-NonEmptyString $buildInfo.versions.$key" in verifier


def test_windows_release_verifier_bounds_every_child_process() -> None:
    verifier = _windows_release_verifier_source()

    assert "function Invoke-BoundedProcess" in verifier
    assert "function Stop-ProcessTreeWithTaskkill" in verifier
    assert verifier.count("Start-Process") == 2
    assert "RedirectStandardOutput" in verifier
    assert "RedirectStandardError" in verifier
    assert "while (-not $process.HasExited)" in verifier
    assert verifier.count("Test-CaptureLimitExceeded") >= 3
    assert "$maxCaptureBytes = 4MB" in verifier
    assert "$stdoutLength -gt $MaxCaptureBytes" in verifier
    assert "$stderrLength -gt $MaxCaptureBytes" in verifier
    assert "GetFolderPath" in verifier
    assert '"taskkill.exe"' in verifier
    assert 'ArgumentList "/PID", $Process.Id.ToString(), "/T", "/F"' in verifier
    assert "$taskkill.WaitForExit(10000)" in verifier
    assert "$Process.WaitForExit(5000)" in verifier
    assert "taskkill returned exit code" in verifier
    assert verifier.count("Stop-ProcessTreeWithTaskkill $process") >= 3
    assert ".Kill($true)" not in verifier
    assert verifier.index("$process.Dispose()") < verifier.index(
        "Remove-Item -LiteralPath $processRoot"
    )
    assert "Invoke-BoundedProcess -FilePath $CorePath" in verifier
    assert "Invoke-BoundedProcess -FilePath $setup" in verifier
    assert "Invoke-BoundedProcess -FilePath $update" in verifier
    assert verifier.count("Invoke-BoundedProcess -FilePath") == 3
    assert verifier.count("-TimeoutSeconds") == 3


def test_windows_release_verifier_requires_exact_frozen_report_identity() -> None:
    verifier = _windows_release_verifier_source()

    assert "$requiredReportKeys" in verifier
    assert "$requiredCheckKeys" in verifier
    assert "$report.schema_version -isnot [string]" in verifier
    assert '$report.schema_version -cne "1.0"' in verifier
    assert "$report.passed -is [bool]" in verifier
    assert "$check -is [pscustomobject]" in verifier
    assert "$check.name -is [string]" in verifier
    assert "$check.status -is [string]" in verifier
    assert "$check.message -is [string]" in verifier
    assert '"component:apache-tika"' in verifier
    assert '"component:exiftool"' in verifier
    assert '"sample:pdf"' in verifier
    assert '"sample:word"' in verifier
    assert '"sample:excel"' in verifier
    assert '"sample:source-integrity"' in verifier
    assert "$seenCheckNames.Add($check.name)" in verifier
    assert "$seenCheckNames.SetEquals($expectedCheckNames)" in verifier


def test_windows_release_verifier_fails_closed_on_install_root_io_errors() -> None:
    verifier = _windows_release_verifier_source()

    assert verifier.count("Test-CleanInstallRoot $installRoot") == 2
    assert "Test-Path -LiteralPath $InstallRoot -ErrorAction Stop" in verifier
    assert "Test-Path -LiteralPath $InstallRoot -PathType Container" in verifier
    assert "Get-InstalledCores $installRoot" in verifier
    assert "Get-RemainingApps $installRoot" in verifier
    assert "Get-ChildItem -LiteralPath $InstallRoot" in verifier
    assert "-ErrorAction Stop" in verifier
    assert "SilentlyContinue" not in verifier


def test_windows_release_verifier_protects_partial_canary_creation() -> None:
    verifier = _windows_release_verifier_source()
    all_mode = verifier[verifier.index('if ($Mode -eq "All")') :]

    assert "$canaryRootCreated = $false" in all_mode
    assert "$canaryCreated = $false" in all_mode
    assert all_mode.index("try {") < all_mode.index(
        "New-Item -ItemType Directory -Path $canaryRoot"
    )
    assert "$canaryRootCreated = $true" in all_mode
    assert "$canaryCreated = $true" in all_mode
    assert "if ($canaryRootCreated)" in all_mode
    assert "Remove-Item -LiteralPath $canaryRoot -Recurse -Force" in all_mode
    assert "if ($canaryCreated -and -not $canaryPreserved)" in all_mode


def test_windows_release_verifier_uninstalls_only_its_owned_setup() -> None:
    verifier = _windows_release_verifier_source()
    all_mode = verifier[verifier.index('if ($Mode -eq "All")') :]
    first_guard = all_mode.index("Test-CleanInstallRoot $installRoot")
    second_guard = all_mode.index(
        "Test-CleanInstallRoot $installRoot",
        first_guard + 1,
    )
    setup_call = all_mode.index("Invoke-BoundedProcess -FilePath $setup")
    owned_cleanup = all_mode.index("if ($setupStarted)", setup_call)

    assert "$setupStarted = $false" in all_mode
    assert "[ref]$Started = $null" in verifier
    assert "$Started.Value = $true" in verifier
    assert "-Started ([ref]$setupStarted)" in all_mode
    assert second_guard < all_mode.index("try {", second_guard) < setup_call
    assert setup_call < owned_cleanup
    assert all_mode.index("$update = Join-Path", owned_cleanup) > owned_cleanup
    assert (
        all_mode.index("Get-RemainingApps $installRoot", owned_cleanup) > owned_cleanup
    )


def test_windows_dual_release_documentation_matches_the_build_commands() -> None:
    packaging = (_PROJECT_ROOT / "docs/packaging.md").read_text(encoding="utf-8")
    acceptance = (_PROJECT_ROOT / "docs/windows-x64-release-acceptance.md").read_text(
        encoding="utf-8"
    )
    windows_start = packaging.index("## Windows 10/11 x64")
    windows_end = packaging.index("## 开发/打包机器的自动检测", windows_start)
    windows_packaging = packaging[windows_start:windows_end]

    for fragment in (
        "powershell.exe -NoProfile -ExecutionPolicy Bypass",
        ".\\scripts\\build_windows_x64.ps1",
        "PowerShell 5.1",
        "OpenJDK21U-jre_x64_windows_hotspot_21.0.12_8.zip",
        "document-metadata-apache-worker.jar",
        "tools/build-cache",
        "不使用系统 Java 17",
    ):
        assert fragment in windows_packaging
    assert "build_release.py --mode onefile" not in windows_packaging
    assert "java-worker/mvnw.cmd" not in windows_packaging
    for filename in (
        "DocumentMetadataInspector-<version>-win-x64-Setup.exe",
        "DocumentMetadataInspector-<version>-win-x64-Portable.zip",
        "DocumentMetadataInspector-<version>-win-x64-CLI.zip",
    ):
        assert filename in windows_packaging
    assert "powershell.exe -NoProfile" in acceptance
    assert "Java/JDK 下载 URL" in acceptance
    assert "Windows Defender" in acceptance
    assert "SmartScreen" in acceptance
    assert "docmeta-runtime/docmeta.exe" in acceptance
    for fragment in (
        "Git 是源码同步与发布元数据前置条件",
        "构建工具链仍只有 `uv`、`nvm` 和内置 PowerShell 5.1",
        "CI 不调用 `scripts/build_windows_x64.ps1`",
        "`actions/setup-java` 提供精确 JDK 21",
        "Maven Wrapper 验证 Java 源码",
    ):
        assert fragment in packaging


def test_windows_acceptance_always_cleans_logs_and_process_java() -> None:
    acceptance = (_PROJECT_ROOT / "docs/windows-x64-release-acceptance.md").read_text(
        encoding="utf-8"
    )
    java_start = acceptance.index("$env:JAVA_HOME")
    java_end = acceptance.index("```", java_start)
    java_cleanup = acceptance[java_start:java_end]
    for fragment in (
        "Get-Command java.exe -CommandType Application",
        "while ($null -ne $javaCommand)",
        "Split-Path -LiteralPath $javaCommand.Source -Parent",
        "$env:Path =",
        "$env:JAVA_HOME = $null",
    ):
        assert fragment in java_cleanup

    build_start = acceptance.index("$buildLog =")
    build_end = acceptance.index("在验收记录中", build_start)
    build_check = acceptance[build_start:build_end]
    assert build_check.index("try {") < build_check.index("powershell.exe -NoProfile")
    assert build_check.index("finally {") < build_check.index(
        "Remove-Item -LiteralPath $buildLog"
    )
    for field in ("`stage`", "`exit_code`", "`sha256`"):
        assert field in acceptance


def test_windows_acceptance_checks_tamper_failure_and_restore() -> None:
    acceptance = (_PROJECT_ROOT / "docs/windows-x64-release-acceptance.md").read_text(
        encoding="utf-8"
    )
    tamper_start = acceptance.index('$workerJar = "tools/prebuilt/')
    tamper_end = acceptance.index("```", tamper_start)
    tamper_check = acceptance[tamper_start:tamper_end]

    assert "2>&1" in tamper_check
    assert "$preflightExitCode = $LASTEXITCODE" in tamper_check
    assert "git restore --source=HEAD --worktree --staged -- $workerJar" in tamper_check
    assert "$restoreExitCode = $LASTEXITCODE" in tamper_check
    assert "$restoreExitCode -ne 0" in tamper_check
    assert "git diff --cached --exit-code HEAD -- $workerJar" in tamper_check
    assert "$indexDiffExitCode = $LASTEXITCODE" in tamper_check
    assert "$indexDiffExitCode -ne 0" in tamper_check
    assert "git diff --exit-code HEAD -- $workerJar" in tamper_check
    assert "$worktreeDiffExitCode = $LASTEXITCODE" in tamper_check
    assert "$worktreeDiffExitCode -ne 0" in tamper_check


def test_windows_acceptance_restore_handles_a_staged_tampered_worker(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    worker_relative = Path(
        "tools/prebuilt/windows-x86_64/document-metadata-apache-worker.jar"
    )
    worker = repository / worker_relative
    worker.parent.mkdir(parents=True)
    committed_worker = b"committed Worker JAR"

    assert _run_git(repository, "init", "--quiet").returncode == 0
    assert (
        _run_git(repository, "config", "user.email", "test@example.invalid").returncode
        == 0
    )
    assert _run_git(repository, "config", "user.name", "Doc Test").returncode == 0
    _ = worker.write_bytes(committed_worker)
    assert _run_git(repository, "add", str(worker_relative)).returncode == 0
    assert _run_git(repository, "commit", "--quiet", "-m", "baseline").returncode == 0

    # Given tampered Worker bytes already staged and present in the worktree.
    _ = worker.write_bytes(b"staged tampered Worker JAR")
    assert _run_git(repository, "add", str(worker_relative)).returncode == 0
    assert (
        _run_git(
            repository,
            "diff",
            "--cached",
            "--exit-code",
            "HEAD",
            "--",
            str(worker_relative),
        ).returncode
        == 1
    )

    acceptance = (_PROJECT_ROOT / "docs/windows-x64-release-acceptance.md").read_text(
        encoding="utf-8"
    )
    assert "git restore --source=HEAD --worktree --staged -- $workerJar" in acceptance

    # The documented restore must replace both dirty locations with HEAD's bytes.
    restore = _run_git(
        repository,
        "restore",
        "--source=HEAD",
        "--worktree",
        "--staged",
        "--",
        str(worker_relative),
    )

    assert restore.returncode == 0
    assert worker.read_bytes() == committed_worker
    assert (
        _run_git(
            repository,
            "diff",
            "--cached",
            "--exit-code",
            "HEAD",
            "--",
            str(worker_relative),
        ).returncode
        == 0
    )
    assert (
        _run_git(
            repository,
            "diff",
            "--exit-code",
            "HEAD",
            "--",
            str(worker_relative),
        ).returncode
        == 0
    )
