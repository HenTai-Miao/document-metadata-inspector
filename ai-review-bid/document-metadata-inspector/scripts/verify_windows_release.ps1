param(
    [Parameter(Mandatory = $true)]
    [string]$ReleaseDirectory,

    [ValidateSet("Portable", "All")]
    [string]$Mode = "Portable"
)

$ErrorActionPreference = "Stop"
$release = (Resolve-Path -LiteralPath $ReleaseDirectory).Path

function Get-ManifestKind([string]$Filename) {
    if ($Filename -ceq "BUILD-INFO.json") {
        return "build_info"
    }
    if ($Filename -ceq "THIRD_PARTY_NOTICES.md") {
        return "notices"
    }
    if ($Filename -cmatch '^DocumentMetadataInspector-.+-win-x64-Setup\.exe$') {
        return "setup"
    }
    if ($Filename -cmatch '^DocumentMetadataInspector-.+-win-x64-Portable\.zip$') {
        return "portable"
    }
    if ($Filename -cmatch '^DocumentMetadataInspector-.+-win-x64-CLI\.zip$') {
        return "cli"
    }
    throw "SHA256SUMS contains an unexpected filename"
}

function Test-NonEmptyString([object]$Value) {
    return $Value -is [string] -and -not [string]::IsNullOrWhiteSpace($Value)
}

function Test-TopLevelJsonObject([string]$JsonText) {
    $trimmed = $JsonText.TrimStart()
    return $trimmed.Length -gt 0 -and $trimmed.StartsWith("{")
}

function Test-CaptureLimitExceeded {
    param(
        [string]$StdoutPath,
        [string]$StderrPath,
        [long]$MaxCaptureBytes
    )

    $stdoutLength = 0L
    if (Test-Path -LiteralPath $StdoutPath -PathType Leaf -ErrorAction Stop) {
        $stdoutLength = (
            Get-Item -LiteralPath $StdoutPath -ErrorAction Stop
        ).Length
    }
    $stderrLength = 0L
    if (Test-Path -LiteralPath $StderrPath -PathType Leaf -ErrorAction Stop) {
        $stderrLength = (
            Get-Item -LiteralPath $StderrPath -ErrorAction Stop
        ).Length
    }
    return (
        $stdoutLength -gt $MaxCaptureBytes -or
        $stderrLength -gt $MaxCaptureBytes
    )
}

function Initialize-ProcessExitCodeInterop {
    if ($null -ne ("DocmetaVerifier.NativeProcessMethods" -as [type])) {
        return
    }
    $typeDefinition = @'
using System;
using System.Runtime.InteropServices;

namespace DocmetaVerifier {
    public static class NativeProcessMethods {
        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool GetExitCodeProcess(
            IntPtr processHandle,
            out uint exitCode
        );
    }
}
'@
    try {
        $null = Add-Type -TypeDefinition $typeDefinition -Language CSharp `
            -ErrorAction Stop
    }
    catch {
        throw "Native process exit-code support could not be initialized"
    }
}

function Get-NativeProcessExitCode {
    param(
        [IntPtr]$ProcessHandle,
        [string]$Description
    )

    $exitCode = [uint32]0
    try {
        $succeeded = [DocmetaVerifier.NativeProcessMethods]::GetExitCodeProcess(
            $ProcessHandle,
            [ref]$exitCode
        )
    }
    catch {
        throw "$Description exit code could not be read"
    }
    if (-not $succeeded) {
        $errorCode = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
        throw "$Description exit code could not be read (Windows error $errorCode)"
    }
    return $exitCode
}

function Get-TrackedProcessHandle {
    param(
        [System.Diagnostics.Process]$Process,
        [string]$Description
    )

    # Start-Process does not retain a launch handle on Windows PowerShell 5.1.
    # A process that wins this race cannot be distinguished safely from PID reuse.
    if ($Process.HasExited) {
        throw "$Description exited before its process handle could be captured"
    }
    try {
        $processHandle = $Process.Handle
    }
    catch {
        throw "$Description process handle could not be captured"
    }
    if ($processHandle -eq [IntPtr]::Zero) {
        throw "$Description returned an invalid process handle"
    }
    $initialExitCode = Get-NativeProcessExitCode $processHandle $Description
    if ($initialExitCode -ne 259) {
        throw "$Description was not active when its process handle was captured"
    }
    return $processHandle
}

function Get-TrackedProcessExitCode {
    param(
        [System.Diagnostics.Process]$Process,
        [IntPtr]$ProcessHandle,
        [string]$Description
    )

    if (-not $Process.HasExited) {
        throw "$Description remained active after its wait completed"
    }
    return Get-NativeProcessExitCode $ProcessHandle $Description
}

function Resolve-SystemTaskkill {
    $systemDirectory = [Environment]::GetFolderPath(
        [Environment+SpecialFolder]::System
    )
    if ([string]::IsNullOrWhiteSpace($systemDirectory)) {
        throw "The Windows system directory could not be resolved"
    }
    $taskkillPath = Join-Path $systemDirectory "taskkill.exe"
    if (-not (
        Test-Path -LiteralPath $taskkillPath -PathType Leaf -ErrorAction Stop
    )) {
        throw "The Windows system taskkill.exe is missing"
    }
    return (Resolve-Path -LiteralPath $taskkillPath -ErrorAction Stop).Path
}

function Complete-TaskkillAfterTrackingFailure {
    param(
        [System.Diagnostics.Process]$Process,
        [System.Diagnostics.Process]$Taskkill,
        [string]$TaskkillPath,
        [string]$Description,
        [string]$ProcessRoot
    )

    $cleanupFailed = $false
    if ($null -ne $Taskkill) {
        try {
            if (-not $Taskkill.HasExited -and -not $Taskkill.WaitForExit(10000)) {
                try {
                    Stop-Process -Id $Taskkill.Id -Force -ErrorAction Stop
                }
                catch {
                    $cleanupFailed = $true
                }
                if (-not $Taskkill.HasExited -and -not $Taskkill.WaitForExit(5000)) {
                    $cleanupFailed = $true
                }
            }
        }
        catch {
            $cleanupFailed = $true
        }
    }

    $rootExited = $false
    try {
        $rootExited = $Process.HasExited -or $Process.WaitForExit(5000)
    }
    catch {
        $cleanupFailed = $true
    }
    $fallbackStdout = Join-Path $ProcessRoot "taskkill-fallback-stdout.txt"
    $fallbackStderr = Join-Path $ProcessRoot "taskkill-fallback-stderr.txt"
    $fallback = $null
    if (-not $rootExited) {
        try {
            $fallback = Start-Process -FilePath $TaskkillPath `
                -ArgumentList "/PID", $Process.Id.ToString(), "/T", "/F" `
                -RedirectStandardOutput $fallbackStdout `
                -RedirectStandardError $fallbackStderr -PassThru
        }
        catch {
            $cleanupFailed = $true
        }
        if ($null -ne $fallback) {
            try {
                if (-not $fallback.WaitForExit(10000)) {
                    $cleanupFailed = $true
                    try {
                        Stop-Process -Id $fallback.Id -Force -ErrorAction Stop
                    }
                    catch {
                        $cleanupFailed = $true
                    }
                    if (
                        -not $fallback.HasExited -and
                        -not $fallback.WaitForExit(5000)
                    ) {
                        $cleanupFailed = $true
                    }
                }
            }
            catch {
                $cleanupFailed = $true
            }
            finally {
                $fallback.Dispose()
            }
        }
        try {
            $rootExited = $Process.HasExited -or $Process.WaitForExit(5000)
        }
        catch {
            $cleanupFailed = $true
        }
    }

    if (-not $rootExited) {
        $cleanupFailed = $true
        try {
            Stop-Process -Id $Process.Id -Force -ErrorAction Stop
            $rootExited = $Process.WaitForExit(5000)
        }
        catch {
            $cleanupFailed = $true
        }
    }
    if (-not $rootExited -or $cleanupFailed) {
        throw "$Description process-tree cleanup did not converge"
    }
}

