[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$')]
    [string]$PackageVersion,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F]{7,40}$')]
    [string]$BuildId,

    [string]$PythonExecutable = "",
    [string]$LicenseSource = "",
    [string]$OutputRoot = "",
    [string]$BuildTime = "",
    [string]$MigrationCurrent = '{"app":1,"world":1}',
    [switch]$AllowDirty
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$packagingTool = Join-Path $projectRoot "tools\release\release_packaging.py"
$python = if ($PythonExecutable) {
    $PythonExecutable
} else {
    Join-Path $projectRoot "backend\venv\Scripts\python.exe"
}
$licenseRoot = if ($LicenseSource) {
    $LicenseSource
} else {
    Join-Path $PSScriptRoot "licenses"
}
$output = if ($OutputRoot) {
    $OutputRoot
} else {
    Join-Path $PSScriptRoot "out"
}
$frontendRoot = Join-Path $projectRoot "frontend"
$frontendDist = Join-Path $frontendRoot "dist"
$pyinstallerDist = Join-Path $output "_pyinstaller-dist"
$pyinstallerWork = Join-Path $output "_pyinstaller-work"
$packageDir = Join-Path $output "AI-Town"
$verifyReport = Join-Path $output "package-verify-report.json"
$archivePath = Join-Path $output "AI-Town-$PackageVersion.zip"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Python 构建解释器不存在：$python"
}
if (-not (Test-Path -LiteralPath $licenseRoot -PathType Container)) {
    throw "许可证源目录不存在：$licenseRoot。必须先完成依赖许可证审核，工具不会联网补齐。"
}
if (-not $AllowDirty) {
    $dirtyEntries = @(& git -C $projectRoot status --porcelain --untracked-files=all)
    if ($LASTEXITCODE -ne 0 -or $dirtyEntries.Count -gt 0) {
        throw "工作区存在未提交或未跟踪文件；发布构建要求 clean checkout。调试时可显式传 -AllowDirty。"
    }
}

# 预检只检测工具，绝不在构建脚本中安装依赖。
& $python -m PyInstaller --version
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller 未安装或不可用。请在隔离构建环境显式安装锁定版本后重试；脚本不会自动安装依赖。"
}

New-Item -ItemType Directory -Force -Path $output | Out-Null

Push-Location $frontendRoot
try {
    & npm ci
    if ($LASTEXITCODE -ne 0) { throw "npm ci 失败。" }
    & npm run build
    if ($LASTEXITCODE -ne 0) { throw "frontend build 失败。" }
} finally {
    Pop-Location
}

# Vite 当前开发配置会生成 sourcemap；构建流水线自动移除，禁止其进入发布包。
Get-ChildItem -LiteralPath $frontendDist -Recurse -File -Filter "*.map" |
    Remove-Item -Force

& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --distpath $pyinstallerDist `
    --workpath $pyinstallerWork `
    (Join-Path $PSScriptRoot "AI-Town.spec")
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller one-folder build 失败。"
}

& $python $packagingTool assemble `
    --package-dir $packageDir `
    --skeleton (Join-Path $PSScriptRoot "package_skeleton") `
    --backend-bundle (Join-Path $pyinstallerDist "AI-Town") `
    --frontend-dist $frontendDist `
    --licenses $licenseRoot
if ($LASTEXITCODE -ne 0) { throw "发布包 layout 组装失败。" }

if (-not $BuildTime) {
    $commitTime = (& git -C $projectRoot show -s --format=%cI $BuildId).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $commitTime) {
        throw "无法从 build_id 解析可复现 build_time：$BuildId"
    }
    $BuildTime = ([DateTimeOffset]::Parse($commitTime)).UtcDateTime.ToString(
        "yyyy-MM-ddTHH:mm:ss.fffZ")
}

& $python $packagingTool manifest $packageDir `
    --package-version $PackageVersion `
    --build-id $BuildId `
    --build-time $BuildTime `
    --migration-current $MigrationCurrent
if ($LASTEXITCODE -ne 0) { throw "release-manifest 生成失败。" }

& $python $packagingTool verify $packageDir --report $verifyReport
if ($LASTEXITCODE -ne 0) {
    throw "离线 package verify 失败；报告：$verifyReport"
}

& $python $packagingTool archive $packageDir $archivePath
if ($LASTEXITCODE -ne 0) { throw "可复现 ZIP 生成失败。" }

Write-Host "发布包构建完成：$archivePath"
Write-Host "离线验证报告：$verifyReport"
