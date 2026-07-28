# P17 前端渲染系统补全设计

## 1. 目标

按 `docs/03-rendering-art-audio/` 的 12 份契约补全前端渲染系统，使
`TEST-RENDER-001`～`TEST-RENDER-012` 中可自动化验证的部分具备稳定、
可重复的 Vitest 覆盖，并将关键契约接入现有 Phaser 运行时。

本阶段延续 Kimi 已创建但未提交的：

- `frontend/src/render/protocol.ts`
- `frontend/src/render/snapshot_gate.ts`

它们属于现有工作成果，不覆盖、不回退；先补测试，再根据失败结果修正。

## 2. 范围

### 2.1 新增纯逻辑模块

| 文件 | 单一职责 | 主要契约 |
| --- | --- | --- |
| `frontend/src/render/event_sequencer.ts` | Event 去重、事务收齐、确定性排序、Revision gap | RENDER-001 |
| `frontend/src/render/scene_lifecycle.ts` | Load Gate、取消旧请求、重试、Warm Dispose | RENDER-002 |
| `frontend/src/render/map_slices.ts` | viewport/zoom 切片范围、preload ring、LOD budget | RENDER-003 |
| `frontend/src/render/animation_sm.ts` | 动画优先级、Revision 覆盖、900 ms 回退 | RENDER-005 |
| `frontend/src/render/sprite_lint.ts` | Sprite Catalog ID、方向、帧数、anchor 校验 | RENDER-004 |
| `frontend/src/render/structures.ts` | 建筑 stage 原子替换与 occluder 计划 | RENDER-006 |
| `frontend/src/render/environment.ts` | 昼夜 band、registry hash、天气与 Reduced Motion | RENDER-007 |
| `frontend/src/render/vfx.ts` | VFX 注册、去重、对象池、上限与降级 | RENDER-008 |
| `frontend/src/render/audio_state.ts` | Audio State、500 ms crossfade、bus 上限、license 引用 | RENDER-010 |
| `frontend/src/render/manifest.ts` | Canonical schema 子集校验、Manifest lint、fallback DAG | RENDER-011 |
| `frontend/src/render/ui_layout.ts` | Safe Area、UiInputGate、fullscreen 决策 | RENDER-009 |
| `frontend/src/render/perf.ts` | nearest-rank 性能门与纹理内存估算 | RENDER-012 |

`protocol.ts` 与 `snapshot_gate.ts` 加入测试后，共形成 14 个职责明确的
纯逻辑模块。模块不导入 Phaser，确保可以在 Node/Vitest 环境独立验证。

### 2.2 必要的现有文件调整

- `frontend/src/types/rendering.ts`
  - 补充契约要求的动画状态及投影类型。
  - 保持现有导出兼容，避免无关调用方重构。
- `frontend/src/scenes/WorldScene.ts`
  - 接入 Snapshot Gate、Event Sequencer。
  - 只在完整事务通过后更新渲染投影。
  - 使用确定性切片与动画决策，不在 Scene 内复制业务规则。
- `frontend/src/scenes/UIScene.ts`
  - 接入布局与输入门状态。
- `frontend/src/ui/PhaserDomBridge.ts`
  - DOM focus/modal 状态驱动 `UiInputGate`。
  - 修复现有未使用参数错误，不改变对外行为。
- `frontend/src/utils/SpriteLoader.ts`
  - 使用 Sprite lint/fallback 结果。
  - 修复现有未使用参数错误。
- `frontend/index.html`
  - 增加 `#game-shell`，同时包裹 `#game-container` 与 `#ui-overlay`。
  - Fullscreen target 固定为 `#game-shell`。

不修改后端、发布模块、`testing-self-study/`，不安装新依赖。

## 3. 架构与数据流

### 3.1 Snapshot

1. 网络层收到 `RenderFrameInput`。
2. `protocol.ts` 校验协议版本、有限数、WorldPoint、facing 和 SHA-256。
3. `SnapshotGate` 校验 world/scene/Revision 与同 Revision 内容一致性。
4. `apply` 时单帧原子替换投影，并通知 `EventSequencer`：
   - 丢弃 `revision <= snapshot.revision` 的 pending event。
   - 清空一次性 VFX 和插值队列。
5. `idempotent_replay` 不重复创建实体或 VFX。
6. `contract_error`、`reject_stale` 均不得部分应用。

### 3.2 Event

1. `EventSequencer` 先校验 protocol/world/scene。
2. 以 `(world_id, event_id)` 做 10,000 ID、30 分钟 TTL 的 LRU 去重。
3. 相同 Revision 的 event 必须：
   - `transaction_event_count` 一致；
   - index 从 0 连续到 `count - 1`；
   - 收齐后按 `(transaction_event_index, event_id)` 确定性排序。
4. 事务未收齐时只缓存，不修改投影。
5. 下一 Revision 缺失时停止应用并请求完整 Snapshot。

### 3.3 Scene 与视觉子系统

