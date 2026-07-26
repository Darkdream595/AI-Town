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
  - DOC-PLAYER-010
  - DOC-DIALOGUE-001
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

## 4. 规则与不变量

- `RULE-RENDER-025`：UIScene 使用屏幕空间和 Safe Area，不随世界相机缩放、天气 tint 或 map occluder 改变。
- `RULE-RENDER-026`：720p 为最低设计目标：HUD 单行不截断、对话最多 3 行正文后滚动；1080p 可扩展留白但不放大文本超过 1.25×。
- `RULE-RENDER-027`：首次进入显示 F11 与可点击 fullscreen 按钮；Fullscreen API 仅在用户手势中调用。

## 5. 数据与接口

`DES-RENDER-009`：UI token registry 包含 `asset_id`、颜色、字体栈、8 px spacing scale、状态色与 fallback。Mayor layout 采用左侧治理列表、右侧详情、底部确认栏；Resident HUD 固定左上，Dialogue 固定底部居中。

## 6. 正常流程

1. 根据 viewport 计算 16 px（720p）或 24 px（1080p）Safe Area。
2. 加载 resident HUD、dialogue 和 mayor panel 的只读 projection。
3. viewport/fullscreen change 后重新排版，不重建 WorldScene。

## 7. 边界情况

窄窗口小于 1280×720 时显示“建议全屏或 720p 以上”的非阻塞提示，并采用紧凑布局；不得隐藏退出、确认或错误信息。

## 8. 错误与降级

羊皮纸纹理/字体失败时使用纯色面板与系统 sans-serif，保留对比度、焦点顺序与所有操作。

## 9. 安全与性能

键盘焦点可见、文字可选择、按钮有 aria 标签；面板纹理可共享，禁止每帧重绘 parchment noise。

## 10. 验收标准

- `REQ-RENDER-009`：720p、1080p、fullscreen 与 fallback 字体下 HUD/对话/镇长布局无重叠、可键盘完成操作。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-RENDER-009` | 四种 viewport 的视觉回归、focus order、fullscreen user-gesture E2E。 |

## 12. 关联文档

- `DOC-RENDER-001`：UIScene
- `DOC-RENDER-012`：Visual QA
