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

function Invoke-BoundedProcess {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,

        [string[]]$ArgumentList = @(),

        [Parameter(Mandatory = $true)]
        [ValidateRange(1, 3600)]
        [int]$TimeoutSeconds,

        [Parameter(Mandatory = $true)]
        [string]$Description
    )

    $processRoot = Join-Path ([System.IO.Path]::GetTempPath()) (
        "docmeta verifier process " + [guid]::NewGuid().ToString("N")
    )
    $stdoutPath = Join-Path $processRoot "stdout.txt"
    $stderrPath = Join-Path $processRoot "stderr.txt"
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
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            try {
                $process.Kill($true)
            }
            catch {
                throw "$Description timed out and its process tree could not be terminated"
            }
            if (-not $process.WaitForExit(5000)) {
                throw "$Description timed out and its process tree could not be terminated"
            }
            throw "$Description timed out"
        }
        $exitCode = $process.ExitCode
        if ($exitCode -ne 0) {
            throw "$Description returned exit code $exitCode"
        }
        $stdout = Get-Item -LiteralPath $stdoutPath -ErrorAction Stop
        if ($stdout.Length -gt 4MB) {
            throw "$Description produced excessive standard output"
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

function Test-Core([string]$CorePath, [string]$ExpectedDigest) {
    $digest = (Get-FileHash -Algorithm SHA256 -LiteralPath $CorePath).Hash.ToLowerInvariant()
    if ($digest -cne $ExpectedDigest) {
        throw "Packaged core hash does not match BUILD-INFO.json"
    }
    $jsonText = Invoke-BoundedProcess -FilePath $CorePath -ArgumentList "verify" `
        -TimeoutSeconds 60 -Description "Frozen core verification"
    try {
        $report = $jsonText | ConvertFrom-Json -NoEnumerate
    }
    catch {
        throw "Frozen core verification did not return valid JSON"
    }
    if ($report -isnot [pscustomobject]) {
        throw "Frozen core verification did not return one JSON object"
    }
    $checks = @($report.checks)
    if ($report.passed -ne $true -or $checks.Count -ne 6) {
        throw "Frozen core verification did not return six passing checks"
    }
    foreach ($check in $checks) {
        if ($check.status -cne "pass") {
            throw "Frozen core verification contains a failed check"
        }
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
    $buildInfo = $buildInfoText | ConvertFrom-Json -NoEnumerate
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

$testRoot = Join-Path ([System.IO.Path]::GetTempPath()) (
    "文档元数据核验 portable " + [guid]::NewGuid().ToString("N")
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
    $update = Join-Path $installRoot "Update.exe"
    $canaryRootCreated = $false
    $canaryCreated = $false
    try {
        New-Item -ItemType Directory -Path $canaryRoot | Out-Null
        $canaryRootCreated = $true
        Set-Content -LiteralPath $canary -Value "preserve" -ErrorAction Stop
        $canaryCreated = $true
        Test-CleanInstallRoot $installRoot
        $null = Invoke-BoundedProcess -FilePath $setup -ArgumentList "--silent" `
            -TimeoutSeconds 120 -Description "Squirrel installer"
        $installDeadline = [DateTime]::UtcNow.AddSeconds(60)
        do {
            $installedCores = @(Get-InstalledCores $installRoot)
            if ($installedCores.Count -eq 1) { break }
            Start-Sleep -Milliseconds 500
        } while ([DateTime]::UtcNow -lt $installDeadline)
        if ($installedCores.Count -ne 1) {
            throw "Installed application must contain exactly one packaged core"
        }
        Test-Core $installedCores[0].FullName $buildInfo.core_sha256
    }
    finally {
        try {
            if (Test-Path -LiteralPath $update -ErrorAction Stop) {
                if (-not (
                    Test-Path -LiteralPath $update -PathType Leaf -ErrorAction Stop
                )) {
                    throw "Squirrel Update.exe is not a regular file"
                }
                $null = Invoke-BoundedProcess -FilePath $update `
                    -ArgumentList "--uninstall", "-s" -TimeoutSeconds 120 `
                    -Description "Squirrel uninstaller"
            }
            $uninstallDeadline = [DateTime]::UtcNow.AddSeconds(60)
            do {
                $remainingApps = @(Get-RemainingApps $installRoot)
                if ($remainingApps.Count -eq 0) { break }
                Start-Sleep -Milliseconds 500
            } while ([DateTime]::UtcNow -lt $uninstallDeadline)
            if ($remainingApps.Count -ne 0) {
                throw "Squirrel uninstall left an installed application directory"
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
}