function Stop-ProcessTreeWithTaskkill {
    param(
        [System.Diagnostics.Process]$Process,
        [string]$Description,
        [string]$ProcessRoot
    )

    $taskkillPath = Resolve-SystemTaskkill
    $taskkillStdout = Join-Path $ProcessRoot "taskkill-stdout.txt"
    $taskkillStderr = Join-Path $ProcessRoot "taskkill-stderr.txt"
    Initialize-ProcessExitCodeInterop
    $taskkill = $null
    try {
        $taskkill = Start-Process -FilePath $taskkillPath `
            -ArgumentList "/PID", $Process.Id.ToString(), "/T", "/F" `
            -RedirectStandardOutput $taskkillStdout `
            -RedirectStandardError $taskkillStderr -PassThru
        $taskkillHandle = Get-TrackedProcessHandle $taskkill $Description
        if (-not $taskkill.WaitForExit(10000)) {
            Stop-Process -Id $taskkill.Id -Force -ErrorAction Stop
            if (-not $taskkill.WaitForExit(5000)) {
                throw "$Description taskkill did not stop after its timeout"
            }
            throw "$Description taskkill timed out"
        }
        $taskkillExitCode = Get-TrackedProcessExitCode `
            $taskkill $taskkillHandle $Description
        if ($taskkillExitCode -ne 0) {
            throw "$Description taskkill returned exit code $taskkillExitCode"
        }
        if (-not $Process.WaitForExit(5000)) {
            throw "$Description root process remained after taskkill succeeded"
        }
    }
    catch {
        Complete-TaskkillAfterTrackingFailure `
            $Process $taskkill $taskkillPath $Description $ProcessRoot
        throw "$Description process-tree terminator exit could not be verified"
    }
    finally {
        if ($null -ne $taskkill) {
            $taskkill.Dispose()
        }
    }
}

function Invoke-BoundedProcess {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,

        [string[]]$ArgumentList = @(),

        [Parameter(Mandatory = $true)]
        [ValidateRange(1, 3600)]
        [int]$TimeoutSeconds,

        [Parameter(Mandatory = $true)]
        [string]$Description,

        [hashtable]$StartState = $null
    )

    if ($null -ne $StartState -and (
        -not $StartState.ContainsKey("Started") -or
        $StartState["Started"] -isnot [bool] -or
        $StartState["Started"]
    )) {
        throw "StartState must contain boolean false Started"
    }

    Initialize-ProcessExitCodeInterop
    $processRoot = Join-Path ([System.IO.Path]::GetTempPath()) (
        "docmeta verifier process " + [guid]::NewGuid().ToString("N")
    )
    $stdoutPath = Join-Path $processRoot "stdout.txt"
    $stderrPath = Join-Path $processRoot "stderr.txt"
    $maxCaptureBytes = 4MB
    $processRootCreated = $false
    $process = $null
    try {
        New-Item -ItemType Directory -Path $processRoot | Out-Null
        $processRootCreated = $true
        try {
            $process = Start-Process -FilePath $FilePath `
                -ArgumentList $ArgumentList `
                -RedirectStandardOutput $stdoutPath `
                -RedirectStandardError $stderrPath -PassThru
        }
        catch {
            throw "$Description could not be started"
        }
        if ($null -ne $StartState) {
            $StartState["Started"] = $true
        }
        try {
            $processHandle = Get-TrackedProcessHandle $process $Description
        }
        catch {
            if (-not $process.HasExited) {
                Stop-ProcessTreeWithTaskkill $process $Description $processRoot
            }
            throw
        }
        $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
        while (-not $process.HasExited) {
            if (Test-CaptureLimitExceeded $stdoutPath $stderrPath $maxCaptureBytes) {
                if ($process.HasExited) { break }
                Stop-ProcessTreeWithTaskkill $process $Description $processRoot
                throw "$Description produced excessive output"
            }
            if ([DateTime]::UtcNow -ge $deadline) {
                Stop-ProcessTreeWithTaskkill $process $Description $processRoot
                throw "$Description timed out"
            }
            Start-Sleep -Milliseconds 100
            $process.Refresh()
        }
        if (-not $process.WaitForExit(5000)) {
            Stop-ProcessTreeWithTaskkill $process $Description $processRoot
            throw "$Description root process did not close its handles"
        }
        if (Test-CaptureLimitExceeded $stdoutPath $stderrPath $maxCaptureBytes) {
            throw "$Description produced excessive output"
        }
        $exitCode = Get-TrackedProcessExitCode `
            $process $processHandle $Description
        if ($exitCode -ne 0) {
            throw "$Description returned exit code $exitCode"
        }
        return Get-Content -LiteralPath $stdoutPath -Raw -ErrorAction Stop
    }
    finally {
        if ($null -ne $process) {
            $process.Dispose()
        }
        if ($processRootCreated -and (
            Test-Path -LiteralPath $processRoot -ErrorAction Stop
        )) {
            Remove-Item -LiteralPath $processRoot -Recurse -Force
        }
    }
}

function Test-CleanInstallRoot([string]$InstallRoot) {
    if (Test-Path -LiteralPath $InstallRoot -ErrorAction Stop) {
        if (-not (
            Test-Path -LiteralPath $InstallRoot -PathType Container `
                -ErrorAction Stop
        )) {
            throw "The installation path is occupied by a non-directory"
        }
        throw "All mode requires a clean test account without an existing installation"
    }
}

