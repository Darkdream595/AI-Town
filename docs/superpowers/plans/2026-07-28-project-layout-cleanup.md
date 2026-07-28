# AI Town 项目目录与发布入口整理实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用
> superpowers:subagent-driven-development（推荐）或
> superpowers:executing-plans 逐任务实现此计划。步骤使用复选框
>（`- [ ]`）语法来跟踪进度。

**目标：** 保持前后端业务源码不变，将开发入口、发布构建源码、玩家交付物和
本机资料分层，并让玩家通过发布包顶层 `AI-Town.exe` 启动游戏。

**架构：** PyInstaller 继续使用 one-folder 模式，但整个 backend bundle 直接
组装到玩家包根目录；`release/` 只保存构建定义，默认输出改到根 `dist/`。
本机资料移动到 Git 忽略的 `_local/`，移动前后以文件数和字节数校验。

**技术栈：** Python 3.11、PyInstaller、PowerShell 5.1、FastAPI/Uvicorn、
TypeScript/Vite、pytest、Vitest。

---

## 文件结构与职责

- 修改 `backend/src/release_entry.py`：冻结环境下从顶层 EXE 解析 package root。
- 修改 `tools/release/backend_entry.py`：PyInstaller entrypoint 使用同一布局。
- 修改 `tools/release/release_packaging.py`：将 backend bundle 组装到玩家包顶层。
- 修改 `release/build-release.ps1`：默认输出从 `release/out/` 改为根 `dist/`。
- 删除 `release/out/.gitignore`：`release/` 不再包含输出目录。
- 删除 `release/package_skeleton/启动AI小镇.bat`：玩家不再通过 BAT 启动。
- 移动 `release/package_skeleton/停止AI小镇.bat` 到
  `release/package_skeleton/关闭AI-Town.bat`：仅保留明确的关闭入口。
- 修改 `release/package_skeleton/README-开始游戏.txt`：说明顶层 EXE 启动。
- 移动 `启动AI小镇.bat` 到 `tools/dev/启动开发环境.bat`：明确开发用途。
- 修改 `.gitignore`：忽略 `_local/`、`dist/` 和视觉原型。
- 修改 `README.md`：重写 GitHub 项目主页。
- 修改 `backend/tests/test_release_entry.py`：验证顶层 frozen package root。
- 修改 `backend/tests/test_release_packaging_tools.py`：验证新发布 layout 与默认输出。

### 任务 1：用测试锁定顶层 EXE 布局

**文件：**

- 修改：`backend/tests/test_release_entry.py`
- 修改：`backend/tests/test_release_packaging_tools.py`

- [ ] **步骤 1：修改 frozen package root 测试**

在 `backend/tests/test_release_entry.py` 中将 frozen EXE 示例设为玩家包顶层：

```python
def test_package_root_uses_frozen_executable_parent(monkeypatch, tmp_path):
    executable = tmp_path / "AI-Town" / "AI-Town.exe"
    monkeypatch.setattr(release_entry.sys, "frozen", True, raising=False)
    monkeypatch.setattr(release_entry.sys, "executable", str(executable))

    assert release_entry._package_root() == executable.parent
```

- [ ] **步骤 2：修改 packaging fixture 与 layout 断言**

`_make_sources()` 不再创建 `启动AI小镇.bat`，只创建：

```python
(skeleton / "关闭AI-Town.bat").write_text(
    "@echo off\nchcp 65001 >nul\n", encoding="utf-8"
)
```

组装断言改为：

```python
assert (package_dir / "AI-Town.exe").is_file()
assert (package_dir / "_internal" / "python311.dll").is_file()
assert not (package_dir / "runtime" / "backend").exists()
assert not (package_dir / "启动AI小镇.bat").exists()
assert (package_dir / "关闭AI-Town.bat").is_file()
```

- [ ] **步骤 3：运行测试确认旧实现失败**

运行：

```powershell
cd backend
.\venv\Scripts\python.exe -m pytest `
  tests/test_release_entry.py `
  tests/test_release_packaging_tools.py -q
```

预期：新 layout 断言失败，报告 EXE 仍位于 `runtime/backend/`。

### 任务 2：实现玩家包顶层 EXE

**文件：**

- 修改：`backend/src/release_entry.py`
- 修改：`tools/release/backend_entry.py`
- 修改：`tools/release/release_packaging.py`
- 修改：`release/package_skeleton/README-开始游戏.txt`
- 移动：`release/package_skeleton/停止AI小镇.bat` →
  `release/package_skeleton/关闭AI-Town.bat`
- 删除：`release/package_skeleton/启动AI小镇.bat`

- [ ] **步骤 1：统一 frozen package root**

两个 `_package_root()` 在 frozen 模式下均返回：

```python
if getattr(sys, "frozen", False):
    return Path(sys.executable).resolve().parent
```

非 frozen 模式仍返回仓库根目录。

- [ ] **步骤 2：修改固定 layout**

