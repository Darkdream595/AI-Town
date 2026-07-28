<div align="center">

# AI Town · AI 小镇

一个运行在本地浏览器中的中世纪奇幻 AI 小镇。

[![Version](https://img.shields.io/badge/version-v0.1.0--alpha-7c3aed)](#开发状态)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](#技术栈)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109-009688?logo=fastapi&logoColor=white)](#技术栈)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.x-3178C6?logo=typescript&logoColor=white)](#技术栈)
[![Phaser](https://img.shields.io/badge/Phaser-3.80-8A2BE2)](#技术栈)

</div>

![AI Town 地图预览](frontend/public/assets/maps/crown_creek_town_base.png)

AI Town 是一个本地单机项目：FastAPI 维护世界状态与数据，Phaser 在浏览器中呈现和交互。项目围绕居民、地图、对话、实时通信与本地持久化持续开发，并预留 DeepSeek 模型接入能力。

> 当前版本为 **v0.1.0 alpha**，适合本地体验与开发验证。

## 开始游玩

玩家使用发布包时，**不需要安装 Python 或 Node.js**。

1. 获取 `dist/AI-Town-<version>.zip` 发布压缩包并解压。
2. 双击解压目录顶层的 `AI-Town.exe`。
3. 等待程序启动；默认浏览器会自动打开游戏页面。
4. 点击网页内全屏按钮，或按 `F11` 进入浏览器全屏。
5. 退出时双击同目录顶层的 `关闭AI-Town.bat`。

如果使用本机生成但尚未压缩的发布目录，入口位于 `dist/AI-Town/AI-Town.exe`。玩家启动入口始终是 EXE，BAT 只用于关闭程序。

## 技术栈

| 层级 | 主要技术 | 职责 |
| --- | --- | --- |
| 后端 | Python 3.11、FastAPI | 本地服务、REST API、世界逻辑 |
| 前端 | TypeScript、Phaser 3、Vite | 浏览器游戏场景与交互 |
| 数据 | SQLite | 本地世界状态与持久化 |
| 通信 | WebSocket | 前后端实时事件同步 |
| AI | DeepSeek 兼容接口 | 居民模型能力与响应策略 |

DeepSeek 配置由本地运行时管理。API Key 等密钥不得写入源码、配置样例、日志或 Git 历史，也不会随仓库或发布包分发。

## 开发环境

开发者需要准备：

- Python 3.11+
- Node.js 与 npm
- Windows PowerShell 或命令提示符

### 一键启动开发环境

在项目根目录双击：

```text
tools/dev/启动开发环境.bat
```

该脚本会准备本地依赖，并分别启动 FastAPI 与 Vite 开发服务。它是开发工具，不是玩家发布包入口。

### 手动启动

首次准备后端环境：

```powershell
python -m venv backend/venv
backend/venv/Scripts/python.exe -m pip install -r backend/requirements.txt
```

终端一，在项目根目录启动后端：

```powershell
$env:PYTHONPATH = "backend"
backend/venv/Scripts/python.exe -m uvicorn src.main:app --host 127.0.0.1 --port 8000 --reload
```

终端二，启动前端：

```powershell
Set-Location frontend
npm install
npm run dev
```

然后访问 `http://localhost:5173`。

## 项目结构

```text
AI_Town/
├─ backend/        # FastAPI 后端、SQLite 持久化与后端测试
├─ frontend/       # Phaser/Vite 前端、资源与前端测试
├─ release/        # Windows 发布构建脚本与发布包骨架
├─ dist/           # 本机构建生成物（不提交到 Git）
├─ tools/
│  └─ dev/         # 开发环境启动工具
├─ docs/           # 设计、协议与实现文档
├─ shared/         # 前后端共享协议与模型
└─ _local/         # 被 Git 忽略的本机资料、备份与会话记录
```

`dist/` 与 `_local/` 都是本地目录：前者可重新构建，后者只用于保存当前机器上的资料。

## 测试与构建

运行后端测试：

```powershell
Set-Location backend
venv/Scripts/python.exe -m pytest tests -q
```

运行前端测试与构建：

```powershell
Set-Location frontend
npm test -- --run --exclude src/tests/residents-api.test.ts
npm run build
```

`src/tests/residents-api.test.ts` 是需要本地后端配合的手动 API 检查脚本，不属于 Vitest 自动化测试集。

在干净的 Git 工作区中构建 Windows 发布包：

```powershell
.\release\build-release.ps1 -PackageVersion 0.1.0 -BuildId <当前 Git commit SHA>
```

构建结果写入根目录 `dist/`，包括可解压游玩的 `AI-Town/` 目录与版本压缩包。

## 开发状态

AI Town 当前处于 **v0.1.0 alpha / 本地开发中**。功能、数据格式和发布方式仍可能调整；提交问题时请附上复现步骤、运行方式和必要日志，但不要附带任何 API Key。

## 许可证

本仓库目前是个人学习项目，尚未声明开源许可证。除非另有书面说明，仓库公开可见不等于授予复制、修改、分发或商业使用许可。
