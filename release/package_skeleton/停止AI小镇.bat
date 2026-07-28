@echo off
chcp 65001 >nul
rem AI Town 备用停止入口（DOC-RELEASE-008 RULE-RELEASE-060）
rem 读取 instance.json，携带 shutdown_token 请求正常关闭；
rem 绝不 taskkill 强杀（绕过安全保存按崩溃恢复处理）
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0runtime\stop-ai-town.ps1"
