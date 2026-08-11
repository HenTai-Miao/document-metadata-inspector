param(
    [Parameter(Mandatory = $true)]
    [string]$ReleaseDirectory,

    [ValidateSet("Portable", "All")]
    [string]$Mode = "Portable"
)

$ErrorActionPreference = "Stop"
$release = (Resolve-Path -LiteralPath $ReleaseDirectory).Path
$buildInfo = Get-Content -LiteralPath (Join-Path $release "BUILD-INFO.json") -Raw |
    ConvertFrom-Json

function Get-SingleFile([string]$Pattern, [string]$Description) {
    $matches = @(Get-ChildItem -LiteralPath $release -File -Filter $Pattern)
    if ($matches.Count -ne 1) {
        throw "$Description must resolve to exactly one file"
    }
    return $matches[0].FullName
}

function Test-Core([string]$CorePath) {
    $digest = (Get-FileHash -Algorithm SHA256 -LiteralPath $CorePath).Hash.ToLowerInvariant()
    if ($digest -ne $buildInfo.core_sha256) {
        throw "Packaged core hash does not match BUILD-INFO.json"
    }
    $jsonText = & $CorePath verify
    if ($LASTEXITCODE -ne 0) {
        throw "Frozen core verification returned a nonzero exit code"
    }
    $report = ($jsonText -join "`n") | ConvertFrom-Json
    if (-not $report.passed -or $report.checks.Count -ne 6) {
        throw "Frozen core verification did not return six passing checks"
    }
    foreach ($check in $report.checks) {
        if ($check.status -ne "pass") {
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
foreach ($line in $manifestLines) {
    if ($line -notmatch '^([0-9a-f]{64})  ([^\\/]+)$') {
        throw "SHA256SUMS contains an invalid record"
    }
    $expected = $Matches[1]
    $filename = $Matches[2]
    $path = Join-Path $release $filename
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "SHA256SUMS references a missing file"
    }
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant()
    if ($actual -ne $expected) {
        throw "Release file hash does not match SHA256SUMS"
    }
}

$testRoot = Join-Path ([System.IO.Path]::GetTempPath()) (
    "文档元数据核验 portable " + [guid]::NewGuid().ToString("N")
)
$movedRoot = "$testRoot moved"
$portable = Get-SingleFile "*-Portable.zip" "Portable archive"

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
    Test-Core $portableCores[0].FullName
    Move-Item -LiteralPath $testRoot -Destination $movedRoot
    $movedCore = @(
        Get-ChildItem -LiteralPath $movedRoot -Recurse -File -Filter "docmeta.exe" |
            Where-Object { $_.FullName -like "*resources*docmeta-runtime*docmeta.exe" }
    )
    if ($movedCore.Count -ne 1) {
        throw "Moved portable application must contain exactly one packaged core"
    }
    Test-Core $movedCore[0].FullName
}
finally {
    if (Test-Path -LiteralPath $movedRoot) {
        Remove-Item -LiteralPath $movedRoot -Recurse -Force
    }
    if (Test-Path -LiteralPath $testRoot) {
        Remove-Item -LiteralPath $testRoot -Recurse -Force
    }
}

if ($Mode -eq "All") {
    $setup = Get-SingleFile "*-Setup.exe" "Squirrel installer"
    $installRoot = Join-Path $env:LOCALAPPDATA "DocumentMetadataInspector"
    if (Test-Path $installRoot) {
        throw "All mode requires a clean test account without an existing installation"
    }
    $canaryRoot = Join-Path ([System.IO.Path]::GetTempPath()) (
        "docmeta uninstall canary " + [guid]::NewGuid().ToString("N")
    )
    $canary = Join-Path $canaryRoot "preserve.txt"
    New-Item -ItemType Directory -Path $canaryRoot | Out-Null
    Set-Content -LiteralPath $canary -Value "preserve"
    $update = Join-Path $installRoot "Update.exe"
    try {
        $installer = Start-Process -FilePath $setup -ArgumentList "--silent" -Wait -PassThru
        if ($installer.ExitCode -ne 0) {
            throw "Squirrel installer returned a nonzero exit code"
        }
        $installDeadline = [DateTime]::UtcNow.AddSeconds(60)
        do {
            $installedCores = @(
                Get-ChildItem -LiteralPath $installRoot -Recurse -File `
                    -Filter "docmeta.exe" -ErrorAction SilentlyContinue |
                    Where-Object {
                        $_.FullName -like "*app-*resources*docmeta-runtime*docmeta.exe"
                    }
            )
            if ($installedCores.Count -eq 1) { break }
            Start-Sleep -Milliseconds 500
        } while ([DateTime]::UtcNow -lt $installDeadline)
        if ($installedCores.Count -ne 1) {
            throw "Installed application must contain exactly one packaged core"
        }
        Test-Core $installedCores[0].FullName
    }
    finally {
        try {
            if (Test-Path -LiteralPath $update -PathType Leaf) {
                $uninstaller = Start-Process -FilePath $update `
                    -ArgumentList "--uninstall", "-s" -Wait -PassThru
                if ($uninstaller.ExitCode -ne 0) {
                    throw "Squirrel uninstaller returned a nonzero exit code"
                }
            }
            $uninstallDeadline = [DateTime]::UtcNow.AddSeconds(60)
            do {
                $remainingApps = @(
                    Get-ChildItem -LiteralPath $installRoot -Directory `
                        -Filter "app-*" -ErrorAction SilentlyContinue
                )
                if ($remainingApps.Count -eq 0) { break }
                Start-Sleep -Milliseconds 500
            } while ([DateTime]::UtcNow -lt $uninstallDeadline)
            if ($remainingApps.Count -ne 0) {
                throw "Squirrel uninstall left an installed application directory"
            }
        }
        finally {
            $canaryPreserved = Test-Path -LiteralPath $canary -PathType Leaf
            if (Test-Path -LiteralPath $canaryRoot) {
                Remove-Item -LiteralPath $canaryRoot -Recurse -Force
            }
            if (-not $canaryPreserved) {
                throw "Uninstall removed a file outside the application directory"
            }
        }
    }
}