function Get-InstalledCores([string]$InstallRoot) {
    if (-not (Test-Path -LiteralPath $InstallRoot -ErrorAction Stop)) {
        return @()
    }
    if (-not (
        Test-Path -LiteralPath $InstallRoot -PathType Container -ErrorAction Stop
    )) {
        throw "The installation path is occupied by a non-directory"
    }
    return @(
        Get-ChildItem -LiteralPath $InstallRoot -Recurse -File `
            -Filter "docmeta.exe" -ErrorAction Stop |
            Where-Object {
                $_.FullName -like "*app-*resources*docmeta-runtime*docmeta.exe"
            }
    )
}

function Get-RemainingApps([string]$InstallRoot) {
    if (-not (Test-Path -LiteralPath $InstallRoot -ErrorAction Stop)) {
        return @()
    }
    if (-not (
        Test-Path -LiteralPath $InstallRoot -PathType Container -ErrorAction Stop
    )) {
        throw "The installation path is occupied by a non-directory"
    }
    return @(
        Get-ChildItem -LiteralPath $InstallRoot -Directory -Filter "app-*" `
            -ErrorAction Stop
    )
}

function Get-SafeRegularFileDigest {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$Description
    )

    try {
        $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    }
    catch {
        throw "$Description could not be inspected"
    }
    if (
        $item -isnot [System.IO.FileInfo] -or
        (
            $item.Attributes -band [System.IO.FileAttributes]::ReparsePoint
        ) -ne 0
    ) {
        throw "$Description is not a safe regular file"
    }
    try {
        return (
            Get-FileHash -Algorithm SHA256 -LiteralPath $item.FullName
        ).Hash.ToLowerInvariant()
    }
    catch {
        throw "$Description could not be hashed"
    }
}

