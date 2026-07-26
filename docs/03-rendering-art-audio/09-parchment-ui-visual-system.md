---
doc_id: DOC-RENDER-009
title: 羊皮纸 UI 视觉系统
version: 1.0.0
status: approved-for-implementation
owner_domain: rendering-art-audio
canonical_for:
  - parchment-ui-tokens
  - resident-hud-layout
  - dialogue-and-mayor-layout
depends_on:
  - DOC-RENDER-001
  - DOC-FOUNDATION-002
requirements:
  - REQ-RENDER-009
last_updated: 2026-07-26
---

# 羊皮纸 UI 视觉系统

## 1. 目的

定义常驻 HUD、对话、镇长面板的羊皮纸视觉 token、布局和分辨率行为。

## 2. 非目标

不定义对话内容、镇长权限或输入协议；UI 不读取不被授权的居民记忆。

## 3. 术语与定义

| Token | 定义 |
|---|---|
| `ui.parchment.base` | 主面板纹理；内容层使用高对比深褐文字。 |
| `ui.ink.primary` | 正文颜色，最小对比度 4.5:1。 |
| Safe Area | 不被 viewport 边缘/浏览器 UI 遮挡的布局区域。 |
| DOM overlay | 与 Phaser canvas 同属 `#game-shell` 的绝对定位 HTML 层，承载 selectable text、buttons、forms 与 accessibility tree。 |
| `PhaserDomBridge` | UIScene 管理 DOM projection、viewport 与 input gate 的单向 bridge；DOM event 不直接修改世界。 |

## 4. 规则与不变量

- `RULE-RENDER-025`：UIScene 是常驻 orchestrator：Canvas 只绘制非交互装饰/世界提示，HUD、Dialogue、Mayor 的正文、按钮和表单必须渲染到 `#ui-overlay` DOM；overlay 使用屏幕空间和 Safe Area，不随世界相机缩放、天气 tint 或 map occluder 改变。
- `RULE-RENDER-026`：720p 为最低设计目标：HUD 单行不截断、对话最多 3 行正文后滚动；1080p 可扩展留白但不放大文本超过 1.25×。
- `RULE-RENDER-027`：首次进入显示 F11 与可点击 fullscreen 按钮；Fullscreen API 仅在用户手势中对 `#game-shell` 调用，使 canvas 与 DOM overlay 同时进入 fullscreen。DOM focus 激活时 `UiInputGate` 必须暂停对应 Phaser keyboard/pointer action，避免一次输入同时作用于 UI 与世界。

## 5. 数据与接口

`DES-RENDER-009`：UI token registry 包含 `asset_id`、颜色、字体栈、8 px spacing scale、状态色与 fallback。Mayor layout 采用左侧治理列表、右侧详情、底部确认栏；Resident HUD 固定左上，Dialogue 固定底部居中。

```text
#game-shell (fullscreen target, position: relative)
├─ canvas[data-phaser-game] (aria-hidden="true")
└─ #ui-overlay (position: absolute; inset: 0)
   ├─ [data-ui="resident-hud"]
   ├─ [data-ui="dialogue"] role="dialog"
   └─ [data-ui="mayor"] role="dialog"
```

`PhaserDomBridge` 只接受同 Revision 的 `UiRenderProjection`，通过 keyed DOM patch 更新 `#ui-overlay`。交互 DOM event 被转换为 Client Command 后走 Backend validation；bridge 不调用 Domain API。焦点策略：打开 modal 保存 `document.activeElement`、聚焦首个可操作元素、Tab/Shift+Tab 被 focus trap 限定；关闭时恢复原元素，元素已不存在则聚焦 `#game-shell`。非 modal HUD 不抢焦点。

## 6. 正常流程

1. `BootScene` 只创建一次 `#game-shell/#ui-overlay`；UIScene create 时 attach `PhaserDomBridge`、`ResizeObserver`、`fullscreenchange` 与 focus/input listeners。
2. 根据 viewport 计算 16 px（720p）或 24 px（1080p）Safe Area，加载 resident HUD、dialogue 和 mayor panel 的只读 projection。
3. DOM `keydown/pointerdown` 先经过 `UiInputGate`：modal 内事件 `preventDefault`/`stopPropagation` 后由 bridge 生成 command；没有 active DOM interaction 时 Phaser Input 才接收世界控制。
4. `ResizeObserver` 或 `fullscreenchange` 在同一 animation frame 合并为一次 layout transaction：先读取 `#game-shell` content box，再调用 Phaser Scale resize，最后更新 DOM Safe Area；不重建 WorldScene。
5. scene transfer 不销毁 UIScene/overlay；应用退出时 UIScene shutdown 必须 detach 全部 listener、observer 与 focus trap 并移除 overlay。

## 7. 边界情况

窄窗口小于 1280×720 时显示“建议全屏或 720p 以上”的非阻塞提示，并采用紧凑布局；不得隐藏退出、确认或错误信息。fullscreen 请求被拒绝时保持当前 focus 和 DOM layout，仅显示状态提示，不重试 API。

## 8. 错误与降级

羊皮纸纹理/字体失败时使用纯色面板与系统 sans-serif，保留对比度、焦点顺序与所有操作。bridge projection Revision 有缺口时保留上一 DOM tree 并请求 Snapshot，不混合新旧 panel。

## 9. 安全与性能

DOM overlay 保证键盘焦点可见、文字可选择、按钮有 accessible name/ARIA 状态；Phaser canvas 标为 `aria-hidden` 且不复制 DOM 正文。面板纹理可共享，禁止每帧重绘 parchment noise。

## 10. 验收标准

- `REQ-RENDER-009`：720p、1080p、fullscreen 与 fallback 字体下 HUD/对话/镇长 DOM layout 无重叠，可选择文本、ARIA、focus trap、input gate、resize/fullscreen 生命周期均可键盘完成和清理。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-RENDER-009` | 四种 viewport 的视觉回归、selectable text/accessibility tree、focus trap/input suppression/listener cleanup、fullscreen target 与 user-gesture E2E。 |

## 12. 关联文档

- `DOC-RENDER-001`：UIScene
- `DOC-RENDER-012`：Visual QA
- 非 direct owner：Player/Dialogue 的已授权只读字段由 Backend/Orchestrator UI projection 提供。