`tools/release/release_packaging.py` 的必要路径改为：

```python
REQUIRED_PATHS = (
    "AI-Town.exe",
    "_internal/python311.dll",
    "关闭AI-Town.bat",
    "README-开始游戏.txt",
    "runtime/stop-ai-town.ps1",
    "assets/web/index.html",
    "licenses/THIRD-PARTY-NOTICES.txt",
)
```

backend bundle 直接复制到 staging：

```python
_copy_tree(skeleton, staging)
_copy_tree(backend_bundle, staging)
_copy_tree(frontend_dist, staging / "assets" / "web")
_copy_tree(licenses, staging / "licenses")
```

- [ ] **步骤 3：重命名关闭脚本并更新玩家说明**

使用 `git mv`：

```powershell
git mv -- `
  "release/package_skeleton/停止AI小镇.bat" `
  "release/package_skeleton/关闭AI-Town.bat"
git rm -- "release/package_skeleton/启动AI小镇.bat"
```

README 的启动与关闭说明固定为：

```text
启动：双击当前目录中的 AI-Town.exe。
全屏：浏览器打开后按 F11，或点击游戏内全屏按钮。
关闭：双击当前目录中的 关闭AI-Town.bat。
```

- [ ] **步骤 4：运行 focused tests**

运行：

```powershell
cd backend
.\venv\Scripts\python.exe -m pytest `
  tests/test_release_entry.py `
  tests/test_release_packaging_tools.py `
  tests/test_release_launcher.py -q
```

预期：全部通过。

- [ ] **步骤 5：提交 release layout**

仅暂存上述文件并确认：

```powershell
git diff --cached --name-only
git commit -m "refactor(发布): 将玩家 EXE 移到发布包顶层"
```

### 任务 3：分离 release 构建源码与 dist 产物

**文件：**

- 修改：`release/build-release.ps1`
- 删除：`release/out/.gitignore`
- 修改：`backend/tests/test_release_packaging_tools.py`
- 修改：`.gitignore`

- [ ] **步骤 1：添加默认输出路径测试**

静态测试必须断言：

```python
assert 'Join-Path $projectRoot "dist"' in script
assert 'Join-Path $PSScriptRoot "out"' not in script
```

- [ ] **步骤 2：确认测试先失败**

运行：

```powershell
cd backend
.\venv\Scripts\python.exe -m pytest `
  tests/test_release_packaging_tools.py::test_spec_and_build_script_encode_offline_onefolder_pipeline `
  -q
```

预期：FAIL，仍找到 `release/out`。

- [ ] **步骤 3：修改默认输出并更新 ignore**

`release/build-release.ps1`：

```powershell
$output = if ($OutputRoot) {
    $OutputRoot
} else {
    Join-Path $projectRoot "dist"
}
```

`.gitignore` 增加：

```gitignore
/_local/
/.superpowers/brainstorm/
/dist/
```

删除已跟踪的 `release/out/.gitignore`。

- [ ] **步骤 4：验证 PowerShell 与测试**

运行：

```powershell
$errors = $null
[System.Management.Automation.Language.Parser]::ParseFile(
  (Resolve-Path "release/build-release.ps1"),
  [ref]$null,
  [ref]$errors
) | Out-Null
if ($errors.Count) { throw $errors }

cd backend
.\venv\Scripts\python.exe -m pytest tests/test_release_packaging_tools.py -q
```

预期：PowerShell parser 0 errors，pytest 全部通过。

- [ ] **步骤 5：提交输出目录调整**

```powershell
git commit -m "chore(发布): 分离构建源码与 dist 产物"
```

### 任务 4：整理开发入口与本机资料

**文件：**

- 移动：`启动AI小镇.bat` → `tools/dev/启动开发环境.bat`
- 本机移动：`backups/`、`old-dont-look/`、`session/`、
  `testing-self-study/` → `_local/`

- [ ] **步骤 1：记录四个源目录校验值**

对每个源目录记录文件数量与字节数：

```powershell
$sourcePaths = @(
  "backups",
  "old-dont-look",
  "session",
  "testing-self-study"
)
$before = foreach ($relativePath in $sourcePaths) {
  $resolved = (Resolve-Path -LiteralPath $relativePath).Path
  $files = @(Get-ChildItem -LiteralPath $resolved -Recurse -File -Force)
  [pscustomobject]@{
    Source = $relativePath
    Files = $files.Count
    Bytes = ($files | Measure-Object Length -Sum).Sum
  }
}
$before | ConvertTo-Json
```

预期：四条记录均生成，所有绝对路径位于项目根目录。

- [ ] **步骤 2：预检目标冲突**

目标映射：

```text
backups            -> _local/backups
old-dont-look      -> _local/old
session            -> _local/sessions
testing-self-study -> _local/experiments/testing-self-study
```

任何目标存在时立即停止，不覆盖、不合并。

- [ ] **步骤 3：移动开发 BAT**

```powershell
New-Item -ItemType Directory -Path "tools/dev" -Force | Out-Null
git mv -- "启动AI小镇.bat" "tools/dev/启动开发环境.bat"
```

将标题与输出文案中的“游戏启动器”改为“开发环境启动器”，保留安装依赖和
启动 Vite/FastAPI 的现有行为。

- [ ] **步骤 4：安全移动本机资料**

先创建明确目标父目录，再逐项使用同一个 PowerShell 进程执行
`Move-Item -LiteralPath`。移动前再次确认每个源、目标的绝对路径都位于
项目根目录，并且目标不存在。

- [ ] **步骤 5：移动后校验**

按步骤 1 的逻辑统计四个目标目录。预期每项 `Files` 和 `Bytes` 与移动前完全
一致；四个源路径均不存在。

- [ ] **步骤 6：提交开发入口**

`_local/` 不得出现在 staged diff：

```powershell
git add -- "tools/dev/启动开发环境.bat"
git add -u -- "启动AI小镇.bat"
git diff --cached --name-only
git commit -m "chore(开发): 明确开发启动脚本位置"
```

### 任务 5：重写 GitHub README

**文件：**

- 修改：`README.md`

- [ ] **步骤 1：用当前事实重写 README**

结构固定为：

```markdown
<div align="center">
  <h1>AI Town · AI 小镇</h1>
  <p>本地运行的中世纪奇幻 AI 居民模拟游戏</p>
