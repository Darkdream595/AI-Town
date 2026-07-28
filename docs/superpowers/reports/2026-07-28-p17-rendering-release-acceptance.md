# P17 Rendering / Launcher Release 本地验收报告

日期：2026-07-28
分支：`codex/p17-rendering`

## 1. 结论

| 范围 | 状态 | 结论 |
|---|---|---|
| P17 纯逻辑渲染模块 | PASS | 14 个模块、协议门、Manifest 文件校验与测试已完成 |
| Phaser / DOM 运行时接入 | PASS（本地） | Crown Creek 底图、12 residents、HUD、EventBus、sprite mapping、safe area 与 fullscreen target 已实测 |
| 本机 Visual QA 基线 | PASS（非门禁） | 720p 与 1920×1080 CSS viewport 可见；无 console error；三段短窗口帧时间低于预算 |
| `REQ-RENDER-012` 正式性能门禁 | NOT RUN | 缺两台指定硬件、每台 3×60 s、raw trace、texture ledger 与完整 overlay 证据 |
| Launcher 核心生命周期 | PASS（测试） | random loopback port、single instance、instance.json、health polling、浏览器打开、安全关闭已实现 |
| Release 离线工具链 | PASS（测试） | one-folder spec、确定性组装、hash manifest、Secret/黑名单/篡改校验与可复现 ZIP 已实现 |
| 可分发 EXE / G9 | BLOCKED | 当前环境无 PyInstaller、无审核后的 `release/licenses`，且尚未在 clean Win10/Win11 VM 验收 |
| 托盘四项菜单 | NOT IMPLEMENTED | 当前仓库无离线可用托盘依赖；停止脚本与 `/shutdown` 可用，但不等价于规格中的托盘常驻 |

因此，本次可以关闭 P17 的本地实现与测试工作，但不能把正式 Visual QA gate
或 Release G9 标记为通过。

## 2. 自动化验证

| 命令 | 结果 |
|---|---|
| `npm test -- --run` | 21 files / 186 tests passed |
| `tsc --noEmit` | exit 0 |
| `tsc -p tsconfig.build.json` | exit 0 |
| `vite build` | exit 0；仅有 bundle >500 kB warning |
| `python -m pytest backend/tests -q` | 2217 passed |
| Release entry / packaging / launcher focused | 35 passed |
| scoped `ruff check` | exit 0 |
| 三份 PowerShell parser | 0 errors；UTF-8 BOM 兼容 Windows PowerShell 5.1 |
| `git diff --check` | exit 0 |

## 3. 浏览器运行时证据

Fixture：`qa.render.crown_creek_stress_v1`

- 精确 query 才启用，正常运行不会注入测试状态。
- `scene_id=scene.crown_creek_town`，revision 17，entity count 12。
- Event log 3 条，SHA-256：
  `3a97e9214ad8c80ce85180e46cb60e451d0ea51b840201a8ef1f36eaf60bfae6`。
- 720p：safe area 16 px；底图、12 residents 与 HUD 可见。
- 1920×1080 CSS px：safe area 24 px，text scale 1.25，compact=false。
- fullscreen button 的直接 target 为 `#game-shell`；真实 click 后
  `document.fullscreenElement.id=game-shell`，再次 click 可退出并恢复按钮状态。
- 浏览器 error/warning log：0。
- 1080p 本机短窗口三段基线：

| iteration | samples | p95 ms | p99 ms | max ms |
|---|---:|---:|---:|---:|
| 1 | 663 | 6.2 | 6.2 | 6.3 |
| 2 | 663 | 6.2 | 6.3 | 7.2 |
| 3 | 663 | 6.2 | 6.2 | 6.4 |

该数据来自 Windows 11 build 26200、Core i7-13700H、Intel Iris Xe /
RTX 4060 Laptop GPU、15.6 GiB RAM，不属于规范固定 Device profile I 或 D，
且每段不足 60 秒，只能作为本机回归基线。

Fixture 能力声明：

| capability | 状态 |
|---|---|
| ground_map | true |
| resident_sprites | true |
| resident_hud | true |
| heavy_rain | false |
| vfx | false |
| overlay | false |

这些 `false` 是明确的未实现/未接入证据，不得在正式 Visual QA 中当作通过。

## 4. Launcher / Release 已实现内容

- PyInstaller entrypoint 已委派 `src.release_entry.run_launcher`，不再走旧的固定端口
  `src.main`。
- 预绑定 `127.0.0.1:0` 并将实际 socket 交给 uvicorn，避免端口选择竞态。
- Windows mutex：`Local\AITown.Launcher.Singleton`。
- `%LOCALAPPDATA%\AI-Town\runtime\instance.json` 原子写入与退出清理。
- `/api/v1/health` 必须显式返回匹配的 `package_version`，缺失版本不再假成功。
- `/api/v1/health` 与 `/api/v1/meta` 暴露 package/build identity。
- `/api/v1/shutdown` 校验 loopback、Origin、Schema 与 shutdown token，重复调用幂等。
- `停止AI小镇.bat` 的 PowerShell 请求已补齐 Origin 与 `schema_version`。
- 固定 package layout、全文件 SHA-256 manifest、Secret/黑名单/额外文件/篡改/
  path budget 校验、固定时间戳 ZIP。
- 构建脚本缺 PyInstaller 时 fail-fast，绝不自动联网安装。

## 5. 外部门禁与下一步

1. 在隔离构建环境锁定并安装 PyInstaller；当前
   `python -m PyInstaller --version` 返回 module missing。
2. 准备并人工审核 `release/licenses/`，至少含
   `THIRD-PARTY-NOTICES.txt` 与逐依赖 License 文本。
3. clean checkout 连续构建两次，比对 ZIP SHA-256。
4. 在指定 Device profile I / D 分别执行 3×60 s 1080p 性能采集，
   补 raw trace、texture ledger、heavy rain/VFX/overlay 与 fullscreen 证据。
5. 在干净 Win10 / Win11 VM 运行双击启动、二次启动、中文空格路径、
   read-only package、graceful shutdown、crash recovery 与数据保留矩阵。
6. 若正式范围坚持托盘要求，引入经许可证审核且可离线打包的托盘实现，
   补四项菜单与 `WM_QUERYENDSESSION` 验收。