function Test-OwnedSquirrelUninstallResidue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$InstallRoot,

        [Parameter(Mandatory = $true)]
        [string]$AppDirectoryName,

        [Parameter(Mandatory = $true)]
        [System.Collections.Generic.Dictionary[string, string]]
        $ExpectedFileDigests
    )

    if (
        [System.IO.Path]::GetFileName($AppDirectoryName) -cne
            $AppDirectoryName -or
        $AppDirectoryName -cnotmatch '^app-[A-Za-z0-9][A-Za-z0-9.+-]*$'
    ) {
        throw "The installed application directory name is invalid"
    }

    $expectedUpdate = "Update.exe"
    $expectedSquirrel = Join-Path $AppDirectoryName "squirrel.exe"
    $expectedSnapshot = Join-Path $AppDirectoryName "v8_context_snapshot.bin"
    $allowedExpectedPaths = [System.Collections.Generic.HashSet[string]]::new(
        [System.StringComparer]::OrdinalIgnoreCase
    )
    foreach ($relativePath in @(
        $expectedUpdate,
        $expectedSquirrel,
        $expectedSnapshot
    )) {
        $null = $allowedExpectedPaths.Add($relativePath)
    }
    if (-not $ExpectedFileDigests.ContainsKey($expectedUpdate)) {
        throw "The Squirrel uninstall residue contract is incomplete"
    }
    foreach ($entry in $ExpectedFileDigests.GetEnumerator()) {
        if (
            -not $allowedExpectedPaths.Contains($entry.Key) -or
            $entry.Value -cnotmatch '^[0-9a-f]{64}$'
        ) {
            throw "The Squirrel uninstall residue contract is invalid"
        }
    }

    $rootItem = Get-Item -LiteralPath $InstallRoot -Force -ErrorAction Stop
    if (
        $rootItem -isnot [System.IO.DirectoryInfo] -or
        (
            $rootItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint
        ) -ne 0
    ) {
        throw "The Squirrel uninstall residue root is unsafe"
    }

    $rootEntries = @(
        Get-ChildItem -LiteralPath $InstallRoot -Force -ErrorAction Stop
    )
    $deadEntries = @($rootEntries | Where-Object { $_.Name -ceq ".dead" })
    if ($deadEntries.Count -ne 1) {
        throw "Squirrel uninstall did not leave its completion marker"
    }
    $deadMarker = Join-Path $InstallRoot ".dead"
    $deadItem = $deadEntries[0]
    if (
        $deadItem -isnot [System.IO.FileInfo] -or
        (
            $deadItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint
        ) -ne 0
    ) {
        throw "The Squirrel uninstall completion marker is unsafe"
    }
    $deadStream = $null
    try {
        $deadStream = [System.IO.File]::Open(
            $deadMarker,
            [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::Read,
            [System.IO.FileShare]::Read
        )
    }
    catch {
        throw "The Squirrel uninstall completion marker could not be opened"
    }
    try {
        $deadValue = $deadStream.ReadByte()
        if ($deadStream.Length -ne 1 -or $deadValue -ne 0x20) {
            throw "The Squirrel uninstall completion marker is invalid"
        }
    }
    finally {
        $deadStream.Dispose()
    }

    foreach ($item in $rootEntries) {
        if ($item.Name -ceq ".dead") {
            continue
        }
        if (
            (
                $item.Attributes -band [System.IO.FileAttributes]::ReparsePoint
            ) -ne 0
        ) {
            throw "Squirrel uninstall left an unsafe reparse point"
        }
        if ($item.Name -ceq $expectedUpdate) {
            if ($item -isnot [System.IO.FileInfo]) {
                throw "Squirrel uninstall left an invalid Update.exe"
            }
            $relativePath = $expectedUpdate
            if (-not $ExpectedFileDigests.ContainsKey($relativePath)) {
                throw "Squirrel uninstall left an unexpected file"
            }
            $digest = Get-SafeRegularFileDigest `
                $item.FullName "Squirrel Update.exe residue"
            if ($digest -cne $ExpectedFileDigests[$relativePath]) {
                throw "Squirrel uninstall changed a retained cleanup file"
            }
            continue
        }
        if ($item.Name -cne $AppDirectoryName) {
            throw "Squirrel uninstall left an unexpected root entry"
        }
        if ($item -isnot [System.IO.DirectoryInfo]) {
            throw "Squirrel uninstall left an invalid application directory"
        }
        $appEntries = @(
            Get-ChildItem -LiteralPath $item.FullName -Force -ErrorAction Stop
        )
        foreach ($appItem in $appEntries) {
            if (
                $appItem -isnot [System.IO.FileInfo] -or
                (
                    $appItem.Attributes -band
                        [System.IO.FileAttributes]::ReparsePoint
                ) -ne 0
            ) {
                throw "Squirrel uninstall left an unsafe application entry"
            }
            $relativePath = Join-Path $AppDirectoryName $appItem.Name
            if (-not $ExpectedFileDigests.ContainsKey($relativePath)) {
                throw "Squirrel uninstall left an unexpected application file"
            }
            $digest = Get-SafeRegularFileDigest `
                $appItem.FullName "Squirrel application residue"
            if ($digest -cne $ExpectedFileDigests[$relativePath]) {
                throw "Squirrel uninstall changed a retained application file"
            }
        }
    }
}