</div>

![王冠溪镇](frontend/public/assets/maps/crown_creek_town_base.png)

## 游戏特色
## 下载与游玩
## 开发环境
## 技术架构
## 项目结构
## 测试与构建
## 数据与隐私
## 许可证
```

玩家说明只写：

```text
解压 AI-Town-<version>.zip。
双击顶层 AI-Town.exe。
浏览器打开后按 F11 或点击全屏按钮。
退出时运行 关闭AI-Town.bat。
```

- [ ] **步骤 2：事实校验**

README 不得包含：

```text
Phase 1 进行中
双击 启动AI小镇.bat 游玩
必须安装 Python/Node 才能运行发布包
已通过 G9
```

所有命令必须对应当前 `package.json`、requirements 和 build script。

- [ ] **步骤 3：检查 Markdown 链接和资源**

运行：

```powershell
Test-Path "frontend/public/assets/maps/crown_creek_town_base.png"
Select-String -Path README.md -Pattern "Phase 1|启动AI小镇\.bat|G9"
```

预期：图片存在；过时词条无命中。

- [ ] **步骤 4：提交 README**

```powershell
git add -- README.md
git commit -m "docs(README): 重写项目主页与启动说明"
```

### 任务 6：完整构建、真实启动与收尾

**文件：**

- 生成但不提交：`dist/AI-Town/`
- 生成但不提交：`dist/AI-Town-0.1.0.zip`

- [ ] **步骤 1：运行完整自动化测试**

并行运行：

```powershell
cd backend
$env:PYTHONUTF8 = "1"
.\venv\Scripts\python.exe -m pytest tests -q
```

```powershell
cd frontend
npm test -- --run
npm run build
```

预期：pytest、Vitest 与 Vite build 全部退出 0。

- [ ] **步骤 2：从 clean commit 构建**

```powershell
$buildId = (git rev-parse --short HEAD).Trim()
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File release/build-release.ps1 `
  -PackageVersion 0.1.0 `
  -BuildId $buildId
```

预期：`dist/AI-Town/AI-Town.exe` 与 ZIP 生成，离线 verify 为 `ok=true`。

- [ ] **步骤 3：真实 EXE 冒烟**

启动 `dist/AI-Town/AI-Town.exe`，读取
`%LOCALAPPDATA%\AI-Town\runtime\instance.json`，请求：

```text
GET http://127.0.0.1:<port>/api/v1/health
```

预期：

```json
{
  "process_state": "ready",
  "package_version": "0.1.0",
  "package_integrity": "verified"
}
```

运行 `dist/AI-Town/关闭AI-Town.bat` 后，进程在 15 秒内退出且
`instance.json` 被清理。

- [ ] **步骤 4：验证最终目录和 Git 边界**

```powershell
Test-Path "启动AI小镇.bat"                         # False
Test-Path "release/out"                           # False
Test-Path "dist/AI-Town/AI-Town.exe"              # True
Test-Path "dist/AI-Town/runtime/backend"           # False
git status --short
git check-ignore -v _local dist .superpowers/brainstorm
```

预期：`_local/`、`dist/`、视觉原型不出现在 Git status；工作树无意外改动。

- [ ] **步骤 5：最终审查并推送**

运行 scoped `ruff check`、PowerShell parser、`git diff --check`，检查提交历史
仅包含计划内文件。若远程仍为 `origin/main`，仅推送 `main`，不使用
`--all` 或 `--mirror`。
