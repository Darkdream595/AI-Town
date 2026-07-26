---
doc_id: DOC-PLAYER-011
title: 输入提示、按键重绑定与无障碍
version: 1.0.0
status: approved-for-implementation
owner_domain: player
canonical_for:
  - player-input-map
  - contextual-input-guidance
  - input-rebinding
  - player-accessibility
depends_on:
  - DOC-RENDER-007
  - DOC-RENDER-009
  - DOC-PLAYER-002
  - DOC-PLAYER-003
  - DOC-PLAYER-010
requirements:
  - REQ-PLAYER-011
last_updated: 2026-07-26
---

# 输入提示、按键重绑定与无障碍

## 1. 目的

`REQ-PLAYER-011`：建立 context-aware 输入映射、屏幕按键提示、冲突安全的重绑定、焦点优先级和无障碍替代，使键盘玩家在 Resident、Dialogue、Mayor、Combat 与 modal 间不会误操作。

## 2. 非目标

本文不定义 gamepad 首版支持、移动端触控、语音输入、浏览器保留键行为或具体视觉 token。RENDER 拥有样式，PLAYER 拥有 action/context/key mapping。

## 3. 默认输入映射

| Context | Action | 默认输入 | 可重绑定 |
|---|---|---|---:|
| `resident_world` | move | `W/A/S/D` | 是 |
| `resident_world` | fast_walk | `Shift` | 是 |
| `resident_world` | interact | `E` | 是 |
| `resident_world` | dialogue_input | `Enter` | 是 |
| `resident_world` | inventory/journal/map | `I/J/M` | 是 |
| `resident_world` | switch_mode | `Tab` | 是，但不能覆盖 focus navigation |
| `global` | pause_or_back | `Escape` | 否 |
| `global` | browser_fullscreen_hint | `F11` | 否，仅提示 |
| `mayor_canvas` | pan | `W/A/S/D` 或方向键 | 是 |
| `modal/dialogue/mayor_form` | focus navigation | `Tab/Shift+Tab` | 否 |
| `dialogue_input` | submit/newline | `Enter/Shift+Enter` | 可交换提交策略 |

## 4. 规则与不变量

- `RULE-PLAYER-052`：输入按 context 优先级解析：`system/recovery > modal DOM > text input > combat turn > mayor canvas > resident world > global hint`。
- `RULE-PLAYER-053`：DOM focus 下 `Tab/Shift+Tab` 永远用于 focus navigation，不能切换 Mayor；textbox 中 WASD/快捷键不得驱动世界。
- `RULE-PLAYER-054`：同一 context 内两个不可组合 action 不得绑定同一 chord；保存前必须显示冲突并要求解决。
- `RULE-PLAYER-055`：`Escape`、浏览器 `F11`、确认/取消安全路径和至少一种 focus navigation 不可被移除；重绑定后必须仍可用键盘恢复默认。
- `RULE-PLAYER-056`：Reduced Motion、色觉/高对比、字幕/文本提示和 camera shake 开关改变表现，不改变规则时间、命中、导航或可见事实。

## 5. InputMap Schema

```json
{
  "schema_version": 1,
  "profile_id": "default.keyboard.v1",
  "bindings": [
    {
      "context": "resident_world",
      "action_id": "move_up",
      "chords": [
        {
          "code": "KeyW",
          "modifiers": []
        }
      ]
    },
    {
      "context": "resident_world",
      "action_id": "switch_mode",
      "chords": [
        {
          "code": "Tab",
          "modifiers": []
        }
      ]
    }
  ],
  "preferences": {
    "reduced_motion": false,
    "high_contrast": false,
    "camera_shake_scale": 1,
    "hold_to_fast_walk": true,
    "dialogue_enter_submits": true
  }
}
```

使用 `KeyboardEvent.code` 保存物理位置，并同时显示本地化 label；`modifiers` 仅 `Alt/Control/Meta/Shift` 且排序固定。未知 action/context/字段拒绝，旧版本通过显式 upcaster。

## 6. 输入提示

底部提示来自当前 `InputContext + CapabilityProjection + InputMap`，格式为“按键 — 操作”，最多显示 6 个高相关项，并提供“全部控制”入口。禁用能力可隐藏或显示带安全 reason 的 disabled hint；不能泄露 secret。首次进入、首次打开 Dialogue、首次切换 Mayor 和首次失败 fullscreen 分别提供一次可再次打开的 onboarding。

## 7. 重绑定流程

1. 打开设置后获取 `settings_input` modal context 并清空世界 latch。
2. 选择 action，进入 capture；忽略仅 modifier、系统组合和 key repeat。
3. 规范化 chord，检查 context 冲突、保留键、安全路径和跨 layout label。
4. 冲突时提供交换、取消或恢复默认；禁止静默覆盖。
5. 通过 validator 后原子保存 profile version；立即更新提示。
6. write 失败保留旧 profile 并显示可恢复错误，不留下半套映射。

## 8. 无障碍要求

所有 DOM button/input 具有可读 name、可见 focus、逻辑 tab order、错误关联和 screen-reader live region；modal 使用 focus trap 并在关闭后恢复合法 focus。重要音频事件同时提供文本/图标，不能只靠颜色。Reduced Motion 禁用 camera shake、闪白和非必要 tween，保留静态方向/危险提示。持续按键可配置 hold/toggle，但 toggle 在 blur/modal/mode change 时自动释放。

## 9. 边界情况与恢复

- IME composing 时 Enter 不提交，等待 `compositionend`。
- 长按 key repeat 不重复触发 toggle/modal；移动按 pressed-state 采样。
- 键盘布局变化只改变显示 label，不改已保存 physical `code`；用户可重设。
- profile JSON 损坏时隔离坏文件、加载内置 default，并提供恢复提示。
- 所有键被误配不可达时，启动时 `Ctrl+Alt+Backspace` 仅打开“恢复默认输入”确认页；不执行世界 mutation。

## 10. 验收标准

- Resident/Dialogue/Mayor/Combat/modal context 的相同按键不会双重触发。
- `Tab` 在 world 切换模式、在 DOM 只移动焦点。
- 冲突、保留键、write failure、坏 profile 与恢复默认均确定。
- 键盘完成首次全屏提示、对话、Mayor 表单、设置和退出。
- Reduced Motion/高对比/文本替代不改变 Domain 结果。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-PLAYER-041` | context priority、UiInputGate 与 stuck-key clearing |
| `TEST-PLAYER-042` | key rebinding/conflict/reserved/recovery |
| `TEST-PLAYER-043` | IME、repeat、layout label 与 hold/toggle |
| `TEST-PLAYER-044` | keyboard-only、screen reader、contrast/reduced motion |

## 12. 关联文档

- `DOC-RENDER-007`：Reduced Motion 的等价视觉语义
- `DOC-RENDER-009`：DOM overlay、focus trap 与 UiInputGate
- `DOC-PLAYER-003`：Tab mode switch context
- `DOC-PLAYER-010`：F11 与 Fullscreen API 用户流程

