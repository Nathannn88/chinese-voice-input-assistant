[CmdletBinding()]
param(
    [string]$ProjectDir = $PSScriptRoot,
    [string]$UvArchivePath,
    [switch]$FunctionsOnly
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$UvVersion = "0.12.5"
$UvArchiveUrl = "https://github.com/astral-sh/uv/releases/download/0.12.5/uv-x86_64-pc-windows-msvc.zip"
$UvArchiveSha256 = "4c4d49d8738847d9b71ba319e49a5688c93eac0fe6204b1df24e98528dddf39a"
$UvExeSha256 = "8da6cedef60c27ac997ebf400fbfc6d373c5b0a7ae6a299b9d52be7fe63723fb"
$AllowedUvFiles = @("uv.exe", "uvw.exe", "uvx.exe")


function Get-FullPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    return [System.IO.Path]::GetFullPath($Path)
}


function Assert-NotReparsePoint {
    param([Parameter(Mandatory = $true)][System.IO.FileSystemInfo]$Item)
    if (($Item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "拒绝 reparse point：$($Item.FullName)"
    }
}


function Assert-WithinProject {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Root
    )
    $fullPath = Get-FullPath $Path
    $fullRoot = (Get-FullPath $Root).TrimEnd("\")
    $rootPrefix = $fullRoot + "\"
    if (-not $fullPath.StartsWith(
        $rootPrefix,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "路径越出项目目录：$fullPath"
    }
}


function Assert-SafeDirectory {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Root,
        [switch]$Create
    )
    Assert-WithinProject -Path $Path -Root $Root
    if (-not (Test-Path -LiteralPath $Path)) {
        if (-not $Create) {
            throw "目录不存在：$Path"
        }
        New-Item -ItemType Directory -Path $Path | Out-Null
    }

    $item = Get-Item -Force -LiteralPath $Path
    if (-not $item.PSIsContainer) {
        throw "目标不是目录：$Path"
    }
    Assert-NotReparsePoint $item
    Assert-WithinProject -Path $item.FullName -Root $Root

    $probe = Join-Path $item.FullName (".write-probe-" + [Guid]::NewGuid().ToString("N"))
    try {
        [System.IO.File]::WriteAllText($probe, "probe")
    }
    finally {
        if (Test-Path -LiteralPath $probe) {
            Remove-Item -Force -LiteralPath $probe
        }
    }
}


function Get-Sha256 {
    param([Parameter(Mandatory = $true)][string]$Path)
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}


function Assert-Hash {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Expected,
        [Parameter(Mandatory = $true)][string]$Label
    )
    $actual = Get-Sha256 $Path
    if ($actual -ne $Expected.ToLowerInvariant()) {
        throw "$Label SHA-256 不匹配：期望 $Expected，实际 $actual"
    }
}


function Assert-UvArchiveLayout {
    param([Parameter(Mandatory = $true)][string]$ArchivePath)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::OpenRead($ArchivePath)
    try {
        $entries = @($archive.Entries)
        if ($entries.Count -ne $AllowedUvFiles.Count) {
            throw "uv 压缩包文件数量异常：$($entries.Count)"
        }
        $names = @($entries | ForEach-Object { $_.FullName })
        $actual = @($names | Sort-Object)
        $expected = @($AllowedUvFiles | Sort-Object)
        if (($actual -join "|") -cne ($expected -join "|")) {
            throw "uv 压缩包只能包含：$($AllowedUvFiles -join ', ')；实际：$($names -join ', ')"
        }
        foreach ($entry in $entries) {
            if ([string]::IsNullOrWhiteSpace($entry.Name)) {
                throw "uv 压缩包不能包含目录项。"
            }
        }
    }
    finally {
        $archive.Dispose()
    }
}


function Assert-UvInstallation {
    param(
        [Parameter(Mandatory = $true)][string]$UvDir,
        [Parameter(Mandatory = $true)][string]$Root
    )
    Assert-SafeDirectory -Path $UvDir -Root $Root
    $items = @(Get-ChildItem -Force -LiteralPath $UvDir)
    $names = @($items | ForEach-Object { $_.Name } | Sort-Object)
    $expected = @($AllowedUvFiles | Sort-Object)
    if (($names -join "|") -cne ($expected -join "|")) {
        throw "uv 目录文件清单异常：$($names -join ', ')"
    }
    foreach ($item in $items) {
        if ($item.PSIsContainer) {
            throw "uv 目录不能包含子目录：$($item.FullName)"
        }
        Assert-NotReparsePoint $item
    }

    $uvExe = Join-Path $UvDir "uv.exe"
    Assert-Hash -Path $uvExe -Expected $UvExeSha256 -Label "uv.exe"
    $versionOutput = @(& $uvExe --version 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "uv.exe 无法运行，退出码：$LASTEXITCODE"
    }
    $versionText = ($versionOutput -join " ").Trim()
    if ($versionText -notmatch ("^uv " + [regex]::Escape($UvVersion) + "(?:\s|$)")) {
        throw "uv 版本不匹配：期望 $UvVersion，实际 $versionText"
    }
}


