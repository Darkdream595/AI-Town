---
doc_id: DOC-RELEASE-009
title: 自包含运行时与发布包
version: 1.0.0
status: approved-for-implementation
owner_domain: release
canonical_for:
  - release-package-layout
  - bundled-python-runtime
  - build-pipeline-integrity
depends_on:
  - DOC-FOUNDATION-001
  - DOC-RELEASE-001
  - DOC-RELEASE-002
  - DOC-RELEASE-008
requirements:
  - REQ-PRODUCT-001
  - REQ-PRODUCT-010
  - REQ-RELEASE-009
last_updated: 2026-07-26
---

# 自包含运行时与发布包

## 1. 目的

`REQ-RELEASE-009`：定义 Windows 发布包的目录布局、One-folder 自包含 Python 运行时的打包形态、构建期生成前端静态资源的边界、`release-manifest.json` 完整性与版本一致性校验，以及打包流水线的固定步骤，保证玩家零开发依赖、发布包内容可验证且必然对应构建源代码版本。

## 2. 非目标

本文件不定义 Launcher 运行行为（`DOC-RELEASE-008`）；不定义 G9 验收执行流程（`DOC-RELEASE-012`）；不定义美术资源内容规范（`DOC-RENDER-*`）；首版不做代码签名与安装器（MSI/Inno），SmartScreen 提示作为已知边界处理。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Release Package | 解压即用的 `AI-Town\` 目录树，无安装器 |
| One-folder Bundle | 后端 + 内嵌 CPython + 依赖的自包含目录 `runtime\backend\` |
| Build Pipeline | 从干净源码到发布包的固定顺序自动化步骤 |
| release-manifest.json | 包根清单：版本、build_id、逐文件 SHA-256 |
| Version Triplet | `package_version`（SemVer）、`build_id`（源码 commit 短哈希）、`build_time` |
| THIRD-PARTY-NOTICES | `licenses\` 下的依赖许可证汇总 |

## 4. 规则与不变量

- `RULE-RELEASE-063`：发布包目录结构固定为第 5.1 节布局；「安装」= 解压到任意用户可写目录，「卸载」= 删除该目录；运行期绝不写入包目录（承接 `RULE-RELEASE-001`，用户数据全部在 `%LOCALAPPDATA%\AI-Town`）。
- `RULE-RELEASE-064`：玩家环境零开发依赖：不要求安装 Python、Node.js、编译器、VC 运行库之外的任何组件；仅要求 Windows 10/11 x64 与一个默认浏览器（系统自带 Edge 即满足）；所需 VC 运行库 DLL 随 One-folder Bundle 附带。
- `RULE-RELEASE-065`：前端在构建期完成产物化：TypeScript/Phaser 源码经构建输出静态资源进入 `assets\web\`；发布包内不含 Node 运行时、`node_modules`、前端源码与 sourcemap；后端以只读静态目录同源提供（`DOC-BACKEND-001`）。
- `RULE-RELEASE-066`：包根必须含 `release-manifest.json`：Version Triplet + 逐文件相对路径与 SHA-256；`/api/health` 回报的 `package_version`/`build_id` 必须与 manifest 一致，三方（manifest、运行进程、构建源 commit）不一致即验收失败（防「发布包不是最新代码」）。
- `RULE-RELEASE-067`：Build Pipeline 步骤固定且全自动：clean checkout → 前端 build → 后端 One-folder Bundle → 资源与 licenses 汇总 → manifest 生成 → 包内自动化冒烟验证（`DOC-RELEASE-012` 的自动化子集）；任何一步失败不产出包，不允许手工向包内补文件。
- `RULE-RELEASE-068`：包内容黑名单：`.env`、`*.sqlite3`/`*.sqlite3-wal`/`*.sqlite3-shm`、`logs\`、`diagnostics\`、测试 fixture、开发依赖清单、`.git`、任何匹配 `old-dont-look*` 的路径、任何 Secret。打包末步执行黑名单与 Secret 扫描，命中即失败。
- `RULE-RELEASE-069`：`licenses\` 必须含全部第三方运行时依赖（Python 包、内嵌 CPython、Phaser 及前端依赖、字体与音频素材）的许可证文本与 `THIRD-PARTY-NOTICES.txt` 版本清单；许可证无法确认的依赖不得进包。
- `RULE-RELEASE-070`：玩家可读文件（`README-开始游戏.txt`）使用 UTF-8 with BOM 编码，Batch 脚本使用 UTF-8（`chcp 65001` 配套），保证中文 Windows 记事本双击可读、脚本输出不乱码。

## 5. 数据与接口

### 5.1 发布包布局

`DES-RELEASE-018`：

```text
AI-Town\
├─ 启动AI小镇.bat
├─ 停止AI小镇.bat
├─ README-开始游戏.txt          # 双击说明、F11 提示、数据位置、常见问题
├─ release-manifest.json
├─ runtime\
│  └─ backend\                  # One-folder Bundle
│     ├─ AI-Town.exe            # windowed 入口（Launcher + FastAPI 后端）
│     └─ _internal\             # 内嵌 CPython、依赖、后端代码、迁移清单
├─ assets\
│  ├─ web\                      # 构建期产出的前端静态资源
│  ├─ art\                      # 图集、瓦片、UI 图（DOC-RENDER-*）
│  └─ audio\
└─ licenses\
   ├─ THIRD-PARTY-NOTICES.txt
   └─ <依赖名>\LICENSE.txt
