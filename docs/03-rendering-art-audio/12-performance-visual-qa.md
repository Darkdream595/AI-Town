---
doc_id: DOC-RENDER-012
title: 渲染性能与真实 Visual QA
version: 1.0.0
status: approved-for-implementation
owner_domain: rendering-art-audio
canonical_for:
  - rendering-budgets
  - visual-qa-protocol
  - collision-overlay-inspection
depends_on:
  - DOC-RENDER-003
  - DOC-RENDER-009
  - DOC-RENDER-011
requirements:
  - REQ-RENDER-012
last_updated: 2026-07-26
---

# 渲染性能与真实 Visual QA

## 1. 目的

定义浏览器渲染预算、60 FPS 目标、视觉 QA 证据和 Collision/Walkability/Semantic overlay 的人工检查流程。

## 2. 非目标

不把静态 lint、HTTP 成功或 unit test 当作 Visual QA；不以性能为由删减权威碰撞与可访问性信息。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Frame budget | 60 FPS 对应 16.67 ms；以真实浏览器 Performance trace 测量。 |
| Texture budget | active WorldScene + UIScene + Warm Scene 的确定性预计 GPU allocation（含 10% safety margin）上限 256 MiB。 |
| Visual QA | 人工在真实浏览器运行中观察、操作并记录截图/录像的验收。 |
| Debug Overlay | 仅开发/QA 可启用的 Walkability、Collision、Semantic、depth overlay。 |
| Device profile I | Windows 10 22H2 build 19045、Core i5-8250U、Intel UHD 620、8 GiB RAM、1920×1080@60 Hz、OS scale 100%。 |
| Device profile D | Windows 11 23H2 build 22631、Ryzen 5 3600、GeForce GTX 1650 4 GiB、16 GiB RAM、1920×1080@60 Hz、OS scale 100%。 |

## 4. 规则与不变量

- `RULE-RENDER-034`：两个固定 device profile 均须在 headed Chromium Stable、`1920×1080 CSS px`、`deviceScaleFactor=1`、camera zoom `1.0` 下达到 60 FPS：每次 60 秒 measured window 的 p95 frame time ≤16.67 ms、p99 ≤25 ms，三次 iteration 必须分别通过。
- `RULE-RENDER-035`：QA overlay 与 MAP 原始结构数据同源；它只能显示，不得改变规则或发布给普通玩家。
- `RULE-RENDER-036`：Visual QA 必须由真实交互场景、截图/录像和环境记录构成；自动截图只可作辅助证据。Browser 的完整版本写入 `qa-runtime.json` 并在 release candidate 冻结；同一 Gate 只接受 exact full version，Chromium major 更新必须重新建立基线并重跑两个 profile。

## 5. 数据与接口

`DES-RENDER-012`：QA evidence 记录 `build_version`、OS build、CPU、GPU/driver、RAM、browser full version、viewport/DPR/camera zoom、scene_id、revision、overlay set、操作步骤、期望/实际、截图或录像路径与审核人；性能 trace 同时记录 active entities/VFX、texture allocation 明细与 fixture ID。

固定压力 fixture 为 `qa.render.crown_creek_stress_v1`：同一 Snapshot/Revision 中含 12 个可见居民、完整 Ground/Structure preload ring、heavy rain、昼夜 transition、resident HUD，并每 2 秒触发一次注册 VFX；输入 event log/asset manifest hash 必须随证据保存。Frame-time 取 measured window 内相邻 `requestAnimationFrame` presentation timestamps 的差值；按升序使用 nearest-rank `ceil(p*N)` 计算 p95/p99，不删除 GC、shader compilation 或长帧。

纹理计量按实际 WebGL internal format：未压缩 mip level 使用 `width × height × bytes_per_pixel`，所有 mip、array layer、cube face 与 framebuffer attachment 分别相加；block-compressed texture 使用每级 `ceil(width/block_width) × ceil(height/block_height) × block_bytes`，浏览器转码后按最终 internal format。共享 WebGLTexture 只计一次，atlas 计整张，active + Warm Scene + fallback 均计入；合计再乘 `1.10` safety margin 后必须 ≤`268435456` bytes。

## 6. 正常流程

1. 两个 device profile 清理浏览器 cache、关闭 DevTools/扩展和后台下载，加载相同 build/fixture；确认 `qa-runtime.json` exact browser version、1080p/DPR/zoom。
2. 每次 iteration 先运行 30 秒 warm-up（完成 asset load、shader compile 与一次 scene transfer），随后立即采集 60 秒 measured window；每 profile 独立重启浏览器并执行 3 次。
3. measured window 不排除任何帧；窗口失焦、OS update/通知遮挡或采集器失败使整个 iteration 无效并完整重跑，不得裁剪样本。
4. 另在 720p、1080p、fullscreen 三种 viewport 依次检查五层画面、四向行走、建筑 stage、昼夜天气、dialogue/mayor、音频和 fallback。
5. 开启 overlay，沿关键通路、建筑边缘、Semantic Exit、树/水/悬崖逐项观察对齐。
6. 保存三轮 raw trace、逐轮 p95/p99、纹理明细、截图/录像；任一 profile/iteration 失败即阻断 release gate。

## 7. 边界情况

Device profile 无法达标时记录完整 trace，按优先级降低 optional weather/VFX 后从 warm-up 重新执行三轮；不得更换 profile、降低 1080p/zoom、隐藏 Collision overlay 问题或把不可见资源缺失标为通过。

## 8. 错误与降级

纹理含 safety margin 后超过 256 MiB、任一轮 p95/p99 超预算或 WebGL context lost 时停止加载 optional group，清理 Warm Scene 后请求重建；运行时可恢复不等于 Gate 通过，必须重新执行完整三轮。

## 9. 安全与性能

帧数据不包含聊天私密内容或 Secret；真实 QA 在固定集显/独显 profile 各执行三轮，hardware/browser/driver 漂移必须作为新基线审计，不能与旧 trace 混算。

## 10. 验收标准

- `REQ-RENDER-012`：两个固定 device profile 的三次 1080p iteration 均达到 p95/p99 frame budget、texture estimate（含 mip/compression/10% margin）≤256 MiB，并具备 raw trace、真实 Visual QA 截图/录像与 overlay 对齐证据。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-RENDER-012` | 两 profile × 三 iteration 的 exact-browser Performance trace gate、nearest-rank 复算、texture estimator fixture、context-loss recovery、完整 Visual QA checklist 与人工证据审阅。 |

## 12. 关联文档

- `DOC-RENDER-003`：五层合成
- `DOC-RENDER-011`：Manifest/fallback
- `DOC-FOUNDATION-001`：发布级 Visual QA 要求