- Scene 切换只接受已提交的 `scene_id` 变化。
- Load Gate 就绪前保持 loading parchment，旧 Scene 最多 Warm 5 秒。
- 地图切片集合由 viewport、zoom、camera bounds 计算，不固定为 3×3。
- 动画、Structure、Environment、VFX 与 Audio 都消费已确认投影，
  不从画面、墙钟或本地输入推断世界事实。
- Reduced Motion 在决策层生成等价静态提示，避免运行时分支散落。

### 3.4 UI

- Canvas 负责世界与非交互装饰。
- HUD、Dialogue、Mayor 文本、按钮和表单保留在 `#ui-overlay`。
- DOM modal/focus 激活时，`UiInputGate` 阻止对应 Phaser world input。
- Fullscreen API 只能在用户手势中作用于 `#game-shell`。

## 4. 错误与降级

- 协议、world、scene、hash 或 Revision 冲突：拒绝整帧/整事务。
- Revision gap、lighting registry mismatch：保留上一有效状态并请求 Snapshot。
- 缺失 Sprite/动画/Structure/VFX：使用文档规定的 fallback，不阻塞事件消费。
- 未知 weather：降级为 `weather.clear`。
- VFX 超过 96：优先保留战斗命中和状态效果，合并或丢弃非关键环境效果。
- Audio autoplay 被阻止：保留目标 Audio State，显示启用入口，不重复创建 layer。
- Manifest 任一安全或 license 校验失败：资源不得进入可加载集合。
- 所有诊断只包含稳定 ID、JSON Pointer 和 reason code，不写入敏感内容。

## 5. 并行执行边界

最多同时运行主 agent 与 3 个 subagent。所有 agent 共享工作区，因此使用
严格文件所有权，禁止跨组修改。

### 主 agent

- 先处理公共契约：
  - `protocol.ts`、`snapshot_gate.ts` 对应测试；
  - `types/rendering.ts` 的最小兼容扩展；
  - 测试 fixtures。
- 并行阶段负责：
  - `manifest.ts`
  - `ui_layout.ts`
  - `perf.ts`
- 汇合后独占：
  - `WorldScene.ts`
  - `UIScene.ts`
  - `PhaserDomBridge.ts`
  - `SpriteLoader.ts`
  - `index.html`

### subagent A

- `event_sequencer.ts`
- `scene_lifecycle.ts`
- `map_slices.ts`
- 上述模块对应测试

### subagent B

- `animation_sm.ts`
- `sprite_lint.ts`
- `structures.ts`
- 上述模块对应测试

### subagent C

- `environment.ts`
- `vfx.ts`
- `audio_state.ts`
- 上述模块对应测试

subagent 不修改公共类型、Scene、DOM、配置或 Git 状态；不安装依赖、不提交。
局部测试只运行自己拥有的测试文件，避免把其他组尚未完成视为失败。

## 6. 测试策略

每组严格执行 Red → Green → Refactor：

1. 先写单一行为的失败测试。
2. 运行聚焦 Vitest，确认因缺少目标行为而失败。
3. 写最小实现。
4. 再运行聚焦测试，确认通过。
5. 组内完成后运行相关测试集合。

覆盖重点：

- TEST-RENDER-001：协议、Snapshot 原子性、Event 去重/排序/gap。
- TEST-RENDER-002：Load Gate、取消、重试、Warm Dispose。
- TEST-RENDER-003：viewport/zoom/边界、LOD 与 depth。
- TEST-RENDER-004/005：Sprite lint、动画优先级与 fallback。
- TEST-RENDER-006/007：Structure 原子替换、1440 分钟 lighting property。
- TEST-RENDER-008：VFX 去重、回收、96 上限、Reduced Motion。
- TEST-RENDER-009：Safe Area、input suppression、fullscreen target。
- TEST-RENDER-010：Audio State、crossfade、并发与 license。
- TEST-RENDER-011：schema、path、hash、license、fallback DAG。
- TEST-RENDER-012：p95/p99、纹理估算、共享纹理去重与预算。

最终验证命令：

```powershell
cd D:\dream\JT_AI\AI_Town\frontend
node node_modules/vitest/vitest.mjs run
node node_modules/typescript/bin/tsc --noEmit
node node_modules/typescript/bin/tsc -p tsconfig.build.json
node node_modules/vite/bin/vite.js build
```

## 7. 验收标准

- 14 个纯逻辑模块都有直接测试。
- TEST-RENDER-001～012 的可自动化契约均有明确测试映射。
- 既有 34 项测试全部通过。
- 新增测试全部通过且输出无错误。
- `tsc --noEmit` 与 production build 通过。
- Snapshot/Event 错误输入不会部分修改 WorldScene。
- DOM focus 不会同时触发 UI 与世界输入。
- `#game-shell` 同时包含 canvas target 与 DOM overlay。
- 未新增依赖；后端变化仅限后续 Launcher/Release 收尾所需契约。
- 最终 Git diff 仅包含 P17 与 Launcher/Release 收尾必需文件。