function Remove-OwnedSquirrelUninstallResidue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$InstallRoot,

        [Parameter(Mandatory = $true)]
        [string]$AppDirectoryName,

        [Parameter(Mandatory = $true)]
        [System.Collections.Generic.Dictionary[string, string]]
        $ExpectedFileDigests
    )

    try {
        if (-not (Test-Path -LiteralPath $InstallRoot -ErrorAction Stop)) {
            return
        }
        Test-OwnedSquirrelUninstallResidue `
            $InstallRoot $AppDirectoryName $ExpectedFileDigests

        $cleanupRoot = (
            "$InstallRoot.verifier-cleanup-" +
            [guid]::NewGuid().ToString("N")
        )
        if (Test-Path -LiteralPath $cleanupRoot -ErrorAction Stop) {
            throw "The Squirrel uninstall cleanup path is already occupied"
        }
        [System.IO.Directory]::Move($InstallRoot, $cleanupRoot)
        if (Test-Path -LiteralPath $InstallRoot -ErrorAction Stop) {
            throw "The Squirrel uninstall residue could not be isolated"
        }
        Test-OwnedSquirrelUninstallResidue `
            $cleanupRoot $AppDirectoryName $ExpectedFileDigests

        foreach ($relativePath in $ExpectedFileDigests.Keys) {
            Test-OwnedSquirrelUninstallResidue `
                $cleanupRoot $AppDirectoryName $ExpectedFileDigests
            $candidatePath = Join-Path $cleanupRoot $relativePath
            if (Test-Path -LiteralPath $candidatePath -ErrorAction Stop) {
                $candidateDigest = Get-SafeRegularFileDigest `
                    $candidatePath "Squirrel cleanup candidate"
                if ($candidateDigest -cne $ExpectedFileDigests[$relativePath]) {
                    throw "A Squirrel cleanup candidate changed before removal"
                }
                [System.IO.File]::Delete($candidatePath)
                if (Test-Path -LiteralPath $candidatePath -ErrorAction Stop) {
                    throw "A Squirrel cleanup candidate could not be removed"
                }
            }
        }

        Test-OwnedSquirrelUninstallResidue `
            $cleanupRoot $AppDirectoryName $ExpectedFileDigests
        $appRoot = Join-Path $cleanupRoot $AppDirectoryName
        if (Test-Path -LiteralPath $appRoot -ErrorAction Stop) {
            $appItem = Get-Item -LiteralPath $appRoot -Force -ErrorAction Stop
            if (
                $appItem -isnot [System.IO.DirectoryInfo] -or
                (
                    $appItem.Attributes -band
                        [System.IO.FileAttributes]::ReparsePoint
                ) -ne 0 -or
                @(
                    Get-ChildItem -LiteralPath $appRoot -Force -ErrorAction Stop
                ).Count -ne 0
            ) {
                throw "The isolated Squirrel application directory is unsafe"
            }
            [System.IO.Directory]::Delete($appRoot, $false)
        }

        Test-OwnedSquirrelUninstallResidue `
            $cleanupRoot $AppDirectoryName $ExpectedFileDigests
        $deadMarker = Join-Path $cleanupRoot ".dead"
        [System.IO.File]::Delete($deadMarker)
        $rootItem = Get-Item -LiteralPath $cleanupRoot -Force -ErrorAction Stop
        if (
            $rootItem -isnot [System.IO.DirectoryInfo] -or
            (
                $rootItem.Attributes -band
                    [System.IO.FileAttributes]::ReparsePoint
            ) -ne 0 -or
            (Test-Path -LiteralPath $deadMarker -ErrorAction Stop) -or
            @(
                Get-ChildItem -LiteralPath $cleanupRoot -Force -ErrorAction Stop
            ).Count -ne 0
        ) {
            throw "The isolated Squirrel uninstall residue is not empty"
        }
        [System.IO.Directory]::Delete($cleanupRoot, $false)
        if (
            (Test-Path -LiteralPath $cleanupRoot -ErrorAction Stop) -or
            (Test-Path -LiteralPath $InstallRoot -ErrorAction Stop)
        ) {
            throw "The Squirrel uninstall residue could not be removed"
        }
    }
    catch {
        throw "Owned Squirrel uninstall residue cleanup failed"
    }
}

