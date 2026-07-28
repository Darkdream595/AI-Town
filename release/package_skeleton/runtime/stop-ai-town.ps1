# AI Town 备用停止脚本（DOC-RELEASE-008 RULE-RELEASE-060）
# 读取 instance.json → POST /api/v1/shutdown（携带 shutdown_token）→
# 15 秒内等待进程退出确认 → 删除 instance.json；
# 连接失败说明后端已死：清理陈旧 instance.json 后提示。绝不强杀进程。

$ErrorActionPreference = "Stop"
$instancePath = Join-Path "$env:LOCALAPPDATA\AI-Town\runtime" "instance.json"

if (-not (Test-Path $instancePath)) {
    Write-Host "没有正在运行的 AI Town 实例。"
    exit 0
}

$instance = Get-Content $instancePath -Raw -Encoding UTF8 | ConvertFrom-Json
$url = "http://127.0.0.1:$($instance.port)/api/v1/shutdown"

try {
    Invoke-RestMethod -Method Post -Uri $url `
        -Headers @{ Origin = "http://127.0.0.1:$($instance.port)" } `
        -Body (@{
            schema_version = 1
            shutdown_token = $instance.shutdown_token
        } | ConvertTo-Json) `
        -ContentType "application/json" -TimeoutSec 5 | Out-Null
} catch {
    # 后端已死：按陈旧实例清理（RULE-RELEASE-061）
    Remove-Item $instancePath -Force -ErrorAction SilentlyContinue
    Write-Host "后端进程已不在运行，已清理残留实例记录。"
    exit 0
}

$deadline = (Get-Date).AddSeconds(15)
$stopped = $false
while ((Get-Date) -lt $deadline) {
    try {
        Invoke-WebRequest -Uri "http://127.0.0.1:$($instance.port)/api/v1/health" `
            -TimeoutSec 2 | Out-Null
        Start-Sleep -Milliseconds 500
    } catch {
        $stopped = $true
        break
    }
}

if ($stopped) {
    Remove-Item $instancePath -Force -ErrorAction SilentlyContinue
    Write-Host "AI Town 已安全停止，存档已保存。"
} else {
    Write-Host "停止请求已发送但进程未在 15 秒内退出。"
    Write-Host "请在系统托盘中选择「保存并退出」，"
    Write-Host "或在任务管理器结束 AI-Town.exe（下次启动将按崩溃恢复处理）。"
}