function Remove-Strict {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -Force -Recurse -LiteralPath $Path
        if (Test-Path -LiteralPath $Path) {
            throw "清理失败：$Path"
        }
    }
}


function Install-VerifiedUv {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$RuntimeDir,
        [Parameter(Mandatory = $true)][string]$CacheDir,
        [string]$LocalArchive
    )
    $uvDir = Join-Path $RuntimeDir "uv"
    if (Test-Path -LiteralPath $uvDir) {
        try {
            Assert-UvInstallation -UvDir $uvDir -Root $Root
            Write-Host "[通过] 项目内 uv $UvVersion 已通过版本、哈希和清单检查。"
            return
        }
        catch {
            Write-Warning "现有 uv 无效，将在新版本完整校验后替换：$($_.Exception.Message)"
        }
    }

    $bootstrapCache = Join-Path $CacheDir "bootstrap"
    Assert-SafeDirectory -Path $bootstrapCache -Root $Root -Create
    $downloadedArchive = Join-Path $bootstrapCache ("uv-" + [Guid]::NewGuid().ToString("N") + ".zip")
    $archiveToUse = $downloadedArchive
    $removeArchive = $true
    $stageDir = Join-Path $RuntimeDir ("uv-stage-" + [Guid]::NewGuid().ToString("N"))
    $backupDir = Join-Path $RuntimeDir ("uv-backup-" + [Guid]::NewGuid().ToString("N"))
    Assert-WithinProject -Path $stageDir -Root $Root
    Assert-WithinProject -Path $backupDir -Root $Root

    try {
        if ($LocalArchive) {
            $archiveToUse = Get-FullPath $LocalArchive
            Assert-WithinProject -Path $archiveToUse -Root $Root
            if (-not (Test-Path -LiteralPath $archiveToUse -PathType Leaf)) {
                throw "指定的 uv 压缩包不存在：$archiveToUse"
            }
            $removeArchive = $false
        }
        else {
            Write-Host "[下载] $UvArchiveUrl"
            Invoke-WebRequest -UseBasicParsing -Uri $UvArchiveUrl -OutFile $downloadedArchive
        }

        Assert-Hash -Path $archiveToUse -Expected $UvArchiveSha256 -Label "uv 压缩包"
        Assert-UvArchiveLayout -ArchivePath $archiveToUse
        New-Item -ItemType Directory -Path $stageDir | Out-Null
        Expand-Archive -LiteralPath $archiveToUse -DestinationPath $stageDir
        Assert-UvInstallation -UvDir $stageDir -Root $Root

        $hadOld = Test-Path -LiteralPath $uvDir
        if ($hadOld) {
            Move-Item -LiteralPath $uvDir -Destination $backupDir
        }
        try {
            Move-Item -LiteralPath $stageDir -Destination $uvDir
            Assert-UvInstallation -UvDir $uvDir -Root $Root
        }
        catch {
            Remove-Strict $uvDir
            if ($hadOld -and (Test-Path -LiteralPath $backupDir)) {
                Move-Item -LiteralPath $backupDir -Destination $uvDir
            }
            throw
        }

        if (Test-Path -LiteralPath $backupDir) {
            Remove-Strict $backupDir
        }
        Write-Host "[通过] uv $UvVersion 已安全安装到 $uvDir"
    }
    finally {
        Remove-Strict $stageDir
        if ($removeArchive) {
            Remove-Strict $downloadedArchive
        }
    }
}


if ($FunctionsOnly) {
    return
}

$projectRoot = Get-FullPath $ProjectDir
if (-not (Test-Path -LiteralPath $projectRoot -PathType Container)) {
    throw "项目目录不存在：$projectRoot"
}
$projectItem = Get-Item -Force -LiteralPath $projectRoot
Assert-NotReparsePoint $projectItem

$runtimeDir = Join-Path $projectRoot ".runtime"
$cacheDir = Join-Path $projectRoot ".cache"
$modelsDir = Join-Path $projectRoot "models"

Assert-SafeDirectory -Path $runtimeDir -Root $projectRoot -Create
Assert-SafeDirectory -Path $cacheDir -Root $projectRoot -Create
Assert-SafeDirectory -Path $modelsDir -Root $projectRoot -Create
foreach ($cacheName in @("tmp", "uv", "pip", "huggingface", "cuda")) {
    Assert-SafeDirectory -Path (Join-Path $cacheDir $cacheName) -Root $projectRoot -Create
}

Install-VerifiedUv -Root $projectRoot -RuntimeDir $runtimeDir -CacheDir $cacheDir -LocalArchive $UvArchivePath
