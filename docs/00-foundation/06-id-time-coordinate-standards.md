---
doc_id: DOC-FOUNDATION-006
title: ID、时间、坐标与单位标准
version: 1.0.0
status: approved-for-implementation
owner_domain: foundation
canonical_for:
  - stable-id-grammar
  - global-time-primitives
  - global-coordinate-primitives
  - global-unit-conventions
depends_on:
  - DOC-FOUNDATION-004
  - DOC-FOUNDATION-005
requirements:
  - REQ-PRODUCT-003
  - REQ-PRODUCT-008
  - REQ-PRODUCT-014
  - REQ-PRODUCT-018
last_updated: 2026-07-26
---

# ID、时间、坐标与单位标准

## 1. 目的

统一文档 ID、运行时 stable ID、ULID、Revision、三套时间、坐标、方向、货币和换算规则，消除跨文档类型与单位歧义。

## 2. 非目标

本文件不规定导航网格分辨率、战斗公式、具体日历节日或价格公式；这些由对应 domain 定义，但必须使用本文件基元。

## 3. 术语与定义

| 基元 | 类型 | 定义 |
|---|---|---|
| Stable Catalog ID | lowercase dotted string | 人工定义、跨存档稳定的类型/实体模板 ID |
| Runtime ID | ULID string | 世界运行时创建的 aggregate、Command、Event、Proposal 等 ID |
| `Revision` | uint64 | 每世界单调事务序号 |
| `RealDurationMs` | uint64 | 单调 RealTime 持续毫秒，不是墙钟 timestamp |
| `GameInstant` | int64 | 自世界纪元起的整数游戏分钟 |
| `TurnIndex` | uint32 | Encounter 内从 0 开始的离散回合序号 |
| `WorldPoint` | `{scene_id,x_wu,y_wu}` | Scene 内 world unit 坐标 |
| `LocalPoint` | `{frame_id,x_lu,y_lu}` | 明确 local frame 内坐标 |
| `CopperFeather` | int64 | 唯一货币存储单位；中文“铜羽” |

## 4. 规则与不变量

### 4.1 ID grammar

- `RULE-FOUNDATION-031`：文档 ID 使用 `DOC-<DOMAIN>-NNN`；需求、设计、规则、测试分别使用 `REQ|DES|RULE|TEST-<DOMAIN>-NNN`，定义后不得复用或改变语义。
- `RULE-FOUNDATION-032`：Stable Catalog ID 使用 `namespace.segment[.segment...]`，每段匹配 `[a-z][a-z0-9_]*`；禁止空格、大小写混用、路径字符和 locale 文本。
- `RULE-FOUNDATION-033`：Runtime ID 使用 26 字符 Crockford Base32 ULID；时间部分只提供排序性，不作为权威 GameTime。
- `RULE-FOUNDATION-034`：外部 Command ID 由 Client 生成 ULID；服务器验证格式并以 `(world_id, command_id)` 作为幂等键。

示例：

```text
DOC-FOUNDATION-006
REQ-MAP-001
resident.apothecary.elise
item.healing_potion.small
semantic_exit.crown_creek.east_gate
01K1AB2CD3EF4GH5JK6MNP7QRS
```

### 4.2 时间

- `RULE-FOUNDATION-035`：`RealTime` 使用 monotonic clock 测量 timeout/latency；持久化墙钟采用 UTC RFC 3339，二者不得混用。
- `RULE-FOUNDATION-036`：`GameTime` 持久化为自世界纪元起整数分钟；默认 `1 real second = 1 game minute`，倍率仅允许 `0, 0.5, 1, 2, 4`。
- `RULE-FOUNDATION-037`：`TurnTime` 只在 Encounter 内以 `turn_index`、`round_index`、`phase` 表达，不与 GameTime 自动换算。
- `RULE-FOUNDATION-038`：游戏关闭、恢复屏障、对话输入、镇长管理和回合战斗按规则暂停 Overworld 时，GameTime 不推进。

### 4.3 坐标与方向

- `RULE-FOUNDATION-039`：2D Scene 使用左上原点，`+X` 向右/东，`+Y` 向下/南；角度以度表示，0° 东、90° 南、180° 西、270° 北，顺时针递增并归一到 `[0,360)`。
- `RULE-FOUNDATION-040`：1 world unit (`wu`) 是规则坐标单位；首版基准 `1 tile = 32 wu`，`1 wu = 1 design pixel at 1×`，渲染缩放不改变规则坐标。
- `RULE-FOUNDATION-041`：LocalPoint 必须携带 `frame_id` 并经版本化 Transform 转为 Scene WorldPoint；不同 Scene 的点不可直接计算距离。
- `RULE-FOUNDATION-042`：位置、Polygon 顶点和距离以有限 IEEE-754 number 传输，持久化量化到 `1/16 wu`；比较使用 owner 定义 epsilon，禁止依赖裸浮点相等。

