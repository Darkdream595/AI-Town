[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$PackageDirectory,
    [string]$ReportPath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $projectRoot "backend\venv\Scripts\python.exe"
$tool = Join-Path $projectRoot "tools\release\release_packaging.py"
$arguments = @($tool, "verify", $PackageDirectory)
if ($ReportPath) {
    $arguments += @("--report", $ReportPath)
}

& $python @arguments
if ($LASTEXITCODE -ne 0) {
    throw "发布包离线验证失败。"
}
