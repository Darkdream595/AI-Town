# AI Town - AI 小镇

> 一个中世纪剑与魔法主题的日式西幻 AI 小镇，由 DeepSeek V4 Flash 驱动的自主 AI 居民。

## 项目概述

AI Town 是一个本地运行的单机游戏，玩家可以作为居民参与世界，也可以切换到镇长模式治理小镇。游戏包含 8-12 名由 AI 自主决策的居民，他们拥有记忆、情感、关系和目标，能够自由探索、对话、工作、交易、施法和战斗。

### 核心特性

- 🏰 **三个区域**：王冠溪镇、暮语森林、银烬矿洞
- 🤖 **AI 居民**：由 DeepSeek V4 Flash 驱动，拥有记忆、情感和自主决策
- 👤 **双模式**：居民模式（自由探索）+ 镇长模式（治理操作）
- 💬 **自然语言**：玩家与 AI 居民进行自然语言对话
- 🎯 **完整系统**：经济、魔法、战斗、事件、建筑、关系
- 💾 **多世界存档**：自动存档 + 3 个手动槽位
- 🖱️ **一键启动**：双击 `.bat` 即可运行

## 技术架构

### 后端
- **Python 3.11+** + FastAPI
- **SQLite** 数据库
- **DeepSeek V4 Flash** API
- WebSocket 实时通信

### 前端
- **TypeScript** + Phaser 3
- **Vite** 构建工具
- 2D 正交俯视视角

## 快速开始

### 环境要求

- Windows 10/11
- Python 3.11+
- Node.js 18+
- DeepSeek API Key（首次启动时输入）

### 启动游戏

1. 双击 `启动AI小镇.bat`
2. 等待服务启动（约 10-15 秒）
3. 浏览器自动打开游戏页面
4. 按 **F11** 进入全屏模式

### 手动启动（开发者）

**后端**：
```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python src/main.py
```

**前端**：
```bash
cd frontend
npm install
npm run dev
```

访问：http://localhost:5173

## 项目结构

```
AI_Town/
├── backend/              # Python FastAPI 后端
│   ├── src/              # 源代码
│   │   ├── main.py       # 入口
│   │   ├── foundation/   # 基础设施
│   │   ├── world/        # 世界设计
│   │   ├── map/          # 地图导航
│   │   ├── residents/    # 居民系统
│   │   ├── ai/           # AI 决策
│   │   ├── memory/       # 记忆社交
│   │   └── ...           # 其他域
│   └── tests/            # 单元测试
├── frontend/             # TypeScript Phaser 3 前端
│   ├── src/              # 源代码
│   │   ├── main.ts       # 入口
│   │   ├── scenes/       # Phaser 场景
│   │   └── ...           # 其他模块
│   └── tests/            # 单元测试
├── shared/               # 前后端共享 Schema
├── docs/                 # 设计文档（188 份）
├── assets/               # 游戏资源
└── 启动AI小镇.bat        # 一键启动脚本
```

## 文档

本项目包含完整的设计文档体系（188 份）：

- **Foundation**：`docs/00-foundation/`（8 份跨系统总纲）
- **业务域**：`docs/01-15-**/`（15 个域 × 12 份）

查看完整文档索引：[docs/00-foundation/08-document-index-reading-order.md](docs/00-foundation/08-document-index-reading-order.md)

## 开发状态

当前版本：**v0.1.0-alpha**

- [x] 文档编写（188 份）
- [x] 项目初始化
- [ ] Phase 1: Foundation 基础设施（进行中）
- [ ] Phase 2-17: 其他域实现

查看完整实现计划：[docs/superpowers/plans/2026-07-26-ai-town-implementation-plan.md](docs/superpowers/plans/2026-07-26-ai-town-implementation-plan.md)

## 许可证

本项目为个人学习项目。

## 致谢

- **DeepSeek**：提供强大的 AI 模型
- **Phaser**：优秀的 2D 游戏引擎
- **FastAPI**：现代化的 Python Web 框架
