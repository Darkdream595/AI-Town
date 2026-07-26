---
doc_id: DOC-RENDER-002
title: Scene 生命周期与区域卸载
version: 1.0.0
status: approved-for-implementation
owner_domain: rendering-art-audio
canonical_for:
  - scene-lifecycle
  - region-unload
  - asset-load-gates
depends_on:
  - DOC-RENDER-001
  - DOC-MAP-001
  - DOC-MAP-012
requirements:
  - REQ-RENDER-002
last_updated: 2026-07-26
---

# Scene 生命周期与区域卸载

## 1. 目的

规定 region/interior Scene 的加载门、转场、卸载与内存释放，确保显示生命周期不改变模拟生命周期。

## 2. 非目标

不规定 Semantic Exit 合法性或跨区位置计算；这些由 MAP/WORLD owner 验证。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Load Gate | Manifest 必需资源、Snapshot 和 map contract 全部就绪的门。 |
| Warm Scene | 可保留少量缓存、但不可更新或接收实体事件的离开区域。 |
| Dispose | 销毁 DisplayObject、Tilemap、音频实例与专属纹理引用。 |

## 4. 规则与不变量

- `RULE-RENDER-004`：转场由已提交的 `scene_id` 变化触发，客户端输入不能自行切换 Scene。
- `RULE-RENDER-005`：Load Gate 未完成前展示 loading parchment，禁止半张地图可操作。
- `RULE-RENDER-006`：离开区域 5 秒后 Dispose；期间允许一次同 ID 回退复用，超过时间必须释放。

## 5. 数据与接口

`DES-RENDER-002`：`SceneLoadRequest` 包含 `scene_id`、`revision`、`entry_world_point`、`required_asset_ids`；任何字段缺失即拒绝进入并保留上一已确认 Scene。

## 6. 正常流程

1. 收到已提交 transfer Snapshot，冻结旧 Scene 输入。
2. Manifest 校验、lazy load、创建新 WorldScene，并将相机置于 `entry_world_point`。
3. 首帧完成五层与实体水合后淡入 180 ms。
4. 旧 Scene 进入 Warm，5 秒后 Dispose。

## 7. 边界情况

连续往返、传送失败或断线时按最高 Revision 的 request 取消较旧 load；不能并行显示两个可更新 WorldScene。

## 8. 错误与降级

网络或资源失败显示可重试提示；重试沿用同一 `scene_id/revision`，三次失败后回到最后确认 Scene 并请求完整 Snapshot。

## 9. 安全与性能

每次只允许一个 load job；Dispose 必须解除事件监听和音频引用，避免跨区累积内存。

## 10. 验收标准

- `REQ-RENDER-002`：连续 20 次区域往返后无重复监听、无旧实体残留，内存曲线回到稳态。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-RENDER-002` | Integration 测试 load gate、取消旧 request、5 秒卸载与重连恢复。 |

## 12. 关联文档

- `DOC-RENDER-001`：Phaser 架构
- `DOC-RENDER-011`：Manifest 与 fallback
