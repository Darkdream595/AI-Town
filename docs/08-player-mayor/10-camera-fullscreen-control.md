---
doc_id: DOC-PLAYER-010
title: 相机、窗口与全屏控制
version: 1.0.0
status: approved-for-implementation
owner_domain: player
canonical_for:
  - player-camera-control
  - fullscreen-user-flow
  - fullscreen-failure-recovery
depends_on:
  - DOC-MAP-011
  - DOC-RENDER-001
  - DOC-RENDER-009
requirements:
  - REQ-PRODUCT-001
  - REQ-PRODUCT-002
  - REQ-PLAYER-010
last_updated: 2026-07-26
---

# 相机、窗口与全屏控制

## 1. 目的

`REQ-PLAYER-010`：定义玩家跟随相机、Mayor overview、窗口 resize、`F11` 提示和可点击 Fullscreen API 的用户流程与恢复，确保双击启动后能明确进入全屏且任何失败不影响游戏。

## 2. 非目标

本文不拥有 MAP camera clamp 数学、Phaser Scene 生命周期、Canvas/DOM layout token、Launcher 打包或浏览器自身 `F11` 行为；PLAYER 只拥有控制 intent、提示和客户端状态协调。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Follow Camera | 以已提交玩家 Resident WorldPoint 为 target 的相机 |
| Mayor Overview | 受 MAP boundary 约束的治理浏览相机，不移动 Resident |
| Browser Fullscreen | 浏览器 `F11`，由浏览器处理，应用只提示 |
| Element Fullscreen | 用户点击后对 `#game-shell` 调用 Fullscreen API |
| Presentation State | `windowed/requesting/fullscreen/exiting/failed` 的纯客户端状态 |

## 4. 规则与不变量

- `RULE-PLAYER-047`：相机位置、zoom、viewport、fullscreen 和 Mayor pan 仅为展示状态，不能改变 actor WorldPoint、Collision、交互距离、视线或 authority。
- `RULE-PLAYER-048`：双击 `启动AI小镇.bat` 打开网页后的首次可交互画面，必须同时显示“按 F11”与可点击“全屏游玩”按钮；提示不能依赖模型或网络。
- `RULE-PLAYER-049`：Element Fullscreen 只能在用户点击/键盘激活按钮的同一 user activation call stack 中请求，目标固定为 `#game-shell`，包含 Canvas 和 DOM overlay。
- `RULE-PLAYER-050`：Fullscreen 请求拒绝、超时、失焦或 API 缺失时保持/恢复 windowed layout、focus 和 input；不得卡在黑屏、暂停或锁定 input。
- `RULE-PLAYER-051`：退出 fullscreen、resize、DPR change 和 orientation-like viewport change 必须重新 clamp camera，但不得发布 DomainEvent。

## 5. 客户端状态 Schema

```json
{
  "schema_version": 1,
  "presentation_state": "windowed",
  "camera_mode": "follow_player",
  "camera_target": {
    "scene_id": "scene.crowncreek.town",
    "x_wu": 1024,
    "y_wu": 960
  },
  "zoom": 1,
  "viewport_css_px": {
    "width": 1920,
    "height": 1080
  },
  "device_pixel_ratio": 1,
  "fullscreen_supported": true,
  "last_failure_code": null
}
```

`camera_mode` 仅 `follow_player/mayor_overview/cinematic_locked`；zoom 范围由 RENDER registry 限制。此 Schema 不进入权威 world snapshot，只进入客户端诊断。

## 6. 相机流程

Resident Mode 默认跟随最新 committed player position，使用 MAP clamp；客户端预测只能短暂影响 Sprite 和相机视觉，不改变规则 target。Mayor mode 可 pan/zoom 查看 jurisdiction，但 interaction hit-test 使用服务端 subject ID/revision，不从屏幕坐标直接修改世界。Scene transition 先安装新 Snapshot，再设置 camera target 和 clamp，避免显示地图外区域。

## 7. Fullscreen 流程

1. 首次进入 modal 展示 `F11`、全屏按钮、`稍后`；所有项可键盘访问。
2. 点击全屏按钮立即调用 `#game-shell.requestFullscreen()`；调用前不 await 网络/模型。
3. 监听 `fullscreenchange/fullscreenerror`，成功后重算 viewport、Safe Area、Canvas backing store 和 camera clamp。
4. 用户按 `Esc` 或浏览器退出时执行相同 windowed resize 路径，并恢复 `#game-shell` 或先前合法 focus。
5. Promise rejection/API 缺失/3 秒无 change 时显示非阻塞提示：“无法自动全屏，可按 F11；游戏仍可在窗口中运行。”
6. 首次提示选择只保存 presentation preference，不保存“已成功全屏”的虚假状态。

## 8. 输入与模式协调

fullscreen 按钮获得 DOM focus 时 `UiInputGate` 阻止 E/Enter/Space 同时触发世界行为。`F11` 不拦截、不重绑定、不假装调用成功；浏览器可能保留该快捷键。Mayor overview 的 pan keys 只在 Mayor canvas context 生效，退出模式立即清除。Fullscreen change 不释放 Pause Token、不自动切换模式。

## 9. 失败恢复与性能

WebGL context loss 与 fullscreen failure 分开处理；前者遵循 RENDER snapshot/recreate，后者只恢复 layout。resize 事件在 animation frame 合并，最终事件必须执行；不得每次像素变化请求后端。极小 viewport 采用 letterbox/滚动 DOM，不缩小到无法点击。重载后从 windowed 开始，浏览器不允许应用自动重新进入 fullscreen。

## 10. 验收标准

- 双击启动后的首屏明确提供 `F11` 和可点击全屏按钮。
- Fullscreen API 只在真实 user gesture 中调用，覆盖 Canvas 与 DOM overlay。
- 成功、拒绝、API 缺失、Esc 退出和 resize 五条路径均可继续游戏。
- fullscreen/zoom/Mayor pan 不改变 WorldPoint、Collision 或权限。
- 720p、1080p、fullscreen 下 camera clamp、Safe Area 和 focus 正确。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-PLAYER-037` | 首次启动 F11/按钮提示与键盘可达 |
| `TEST-PLAYER-038` | user activation、success/error/timeout/Esc |
| `TEST-PLAYER-039` | resize/DPR/小地图 clamp 与 Snapshot transition |
| `TEST-PLAYER-040` | fullscreen/camera 对规则状态零影响 |

## 12. 关联文档

- `DOC-MAP-011`：camera clamp 与小于 viewport 的 Scene
- `DOC-RENDER-001`：WorldPoint、Snapshot 与 camera projection
- `DOC-RENDER-009`：`#game-shell`、DOM overlay、Safe Area 与 focus
- `DOC-PLAYER-011`：全屏提示、快捷键和可访问输入