function Test-Core([string]$CorePath, [string]$ExpectedDigest) {
    $digest = (Get-FileHash -Algorithm SHA256 -LiteralPath $CorePath).Hash.ToLowerInvariant()
    if ($digest -cne $ExpectedDigest) {
        throw "Packaged core hash does not match BUILD-INFO.json"
    }
    $jsonText = Invoke-BoundedProcess -FilePath $CorePath -ArgumentList "verify" `
        -TimeoutSeconds 60 -Description "Frozen core verification"
    if (-not (Test-TopLevelJsonObject $jsonText)) {
        throw "Frozen core verification did not return one JSON object"
    }
    try {
        $report = ConvertFrom-Json -InputObject $jsonText
    }
    catch {
        throw "Frozen core verification did not return valid JSON"
    }
    if ($report -isnot [pscustomobject]) {
        throw "Frozen core verification did not return one JSON object"
    }
    $requiredReportKeys = @("schema_version", "passed", "checks")
    $actualReportKeys = @($report.PSObject.Properties.Name)
    if ($actualReportKeys.Count -ne $requiredReportKeys.Count) {
        throw "Frozen core verification returned an invalid report contract"
    }
    foreach ($key in $requiredReportKeys) {
        if ($actualReportKeys -cnotcontains $key) {
            throw "Frozen core verification returned an invalid report contract"
        }
    }
    if (
        $report.schema_version -isnot [string] -or
        $report.schema_version -cne "1.0"
    ) {
        throw "Frozen core verification returned an invalid schema version"
    }
    if (-not ($report.passed -is [bool]) -or $report.passed -ne $true) {
        throw "Frozen core verification did not pass"
    }
    $checks = @($report.checks)
    if ($checks.Count -ne 6) {
        throw "Frozen core verification did not return six passing checks"
    }
    $expectedCheckNames = [System.Collections.Generic.HashSet[string]]::new(
        [System.StringComparer]::Ordinal
    )
    foreach ($name in @(
        "component:apache-tika",
        "component:exiftool",
        "sample:pdf",
        "sample:word",
        "sample:excel",
        "sample:source-integrity"
    )) {
        $null = $expectedCheckNames.Add($name)
    }
    $seenCheckNames = [System.Collections.Generic.HashSet[string]]::new(
        [System.StringComparer]::Ordinal
    )
    $requiredCheckKeys = @("name", "status", "message")
    foreach ($check in $checks) {
        if (-not ($check -is [pscustomobject])) {
            throw "Frozen core verification contains a non-object check"
        }
        $actualCheckKeys = @($check.PSObject.Properties.Name)
        if ($actualCheckKeys.Count -ne $requiredCheckKeys.Count) {
            throw "Frozen core verification contains an invalid check contract"
        }
        foreach ($key in $requiredCheckKeys) {
            if ($actualCheckKeys -cnotcontains $key) {
                throw "Frozen core verification contains an invalid check contract"
            }
        }
        if (-not ($check.name -is [string])) {
            throw "Frozen core verification contains an invalid check name"
        }
        if (-not ($expectedCheckNames.Contains($check.name))) {
            throw "Frozen core verification contains an unexpected check"
        }
        if (-not ($seenCheckNames.Add($check.name))) {
            throw "Frozen core verification contains a duplicate check"
        }
        if (-not ($check.status -is [string]) -or $check.status -cne "pass") {
            throw "Frozen core verification contains a failed check"
        }
        if (-not ($check.message -is [string])) {
            throw "Frozen core verification contains an invalid check message"
        }
    }
    if (-not ($seenCheckNames.SetEquals($expectedCheckNames))) {
        throw "Frozen core verification is missing an expected check"
    }
}

$manifestLines = @(
    Get-Content -LiteralPath (Join-Path $release "SHA256SUMS") |
        Where-Object { $_.Length -gt 0 }
)
if ($manifestLines.Count -ne 5) {
    throw "SHA256SUMS must contain exactly five records"
}
$manifest = [System.Collections.Generic.Dictionary[string, object]]::new(
    [System.StringComparer]::OrdinalIgnoreCase
)
foreach ($line in $manifestLines) {
    if ($line -cnotmatch '^([0-9a-f]{64})  ([^\\/]+)$') {
        throw "SHA256SUMS contains an invalid record"
    }
    $expected = $Matches[1]
    $filename = $Matches[2]
    if ($manifest.ContainsKey($filename)) {
        throw "SHA256SUMS contains a duplicate filename"
    }
    $kind = Get-ManifestKind $filename
    $path = Join-Path $release $filename
    $manifest.Add(
        $filename,
        [pscustomobject]@{
            Name = $filename
            Path = $path
            ExpectedHash = $expected
            Kind = $kind
        }
    )
}

$setupRecords = @($manifest.Values | Where-Object { $_.Kind -ceq "setup" })
$portableRecords = @($manifest.Values | Where-Object { $_.Kind -ceq "portable" })
$cliRecords = @($manifest.Values | Where-Object { $_.Kind -ceq "cli" })
$buildInfoRecords = @($manifest.Values | Where-Object { $_.Kind -ceq "build_info" })
$noticeRecords = @($manifest.Values | Where-Object { $_.Kind -ceq "notices" })
if (
    $manifest.Count -ne 5 -or
    $setupRecords.Count -ne 1 -or
    $portableRecords.Count -ne 1 -or
    $cliRecords.Count -ne 1 -or
    $buildInfoRecords.Count -ne 1 -or
    $noticeRecords.Count -ne 1
) {
    throw "SHA256SUMS does not contain the exact release file set"
}

foreach ($record in $manifest.Values) {
    if (-not (
        Test-Path -LiteralPath $record.Path -PathType Leaf -ErrorAction Stop
    )) {
        throw "SHA256SUMS references a missing file"
    }
    $actual = (
        Get-FileHash -Algorithm SHA256 -LiteralPath $record.Path
    ).Hash.ToLowerInvariant()
    if ($actual -cne $record.ExpectedHash) {
        throw "Release file hash does not match SHA256SUMS"
    }
}

$setupRecord = $setupRecords[0]
$portableRecord = $portableRecords[0]
$cliRecord = $cliRecords[0]
$buildInfoRecord = $buildInfoRecords[0]
$setup = $setupRecord.Path
$portable = $portableRecord.Path

try {
    $buildInfoText = Get-Content -LiteralPath $buildInfoRecord.Path -Raw `
        -ErrorAction Stop
}
catch {
    throw "BUILD-INFO.json is not valid JSON"
}
if (-not (Test-TopLevelJsonObject $buildInfoText)) {
    throw "BUILD-INFO.json must contain exactly one object"
}
try {
    $buildInfo = ConvertFrom-Json -InputObject $buildInfoText
}
catch {
    throw "BUILD-INFO.json is not valid JSON"
}
if ($buildInfo -isnot [pscustomobject]) {
    throw "BUILD-INFO.json must contain exactly one object"
}

$requiredBuildInfoKeys = @(
    "schema_version",
    "product_version",
    "git_commit",
    "target_platform",
    "core_sha256",
    "built_at_utc",
    "versions"
)
$actualBuildInfoKeys = @($buildInfo.PSObject.Properties.Name)
if ($actualBuildInfoKeys.Count -ne $requiredBuildInfoKeys.Count) {
    throw "BUILD-INFO.json contains an invalid top-level contract"
}
foreach ($key in $requiredBuildInfoKeys) {
    if ($actualBuildInfoKeys -cnotcontains $key) {
        throw "BUILD-INFO.json contains an invalid top-level contract"
    }
}