### 4.4 数量与单位

- `RULE-FOUNDATION-043`：货币只存整数铜羽，`1 silver_crown = 100 copper_feather`；显示换算不得产生或截断余额。
- `RULE-FOUNDATION-044`：JSON timestamp 使用 UTC RFC 3339 格式 `YYYY-MM-DDTHH:mm:ss.sssZ`；GameTime 禁止伪装为 UTC timestamp。
- `RULE-FOUNDATION-045`：持续时间字段带单位后缀：`*_ms`、`*_game_minutes`、`*_turns`；距离字段使用 `*_wu`，角度字段使用 `*_degrees`。

## 5. 数据与接口

`DES-FOUNDATION-006`：协议采用以下基元：

```json
{
  "world_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "revision": 42,
  "game_time": 1830,
  "recorded_at": "2026-07-26T08:30:15.250Z",
  "position": {
    "scene_id": "region.crown_creek_town",
    "x_wu": 1024.0,
    "y_wu": 768.0
  },
  "facing_degrees": 90,
  "balance_copper_feather": 1234
}
```

World ID、timeline ID、entity instance ID、Command/Event/Proposal/Reservation/Snapshot ID 均使用 ULID；注册表中的 region/item/spell/action/semantic node 使用 Stable Catalog ID。

## 6. 正常流程

1. 世界创建时使用 CSPRNG 生成 world ULID 与 128-bit Seed。
2. 注册内容在构建期验证 Stable Catalog ID 唯一性。
3. 命令入口验证 ID、数字有限性、单位后缀和 timestamp。
4. Domain 内以明确 value object 计算，提交时量化并检查范围。
5. 对外显示层进行 locale 与银冠/铜羽格式化，不改变存储值。

## 7. 边界情况

- ULID 同毫秒生成时使用 monotonic ULID factory 保持进程内排序，但事实顺序仍以 Revision 为准。
- 夏令时、系统时钟回拨不影响 RealDuration 或 GameTime；仅 `recorded_at` 可能反映墙钟校正。
- Polygon 边界上的点由 MAP owner 采用一致的 boundary-inclusive Walkability、boundary-exclusive Collision 规则判定。
- 区域转场不是坐标平移；必须通过 Semantic Exit 的明确 arrival point。
- 负货币只允许作为拒绝前的计算中间值，任何持久余额不得小于 0。

## 8. 错误与降级

格式错误、NaN/Infinity、超范围整数、未知 frame/scene 或单位缺失均在协议边界拒绝。旧 Schema 由版本化 upcaster 转换；无法无损转换时停止加载该 world，不猜测坐标或时间。

## 9. 安全与性能

ULID 不用于授权且可能泄漏创建时间，公开日志按需脱敏 entity ID。坐标与数量必须设有限幅，防止超大 Polygon/整数导致 CPU 或存储滥用。常用 Transform 和 ID registry 按版本缓存为不可变结构。

## 10. 验收标准

- 所有 Schema 字段可唯一识别 ID 类别、时间域、坐标 frame 与单位。
- 存档重载后 Seed、GameTime、坐标量化值和 Revision 不变。
- 货币往返格式化保持整数铜羽守恒。
- 区域/室内转换不会直接比较不同 frame 坐标。
- repository-wide lint 不存在无单位 duration/distance 字段或废弃 ID spelling。

## 11. 测试追踪

| 测试 ID | 覆盖规则 |
|---|---|
| `TEST-FOUNDATION-026` | `RULE-FOUNDATION-031..034` ID grammar、唯一性与幂等键 |
| `TEST-FOUNDATION-027` | `RULE-FOUNDATION-035..038` pause、倍率、时钟回拨 |
| `TEST-FOUNDATION-028` | `RULE-FOUNDATION-039..042` 坐标、Transform、量化 |
| `TEST-FOUNDATION-029` | `RULE-FOUNDATION-043..045` 货币与单位 round-trip |

## 12. 关联文档

- `DOC-FOUNDATION-004`：共享术语语义
- `DOC-FOUNDATION-005`：Revision、Seed、位置和货币不变量
- `DOC-MAP-001..012`：地图与导航细化
- `DOC-TIME-001..012`：GameTime、Tick 与 Seed stream 细化
- `DOC-BACKEND-005..007`：协议与 Schema 版本化
