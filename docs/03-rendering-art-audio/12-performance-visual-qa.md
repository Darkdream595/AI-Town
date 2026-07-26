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
| Texture budget | 单个 WorldScene 已加载 GPU texture 总量上限 256 MiB。 |
| Visual QA | 人工在真实浏览器运行中观察、操作并记录截图/录像的验收。 |
| Debug Overlay | 仅开发/QA 可启用的 Walkability、Collision、Semantic、depth overlay。 |

## 4. 规则与不变量

- `RULE-RENDER-034`：目标为常规 1080p 视窗 60 FPS；连续 10 秒 p95 frame time 必须 ≤16.67 ms，p99 ≤25 ms。
- `RULE-RENDER-035`：QA overlay 与 MAP 原始结构数据同源；它只能显示，不得改变规则或发布给普通玩家。
- `RULE-RENDER-036`：Visual QA 必须由真实交互场景、截图/录像和环境记录构成；自动截图只可作辅助证据。

## 5. 数据与接口

`DES-RENDER-012`：QA evidence 记录 `build_version`、browser/GPU、viewport、scene_id、revision、overlay set、操作步骤、期望/实际、截图或录像路径与审核人；性能 trace 同时记录 active entities/VFX/textures。

## 6. 正常流程

1. 在 720p、1080p、fullscreen 三种 viewport 跑指定世界与区域转场。
2. 依次检查五层画面、四向行走、建筑 stage、昼夜天气、dialogue/mayor、音频和 fallback。
3. 开启 overlay，沿关键通路、建筑边缘、Semantic Exit、树/水/悬崖逐项观察对齐。
4. 采集 trace、截图/录像；失败记录实际证据并阻断 release gate。

## 7. 边界情况

低端设备无法达标时记录硬件与 trace，按优先级降低 optional weather/VFX/分辨率；不得隐藏 Collision overlay 问题或把不可见资源缺失标为通过。

## 8. 错误与降级

纹理超过 256 MiB、p95 超预算或 WebGL context lost 时停止加载 optional group，清理 Warm Scene 后请求重建；仍失败则展示可恢复错误，不宣称通过 QA。

## 9. 安全与性能

帧数据不包含聊天私密内容或 Secret；真实 QA 在目标 Windows 浏览器与独显/集显代表设备各执行一次。

## 10. 验收标准

- `REQ-RENDER-012`：1080p 代表场景达到 60 FPS frame budget、texture ≤256 MiB，并具备真实 Visual QA 的截图/录像与 overlay 对齐证据。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-RENDER-012` | Performance trace gate、context-loss recovery、完整 Visual QA checklist 与人工证据审阅。 |

## 12. 关联文档

- `DOC-RENDER-003`：五层合成
- `DOC-RENDER-011`：Manifest/fallback
- `DOC-FOUNDATION-001`：发布级 Visual QA 要求
