Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$LastStage = "startup"

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$ArgumentList,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory
    )
    Push-Location -LiteralPath $WorkingDirectory
    try {
        & $FilePath @ArgumentList
        $exitCode = $LASTEXITCODE
        if ($exitCode -ne 0) {
            throw "Native command failed with exit code $exitCode: $FilePath"
        }
    }
    finally {
        Pop-Location
    }
}

function Test-Windows10Or11X64Client {
    param(
        [Parameter(Mandatory = $true)][object]$OperatingSystem,
        [Parameter(Mandatory = $true)][object[]]$Processors
    )
    try {
        $version = [version][string]$OperatingSystem.Version
        $productType = [int]$OperatingSystem.ProductType
    }
    catch {
        return $false
    }
    if ($version.Major -ne 10 -or $productType -ne 1) {
        return $false
    }
    if ($Processors.Count -eq 0) {
        return $false
    }
    foreach ($processor in $Processors) {
        try {
            $architecture = [int]$processor.Architecture
        }
        catch {
            return $false
        }
        if ($architecture -ne 9) {
            return $false
        }
    }
    return $true
}

try {
    $LastStage = "Windows x64 preflight"
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        throw "This build entry requires Windows"
    }
    if (-not [Environment]::Is64BitOperatingSystem) {
        throw "This build entry requires 64-bit Windows"
    }
    $operatingSystems = @(
        Get-CimInstance -ClassName "Win32_OperatingSystem" -ErrorAction Stop
    )
    $processors = @(
        Get-CimInstance -ClassName "Win32_Processor" -ErrorAction Stop
    )
    if (
        $operatingSystems.Count -ne 1 -or
        -not (Test-Windows10Or11X64Client $operatingSystems[0] $processors)
    ) {
        throw "This build entry requires Windows 10 or 11 client on AMD64/x64"
    }
    Get-Command uv -ErrorAction Stop | Out-Null
    Get-Command nvm -ErrorAction Stop | Out-Null

    $LastStage = "Node.js 24 setup"
    Invoke-NativeCommand -FilePath "nvm" -ArgumentList @("install", "24") `
        -WorkingDirectory $ProjectRoot
    Invoke-NativeCommand -FilePath "nvm" -ArgumentList @("use", "24") `
        -WorkingDirectory $ProjectRoot
    Get-Command node -ErrorAction Stop | Out-Null
    Get-Command corepack -ErrorAction Stop | Out-Null
    $nodeVersion = @(
        Invoke-NativeCommand -FilePath "node" -ArgumentList @("--version") `
            -WorkingDirectory $ProjectRoot
    )
    $nodeVersionText = ($nodeVersion -join "`n").Trim()
    if ($nodeVersionText -notmatch "^v24\.") {
        throw "nvm did not activate a Node.js 24 release"
    }
    $nodeArchitecture = @(
        Invoke-NativeCommand -FilePath "node" `
            -ArgumentList @("-p", "process.arch") -WorkingDirectory $ProjectRoot
    )
    $nodeArchitectureText = ($nodeArchitecture -join "`n").Trim()
    if ($nodeArchitectureText -cne "x64") {
        throw "nvm did not activate an x64 Node.js release"
    }

    $LastStage = "project-local build cache setup"
    $BuildCache = Join-Path $ProjectRoot "tools\build-cache"
    $env:UV_CACHE_DIR = Join-Path $BuildCache "uv"
    $env:COREPACK_HOME = Join-Path $BuildCache "corepack"
    $env:electron_config_cache = Join-Path $BuildCache "electron"
    $PnpmStore = Join-Path $BuildCache "pnpm-store"
    New-Item -ItemType Directory -Path $BuildCache -Force | Out-Null

    $LastStage = "pnpm 11.10.0 setup"
    Invoke-NativeCommand -FilePath "corepack" `
        -ArgumentList @("install", "--global", "pnpm@11.10.0") `
        -WorkingDirectory $ProjectRoot
    $pnpmVersion = @(
        Invoke-NativeCommand -FilePath "corepack" `
            -ArgumentList @("pnpm", "--version") -WorkingDirectory $ProjectRoot
    )
    $pnpmVersionText = ($pnpmVersion -join "`n").Trim()
    if ($pnpmVersionText -cne "11.10.0") {
        throw "Corepack did not activate pnpm 11.10.0"
    }

    $LastStage = "locked Python environment"
    Invoke-NativeCommand -FilePath "uv" `
        -ArgumentList @("python", "install", "3.12.13") `
        -WorkingDirectory $ProjectRoot
    Invoke-NativeCommand -FilePath "uv" `
        -ArgumentList @("sync", "--all-groups", "--locked") `
        -WorkingDirectory $ProjectRoot

    $LastStage = "vendored Windows runtime preparation"
    Invoke-NativeCommand -FilePath "uv" `
        -ArgumentList @(
            "run", "python", "scripts/windows_vendored_java.py", "--cache",
            "tools/build-cache/windows-vendored-java"
        ) -WorkingDirectory $ProjectRoot

    $LastStage = "Python quality checks"
    Invoke-NativeCommand -FilePath "uv" -ArgumentList @("run", "pytest") `
        -WorkingDirectory $ProjectRoot
    Invoke-NativeCommand -FilePath "uv" `
        -ArgumentList @("run", "ruff", "check", ".") `
        -WorkingDirectory $ProjectRoot
    Invoke-NativeCommand -FilePath "uv" `
        -ArgumentList @("run", "ruff", "format", "--check", ".") `
        -WorkingDirectory $ProjectRoot
    Invoke-NativeCommand -FilePath "uv" `
        -ArgumentList @("run", "basedpyright") `
        -WorkingDirectory $ProjectRoot
    Invoke-NativeCommand -FilePath "uv" -ArgumentList @("lock", "--check") `
        -WorkingDirectory $ProjectRoot
    Invoke-NativeCommand -FilePath "uv" -ArgumentList @("build") `
        -WorkingDirectory $ProjectRoot

    $DesktopRoot = Join-Path $ProjectRoot "desktop"
    $LastStage = "locked desktop environment"
    Invoke-NativeCommand -FilePath "corepack" `
        -ArgumentList @(
            "pnpm", "install", "--frozen-lockfile", "--store-dir", $PnpmStore
        ) -WorkingDirectory $DesktopRoot

    $LastStage = "desktop quality checks"
    Invoke-NativeCommand -FilePath "corepack" `
        -ArgumentList @("pnpm", "test") -WorkingDirectory $DesktopRoot
    Invoke-NativeCommand -FilePath "corepack" `
        -ArgumentList @("pnpm", "typecheck") -WorkingDirectory $DesktopRoot
    Invoke-NativeCommand -FilePath "corepack" `
        -ArgumentList @("pnpm", "lint") -WorkingDirectory $DesktopRoot
    Invoke-NativeCommand -FilePath "corepack" `
        -ArgumentList @("pnpm", "format:check") -WorkingDirectory $DesktopRoot
    Invoke-NativeCommand -FilePath "corepack" `
        -ArgumentList @("pnpm", "build") -WorkingDirectory $DesktopRoot

    $LastStage = "final frozen desktop build"
    Invoke-NativeCommand -FilePath "corepack" `
        -ArgumentList @("pnpm", "make") -WorkingDirectory $DesktopRoot

    $LastStage = "checksummed release packaging"
    Invoke-NativeCommand -FilePath "uv" `
        -ArgumentList @("run", "python", "scripts/package_release.py") `
        -WorkingDirectory $ProjectRoot
    Invoke-NativeCommand -FilePath "uv" `
        -ArgumentList @("run", "python", "scripts/assemble_windows_release.py") `
        -WorkingDirectory $ProjectRoot

    $LastStage = "final Windows release verification"
    & (Join-Path $ProjectRoot "scripts\verify_windows_release.ps1") `
        -ReleaseDirectory (Join-Path $ProjectRoot "release\windows-x64") `
        -Mode "All"

    $LastStage = "release manifest output"
    $releaseDirectory = Join-Path $ProjectRoot "release\windows-x64"
    $releaseFiles = @(
        Get-ChildItem -LiteralPath $releaseDirectory -File -ErrorAction Stop |
            Sort-Object -Property Name
    )
    if ($releaseFiles.Count -ne 6) {
        throw "Windows release verification did not produce exactly six release files"
    }
    foreach ($releaseFile in $releaseFiles) {
        $relativePath = $releaseFile.FullName.Substring($releaseDirectory.Length)
        $relativeName = $relativePath.TrimStart([char[]]"\\/")
        $hash = (
            Get-FileHash -LiteralPath $releaseFile.FullName -Algorithm SHA256
        ).Hash.ToLowerInvariant()
        Write-Output ("{0}`t{1}`t{2}" -f $relativeName, $releaseFile.Length, $hash)
    }
}
catch {
    Write-Error "Windows x64 release build failed during $LastStage: $($_.Exception.Message)"
    exit 1
}
