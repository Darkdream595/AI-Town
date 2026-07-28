@echo off
chcp 65001 >nul
rem AI Town 启动入口（DOC-RELEASE-008 RULE-RELEASE-055）
rem 只做三件事：设定代码页、定位包根、委派 Launcher；不解析参数、
rem 不写注册表、不请求管理员权限
start "" "%~dp0runtime\backend\AI-Town.exe"
