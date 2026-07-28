# AI Town 项目目录与发布入口整理设计

日期：2026-07-28

## 1. 目标

在不修改前后端业务源码的前提下，明确区分开发环境、发布构建源码、
最终玩家交付物和本机资料。

玩家解压发布包后，应直接看到并双击顶层 `AI-Town.exe`。项目根目录不再
使用名称含糊的 `启动AI小镇.bat` 作为入口。

## 2. 不变范围

以下目录不移动、不重构、不修改业务实现：

- `backend/`
- `frontend/`
- `assets/`
- `shared/`
- 现有业务和设计文档；仅新增本整理规格及后续必要的发布说明

本次不新增托盘、安装器、Electron 外壳或 G9 正式发行门禁。

## 3. 根目录目标结构

```text
AI-Town/
├─ README.md
├─ backend/
├─ frontend/
├─ assets/
├─ shared/
├─ docs/
├─ tools/
│  ├─ dev/
│  │  └─ 启动开发环境.bat
│  └─ release/
├─ release/
│  ├─ AI-Town.spec
│  ├─ build-release.ps1
│  ├─ verify-release.ps1
│  ├─ licenses/
│  └─ package_skeleton/
│     ├─ 关闭AI-Town.bat
│     └─ README-开始游戏.txt
├─ dist/
│  ├─ AI-Town-<version>.zip
│  └─ AI-Town/
│     ├─ AI-Town.exe
│     ├─ _internal/
│     ├─ assets/
│     ├─ runtime/
│     ├─ licenses/
│     ├─ 关闭AI-Town.bat
│     └─ README-开始游戏.txt
└─ _local/
   ├─ backups/
   ├─ old/
   ├─ sessions/
   └─ experiments/
```

`dist/` 与 `_local/` 均为本机目录，加入 Git ignore，不提交构建产物或用户资料。

## 4. 精确移动映射

| 当前路径 | 目标路径 | 处理 |
|---|---|---|
| `启动AI小镇.bat` | `tools/dev/启动开发环境.bat` | 保留开发能力，名称明确 |
| `release/out/` | `dist/` | 发布输出与构建源码分离 |
| `backups/` | `_local/backups/` | 完整移动，不删除 |
| `old-dont-look/` | `_local/old/` | 完整移动，不删除 |
| `session/` | `_local/sessions/` | 完整移动，不删除 |
| `testing-self-study/` | `_local/experiments/testing-self-study/` | 完整移动，不删除 |

若目标已存在同名内容，停止移动并报告冲突，不覆盖、不合并、不删除。

## 5. 发布包布局

当前真正的程序位于 `runtime/backend/AI-Town.exe`。整理后，将 PyInstaller
one-folder bundle 的 `AI-Town.exe` 与 `_internal/` 一起放到发布包顶层，
而不是单独复制 EXE。

```diff
 AI-Town/
-├─ 启动AI小镇.bat
-└─ runtime/backend/
-   ├─ AI-Town.exe
-   └─ _internal/
+├─ AI-Town.exe
+├─ _internal/
+├─ assets/
+├─ runtime/
+├─ licenses/
+├─ 关闭AI-Town.bat
+└─ README-开始游戏.txt
```

Launcher 的 package root 解析与 PyInstaller 组装逻辑必须同步调整，确保：

- 双击顶层 EXE 后启动随机 loopback 端口；
- 默认浏览器自动打开；
- 前端静态资源可加载；
- `%LOCALAPPDATA%\AI-Town\` 存档路径不变；
- `关闭AI-Town.bat` 可安全停止后台进程。

## 6. README 设计

根 `README.md` 重写为 GitHub 项目主页，使用准确、简洁的结构：

1. 项目标题、简短定位和当前状态；
2. 游戏截图或已有项目视觉素材；
3. 核心能力；
4. 玩家下载与启动方式；
5. 开发环境启动方式；
6. 技术栈与简化项目结构；
7. 测试和构建命令；
8. 数据目录、许可证与第三方声明。

README 不再声称 Phase 1 正在进行，不把开发 BAT 描述为玩家启动方式，
不添加未经配置的 CI、coverage 或下载量徽章。

## 7. 安全与回滚

- 移动前逐项解析绝对路径，确认源路径位于项目根目录内。
- `_local/` 迁移只执行同文件系统移动，不进行递归删除。
- 不使用 `git add .` 或 `git add -A`。
- `_local/`、`dist/` 和视觉原型不进入提交。
- 移动失败时保留已移动清单；已移动目录可按映射反向移动恢复。
- 发现活动进程占用或目标冲突时停止，不强杀无关进程。

## 8. 验收标准

- 根目录不再存在 `启动AI小镇.bat`、`release/out/` 及四个散落资料目录。
- `_local/` 中四类资料均存在，移动前后文件数量与总字节数一致。
- `release/` 仅保存发布构建源码、模板和许可证。
- `dist/AI-Town/AI-Town.exe` 位于玩家包顶层，真实启动与安全停止通过。
- ZIP 解压后的根目录结构与本规格一致。
- 新 README 与当前实现、测试和发布方式一致。
- 后端、前端及 release focused 自动化测试通过。
- 提交中不包含 `_local/`、`dist/` 或 `testing-self-study` 内容。