```

### 5.2 release-manifest.json

```json
{
  "manifest_format_version": 1,
  "product": "AI-Town",
  "package_version": "1.0.0",
  "build_id": "43d1e4a",
  "build_time": "2026-07-26T13:00:00.000Z",
  "target": "windows-x64",
  "migration_manifest_current": {"app": 1, "world": 3},
  "files": [
    {"path": "runtime/backend/AI-Town.exe", "sha256": "2222222222222222222222222222222222222222222222222222222222222222", "size_bytes": 18874368},
    {"path": "assets/web/index.html", "sha256": "3333333333333333333333333333333333333333333333333333333333333333", "size_bytes": 2048}
  ]
}
```

`files` 覆盖包内除 manifest 自身外的全部文件；`migration_manifest_current` 与 `DOC-RELEASE-002` 的注册清单 current 版本一致，供验收比对。

### 5.3 Build Pipeline 接口

`DES-RELEASE-019`：流水线以 PowerShell 脚本驱动，每步产出机器可读结果：

```text
build_frontend() -> assets\web\ + 前端构建报告
build_backend_bundle() -> runtime\backend\ (PyInstaller one-folder, windowed)
collect_assets_and_licenses() -> assets\ + licenses\
generate_manifest() -> release-manifest.json
verify_package(package_dir) -> PackageVerifyReport   # 黑名单、Secret 扫描、manifest 复算、冒烟启动
```

`verify_package` 的冒烟启动在临时 `%LOCALAPPDATA%` 重定向环境执行：双击链模拟 → health `ready` → 版本三方比对 → 干净关闭。

## 6. 正常流程

1. CI 从目标 commit 干净检出，记录 `build_id`。
2. 前端构建产出静态资源；后端 PyInstaller one-folder 产出 `AI-Town.exe` 与 `_internal\`。
3. 汇总 assets 与 licenses，生成 manifest。
4. `verify_package` 全绿后产出 `AI-Town-<package_version>.zip`。
5. 该 zip 交付 `DOC-RELEASE-012` 的 G9 真实环境验收。

## 7. 边界情况

- 玩家把包解压到含中文/空格路径或桌面：布局与 Batch 策略天然支持（`DOC-RELEASE-008`）；`runtime\backend\_internal` 深路径叠加长中文路径可能逼近 260 字符限制——打包验证断言包内最长相对路径 ≤ 120 字符，为玩家路径预留余量。
- SmartScreen 对未签名 exe 提示：README 提供「更多信息 → 仍要运行」指引；首版接受此边界，签名列入后续版本。
- 杀毒软件误报 PyInstaller 打包产物：README 提供排除目录指引；`verify_package` 在 Defender 默认设置环境执行以尽早暴露。
- 玩家在包目录只读介质（如挂载 ISO）运行：包目录只读不影响运行（`RULE-RELEASE-063`），用户数据在 `%LOCALAPPDATA%`。
- 升级：玩家解压新版本到新目录即可，旧目录可直接删除；数据兼容由 `DOC-RELEASE-002` 迁移保证；不支持包目录原地覆盖混合新旧文件——README 明确要求整目录替换。
- 32 位或 ARM Windows：不支持，启动时检测并给出明确提示（target 仅 windows-x64）。

## 8. 错误与降级

流水线任何一步失败即整体失败，无部分产出；`verify_package` 失败的包禁止进入验收与分发。运行期发现 manifest 与实际文件哈希不符（玩家改包或下载损坏）：启动继续但 `/api/health` 附 `package_integrity: "modified"`，G9 验收视为失败，玩家场景仅提示重新解压。

## 9. 安全与性能

- 包不含任何 Secret 与用户数据；manifest 哈希提供篡改可见性（非防篡改，首版无签名）。
- One-folder Bundle 启动到进程可服务目标 ≤ 10 s（不含世界恢复），配合 `DOC-RELEASE-008` 的 60 s 冷启动预算。
- 包体积预算：总 zip ≤ 800 MiB（美术与音频为主）；`verify_package` 报告体积构成 Top 10。
- 构建产物可复现性：同一 commit 两次构建的 manifest `files` 集合与各文件哈希一致（PyInstaller 时间戳归一化）。

## 10. 验收标准

- 全新 Windows 10 与 11 虚拟机（无 Python/Node/Git）解压后双击即玩（详细矩阵见 `DOC-RELEASE-012`）。
- manifest 复算全对；`/api/health` 三方版本一致。
- 黑名单扫描零命中；licenses 覆盖率 100%（依赖清单逐项对照）。
- 包内最长相对路径 ≤ 120 字符；`README-开始游戏.txt` 在记事本正确显示中文。
- 同 commit 重复构建 manifest 一致。

## 11. 测试追踪

| 测试 ID | 覆盖规则 |
|---|---|
| `TEST-RELEASE-033` | `RULE-RELEASE-063..065` 布局、零依赖与前端产物化 |
| `TEST-RELEASE-034` | `RULE-RELEASE-066..067` manifest 一致性与流水线完整性 |
| `TEST-RELEASE-035` | `RULE-RELEASE-068..069` 内容黑名单与许可证覆盖 |
| `TEST-RELEASE-036` | `RULE-RELEASE-070` 编码与中文可读性 |

## 12. 关联文档

- `DOC-RELEASE-008`：包内入口的运行行为
- `DOC-RELEASE-002`：迁移清单随包固化
- `DOC-RELEASE-012`：G9 真实双击验收
- `DOC-BACKEND-001`：同源静态资源服务
- `DOC-FOUNDATION-001`：`REQ-PRODUCT-001` 零依赖承诺