if (
    $buildInfo.schema_version -isnot [string] -or
    $buildInfo.schema_version -cne "1"
) {
    throw "BUILD-INFO.json has an unsupported schema version"
}
if (-not (Test-NonEmptyString $buildInfo.product_version)) {
    throw "BUILD-INFO.json has an invalid product version"
}
if (
    $buildInfo.git_commit -isnot [string] -or
    $buildInfo.git_commit -cnotmatch '^[0-9a-f]{40}$'
) {
    throw "BUILD-INFO.json has an invalid Git commit"
}
if (
    $buildInfo.target_platform -isnot [string] -or
    $buildInfo.target_platform -cne "windows-x86_64"
) {
    throw "BUILD-INFO.json has an invalid target platform"
}
if (
    $buildInfo.core_sha256 -isnot [string] -or
    $buildInfo.core_sha256 -cnotmatch '^[0-9a-f]{64}$'
) {
    throw "BUILD-INFO.json has an invalid core hash"
}
if ($buildInfo.built_at_utc -isnot [string]) {
    throw "BUILD-INFO.json has an invalid UTC build time"
}
$parsedBuildTime = [datetime]::MinValue
$timestampStyles = [Globalization.DateTimeStyles]::AssumeUniversal -bor `
    [Globalization.DateTimeStyles]::AdjustToUniversal
$timestampValid = [datetime]::TryParseExact(
    $buildInfo.built_at_utc,
    "yyyy-MM-ddTHH:mm:ssZ",
    [Globalization.CultureInfo]::InvariantCulture,
    $timestampStyles,
    [ref]$parsedBuildTime
)
if (-not $timestampValid) {
    throw "BUILD-INFO.json has an invalid UTC build time"
}
if ($buildInfo.versions -isnot [pscustomobject]) {
    throw "BUILD-INFO.json has an invalid versions contract"
}
$requiredVersionKeys = @(
    "python",
    "java_runtime",
    "exiftool",
    "electron",
    "electron_forge"
)
$actualVersionKeys = @($buildInfo.versions.PSObject.Properties.Name)
if ($actualVersionKeys.Count -ne $requiredVersionKeys.Count) {
    throw "BUILD-INFO.json has an invalid versions contract"
}
foreach ($key in $requiredVersionKeys) {
    if (
        $actualVersionKeys -cnotcontains $key -or
        -not (Test-NonEmptyString $buildInfo.versions.$key)
    ) {
        throw "BUILD-INFO.json has an invalid versions contract"
    }
}

$expectedSetupName = "DocumentMetadataInspector-$($buildInfo.product_version)-win-x64-Setup.exe"
$expectedPortableName = "DocumentMetadataInspector-$($buildInfo.product_version)-win-x64-Portable.zip"
$expectedCliName = "DocumentMetadataInspector-$($buildInfo.product_version)-win-x64-CLI.zip"
if (
    $setupRecord.Name -cne $expectedSetupName -or
    $portableRecord.Name -cne $expectedPortableName -or
    $cliRecord.Name -cne $expectedCliName
) {
    throw "Release artifact filenames do not match BUILD-INFO.json product_version"
}

$portableTestPrefix = -join @(
    [char]0x6587
    [char]0x6863
    [char]0x5143
    [char]0x6570
    [char]0x636E
    [char]0x6838
    [char]0x9A8C
)
$testRoot = Join-Path ([System.IO.Path]::GetTempPath()) (
    $portableTestPrefix + " portable " + [guid]::NewGuid().ToString("N")
)
$movedRoot = "$testRoot moved"

try {
    New-Item -ItemType Directory -Path $testRoot | Out-Null
    Expand-Archive -LiteralPath $portable -DestinationPath $testRoot
    $portableCores = @(
        Get-ChildItem -LiteralPath $testRoot -Recurse -File -Filter "docmeta.exe" |
            Where-Object { $_.FullName -like "*resources*docmeta-runtime*docmeta.exe" }
    )
    if ($portableCores.Count -ne 1) {
        throw "Portable archive must contain exactly one packaged core"
    }
    Test-Core $portableCores[0].FullName $buildInfo.core_sha256
    Move-Item -LiteralPath $testRoot -Destination $movedRoot
    $movedCore = @(
        Get-ChildItem -LiteralPath $movedRoot -Recurse -File -Filter "docmeta.exe" |
            Where-Object { $_.FullName -like "*resources*docmeta-runtime*docmeta.exe" }
    )
    if ($movedCore.Count -ne 1) {
        throw "Moved portable application must contain exactly one packaged core"
    }
    Test-Core $movedCore[0].FullName $buildInfo.core_sha256
}
finally {
    if (Test-Path -LiteralPath $movedRoot -ErrorAction Stop) {
        Remove-Item -LiteralPath $movedRoot -Recurse -Force
    }
    if (Test-Path -LiteralPath $testRoot -ErrorAction Stop) {
        Remove-Item -LiteralPath $testRoot -Recurse -Force
    }
}

if ($Mode -eq "All") {
    $installRoot = Join-Path $env:LOCALAPPDATA "DocumentMetadataInspector"
    Test-CleanInstallRoot $installRoot
    $canaryRoot = Join-Path ([System.IO.Path]::GetTempPath()) (
        "docmeta uninstall canary " + [guid]::NewGuid().ToString("N")
    )
    $canary = Join-Path $canaryRoot "preserve.txt"
    $canaryRootCreated = $false
    $canaryCreated = $false
    $setupState = @{ Started = $false }
    $residueAppDirectoryName = $null
    $expectedResidueDigests = `
        [System.Collections.Generic.Dictionary[string, string]]::new(
            [System.StringComparer]::OrdinalIgnoreCase
        )
    $residueContractReady = $false
    try {
        New-Item -ItemType Directory -Path $canaryRoot | Out-Null
        $canaryRootCreated = $true
        Set-Content -LiteralPath $canary -Value "preserve" -ErrorAction Stop
        $canaryCreated = $true
        Test-CleanInstallRoot $installRoot
        try {
            $null = Invoke-BoundedProcess -FilePath $setup `
                -ArgumentList "--silent" -TimeoutSeconds 120 `
                -Description "Squirrel installer" -StartState $setupState
            $installDeadline = [DateTime]::UtcNow.AddSeconds(60)
            do {
                $installedCores = @(Get-InstalledCores $installRoot)
                if ($installedCores.Count -eq 1) { break }
                Start-Sleep -Milliseconds 500
            } while ([DateTime]::UtcNow -lt $installDeadline)
            $installedApps = @(Get-RemainingApps $installRoot)
            if ($installedApps.Count -ne 1) {
                throw "Installed application must contain exactly one version directory"
            }
            if (
                (
                    $installedApps[0].Attributes -band
                        [System.IO.FileAttributes]::ReparsePoint
                ) -ne 0
            ) {
                throw "The installed application directory is unsafe"
            }
            $residueAppDirectoryName = $installedApps[0].Name
            $residueCandidates = @(
                [pscustomobject]@{
                    RelativePath = "Update.exe"
                    Path = Join-Path $installRoot "Update.exe"
                    Required = $true
                },
                [pscustomobject]@{
                    RelativePath = Join-Path `
                        $residueAppDirectoryName "squirrel.exe"
                    Path = Join-Path `
                        $installedApps[0].FullName "squirrel.exe"
                    Required = $false
                },
                [pscustomobject]@{
                    RelativePath = Join-Path `
                        $residueAppDirectoryName "v8_context_snapshot.bin"
                    Path = Join-Path `
                        $installedApps[0].FullName "v8_context_snapshot.bin"
                    Required = $false
                }
            )
            foreach ($candidate in $residueCandidates) {
                $candidateExists = Test-Path -LiteralPath $candidate.Path `
                    -ErrorAction Stop
                if ($candidate.Required -and -not $candidateExists) {
                    throw "The installed Squirrel cleanup binary is missing"
                }
                if ($candidateExists) {
                    $expectedResidueDigests.Add(
                        $candidate.RelativePath,
                        (Get-SafeRegularFileDigest `
                            $candidate.Path "Installed Squirrel cleanup file")
                    )
                }
            }
            $residueContractReady = $true
            if ($installedCores.Count -ne 1) {
                throw "Installed application must contain exactly one packaged core"
            }
            Test-Core $installedCores[0].FullName $buildInfo.core_sha256
        }
        finally {
            if ($setupState["Started"]) {
                if (-not $residueContractReady) {
                    throw "The installed Squirrel cleanup contract is unavailable"
                }
                $update = Join-Path $installRoot "Update.exe"
                $currentUpdateDigest = Get-SafeRegularFileDigest `
                    $update "Installed Squirrel Update.exe"
                if (
                    $currentUpdateDigest -cne
                        $expectedResidueDigests["Update.exe"]
                ) {
                    throw "Installed Squirrel Update.exe changed before uninstall"
                }
                $null = Invoke-BoundedProcess -FilePath $update `
                    -ArgumentList "--uninstall", "-s" -TimeoutSeconds 120 `
                    -Description "Squirrel uninstaller"
                $uninstallDeadline = [DateTime]::UtcNow.AddSeconds(60)
                $uninstallCompleted = $false
                do {
                    if (-not (
                        Test-Path -LiteralPath $installRoot -ErrorAction Stop
                    )) {
                        $uninstallCompleted = $true
                        break
                    }
                    $deadMarker = Join-Path $installRoot ".dead"
                    if (
                        Test-Path -LiteralPath $deadMarker -PathType Leaf `
                            -ErrorAction Stop
                    ) {
                        $uninstallCompleted = $true
                        break
                    }
                    Start-Sleep -Milliseconds 500
                } while ([DateTime]::UtcNow -lt $uninstallDeadline)
                if (-not $uninstallCompleted) {
                    throw "Squirrel uninstall did not reach its completed state"
                }
                if (Test-Path -LiteralPath $installRoot -ErrorAction Stop) {
                    if (-not $residueContractReady) {
                        throw "Squirrel uninstall residue could not be validated"
                    }
                    # The pinned Squirrel FullUninstall contract recreates the root
                    # and writes one space to .dead after its best-effort deletion.
                    Remove-OwnedSquirrelUninstallResidue `
                        $installRoot $residueAppDirectoryName `
                        $expectedResidueDigests
                }
            }
        }
    }
    finally {
        $canaryPreserved = $true
        if ($canaryCreated) {
            $canaryPreserved = Test-Path -LiteralPath $canary -PathType Leaf `
                -ErrorAction Stop
        }
        if ($canaryRootCreated) {
            Remove-Item -LiteralPath $canaryRoot -Recurse -Force
        }
        if ($canaryCreated -and -not $canaryPreserved) {
            throw "Uninstall removed a file outside the application directory"
        }
    }
}
