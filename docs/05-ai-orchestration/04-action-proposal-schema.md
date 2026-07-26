---
doc_id: DOC-AI-004
title: ActionProposal 严格 Schema
version: 1.0.0
status: approved-for-implementation
owner_domain: ai
canonical_for:
  - action-proposal-schema
  - action-parameter-discriminator
depends_on:
  - DOC-FOUNDATION-006
  - DOC-AI-001
  - DOC-AI-003
requirements:
  - REQ-AI-004
last_updated: 2026-07-26
---

# ActionProposal 严格 Schema

## 1. 目的

`REQ-AI-004`：定义模型输出 `ActionProposalV1` 的唯一 strict JSON Schema，以及总体设计首版清单中的 19 个 Action 与其唯一 canonical `parameters` 分支。

## 2. 非目标

Schema 通过不等于行动合法或成功。模型不提供可信 `proposal_id/actor_id/world_id/revision`，不决定路径、价格结算、伤害、产出、权限或 DomainEvent。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Model Artifact | provider 返回、尚未可信的 JSON bytes |
| Strict Decode | required、type、enum、range 和 `additionalProperties=false` 全部通过 |
| Action Discriminator | `action` const 与 `parameters` `$defs` 的一一映射 |
| Server Envelope | decode 后由服务器追加的不可伪造 metadata |

## 4. Canonical JSON Schema

`DES-AI-004`：注册 `$id=schema://ai-town/ai/action-proposal/v1`。以下 code block 是唯一机器提取真源，DOC-AI-005 只解释语义，不复制另一套字段定义。

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "schema://ai-town/ai/action-proposal/v1",
  "type": "object",
  "required": ["goal", "action", "target_entity_id", "destination_id", "parameters", "spoken_text", "emotion", "priority", "expected_duration_minutes", "abort_conditions"],
  "properties": {
    "goal": {"type": "string", "minLength": 1, "maxLength": 240},
    "action": {"enum": ["move_to", "talk", "work", "rest", "eat", "buy", "sell", "give_item", "use_object", "craft", "gather", "explore", "cast_spell", "start_encounter", "combat_action", "build", "repair", "wait", "observe"]},
    "target_entity_id": {"oneOf": [{"$ref": "#/$defs/entity_ref"}, {"type": "null"}]},
    "destination_id": {"oneOf": [{"$ref": "#/$defs/stable_ref"}, {"type": "null"}]},
    "parameters": {"type": "object"},
    "spoken_text": {"oneOf": [{"type": "string", "maxLength": 280}, {"type": "null"}]},
    "emotion": {"enum": ["calm", "joy", "sadness", "anger", "fear", "anxiety", "disgust", "hope"]},
    "priority": {"type": "integer", "minimum": 0, "maximum": 100},
    "expected_duration_minutes": {"type": "integer", "minimum": 0, "maximum": 1440},
    "abort_conditions": {
      "type": "array",
      "maxItems": 8,
      "uniqueItems": true,
      "items": {"enum": ["danger_detected", "critical_need", "health_restricted", "target_unavailable", "destination_unreachable", "permission_denied", "resource_unavailable", "reservation_conflict", "deadline_missed", "shop_closed", "insufficient_funds", "quote_changed", "combat_started", "player_interrupt", "world_event_changed", "action_no_longer_useful"]}
    }
  },
  "allOf": [
    {"if": {"properties": {"action": {"const": "move_to"}}}, "then": {"properties": {"parameters": {"$ref": "#/$defs/move_to_parameters"}}}},
    {"if": {"properties": {"action": {"const": "talk"}}}, "then": {"properties": {"parameters": {"$ref": "#/$defs/talk_parameters"}}}},
    {"if": {"properties": {"action": {"const": "work"}}}, "then": {"properties": {"parameters": {"$ref": "#/$defs/work_parameters"}}}},
    {"if": {"properties": {"action": {"const": "rest"}}}, "then": {"properties": {"parameters": {"$ref": "#/$defs/rest_parameters"}}}},
    {"if": {"properties": {"action": {"const": "eat"}}}, "then": {"properties": {"parameters": {"$ref": "#/$defs/eat_parameters"}}}},
    {"if": {"properties": {"action": {"const": "buy"}}}, "then": {"properties": {"parameters": {"$ref": "#/$defs/buy_parameters"}}}},
    {"if": {"properties": {"action": {"const": "sell"}}}, "then": {"properties": {"parameters": {"$ref": "#/$defs/sell_parameters"}}}},
    {"if": {"properties": {"action": {"const": "give_item"}}}, "then": {"properties": {"parameters": {"$ref": "#/$defs/give_item_parameters"}}}},
    {"if": {"properties": {"action": {"const": "use_object"}}}, "then": {"properties": {"parameters": {"$ref": "#/$defs/use_object_parameters"}}}},
    {"if": {"properties": {"action": {"const": "craft"}}}, "then": {"properties": {"parameters": {"$ref": "#/$defs/craft_parameters"}}}},
    {"if": {"properties": {"action": {"const": "gather"}}}, "then": {"properties": {"parameters": {"$ref": "#/$defs/gather_parameters"}}}},
    {"if": {"properties": {"action": {"const": "explore"}}}, "then": {"properties": {"parameters": {"$ref": "#/$defs/explore_parameters"}}}},
    {"if": {"properties": {"action": {"const": "cast_spell"}}}, "then": {"properties": {"parameters": {"$ref": "#/$defs/cast_spell_parameters"}}}},
    {"if": {"properties": {"action": {"const": "start_encounter"}}}, "then": {"properties": {"parameters": {"$ref": "#/$defs/start_encounter_parameters"}}}},
    {"if": {"properties": {"action": {"const": "combat_action"}}}, "then": {"properties": {"parameters": {"$ref": "#/$defs/combat_action_parameters"}}}},
    {"if": {"properties": {"action": {"const": "build"}}}, "then": {"properties": {"parameters": {"$ref": "#/$defs/build_parameters"}}}},
    {"if": {"properties": {"action": {"const": "repair"}}}, "then": {"properties": {"parameters": {"$ref": "#/$defs/repair_parameters"}}}},
    {"if": {"properties": {"action": {"const": "wait"}}}, "then": {"properties": {"parameters": {"$ref": "#/$defs/wait_parameters"}}}},
    {"if": {"properties": {"action": {"const": "observe"}}}, "then": {"properties": {"parameters": {"$ref": "#/$defs/observe_parameters"}}}}
  ],
  "$defs": {
    "ulid": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "stable_ref": {"type": "string", "pattern": "^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)+$", "maxLength": 128},
    "entity_ref": {"type": "string", "anyOf": [{"pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"}, {"pattern": "^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)+$"}], "maxLength": 128},
    "world_point": {
      "type": "object",
      "required": ["scene_id", "x_wu", "y_wu"],
      "properties": {"scene_id": {"$ref": "#/$defs/stable_ref"}, "x_wu": {"type": "number", "minimum": 0, "maximum": 8192}, "y_wu": {"type": "number", "minimum": 0, "maximum": 8192}},
      "additionalProperties": false
    },
    "move_to_parameters": {
      "type": "object", "required": ["destination_kind", "arrival_radius_wu", "movement_mode"],
      "properties": {"destination_kind": {"enum": ["semantic_node", "world_point"]}, "world_point": {"oneOf": [{"$ref": "#/$defs/world_point"}, {"type": "null"}]}, "arrival_radius_wu": {"type": "number", "minimum": 0, "maximum": 64}, "movement_mode": {"enum": ["normal", "cautious", "urgent"]}},
      "additionalProperties": false
    },
    "talk_parameters": {
      "type": "object", "required": ["topic_id", "conversation_intent", "privacy"],
      "properties": {"topic_id": {"$ref": "#/$defs/stable_ref"}, "conversation_intent": {"enum": ["greet", "ask", "inform", "request", "negotiate", "comfort", "warn", "apologize"]}, "privacy": {"enum": ["public", "private_requested"]}},
      "additionalProperties": false
    },
    "work_parameters": {
      "type": "object", "required": ["employment_contract_id", "shift_id", "workplace_id"],
      "properties": {"employment_contract_id": {"$ref": "#/$defs/ulid"}, "shift_id": {"$ref": "#/$defs/ulid"}, "workplace_id": {"$ref": "#/$defs/entity_ref"}},
      "additionalProperties": false
    },
    "rest_parameters": {
      "type": "object", "required": ["rest_kind", "minimum_game_minutes", "rest_node_id"],
      "properties": {"rest_kind": {"enum": ["short_break", "sleep", "recover"]}, "minimum_game_minutes": {"type": "integer", "minimum": 1, "maximum": 720}, "rest_node_id": {"$ref": "#/$defs/stable_ref"}},
      "additionalProperties": false
    },
    "eat_parameters": {
      "type": "object", "required": ["item_or_batch_id", "quantity"],
      "properties": {"item_or_batch_id": {"$ref": "#/$defs/ulid"}, "quantity": {"type": "integer", "minimum": 1, "maximum": 32}},
      "additionalProperties": false
    },
    "buy_parameters": {
      "type": "object", "required": ["item_definition_id", "quantity", "maximum_unit_price_copper_feather", "quote_id"],
      "properties": {"item_definition_id": {"$ref": "#/$defs/stable_ref"}, "quantity": {"type": "integer", "minimum": 1, "maximum": 99}, "maximum_unit_price_copper_feather": {"type": "integer", "minimum": 0, "maximum": 1000000}, "quote_id": {"oneOf": [{"$ref": "#/$defs/ulid"}, {"type": "null"}]}},
      "additionalProperties": false
    },
    "sell_parameters": {
      "type": "object", "required": ["item_or_batch_id", "quantity", "minimum_unit_price_copper_feather", "quote_id"],
      "properties": {"item_or_batch_id": {"$ref": "#/$defs/ulid"}, "quantity": {"type": "integer", "minimum": 1, "maximum": 99}, "minimum_unit_price_copper_feather": {"type": "integer", "minimum": 0, "maximum": 1000000}, "quote_id": {"oneOf": [{"$ref": "#/$defs/ulid"}, {"type": "null"}]}},
      "additionalProperties": false
    },
    "give_item_parameters": {
      "type": "object", "required": ["item_or_batch_id", "quantity", "gift_intent"],
      "properties": {"item_or_batch_id": {"$ref": "#/$defs/ulid"}, "quantity": {"type": "integer", "minimum": 1, "maximum": 99}, "gift_intent": {"enum": ["gift", "return", "fulfill_commitment", "aid"]}},
      "additionalProperties": false
    },
    "use_object_parameters": {
      "type": "object", "required": ["object_id", "interaction_id"],
      "properties": {"object_id": {"$ref": "#/$defs/entity_ref"}, "interaction_id": {"$ref": "#/$defs/stable_ref"}},
      "additionalProperties": false
    },
    "craft_parameters": {
      "type": "object", "required": ["recipe_id", "recipe_version", "quantity", "target_inventory_id"],
      "properties": {"recipe_id": {"$ref": "#/$defs/stable_ref"}, "recipe_version": {"type": "integer", "minimum": 1}, "quantity": {"type": "integer", "minimum": 1, "maximum": 32}, "target_inventory_id": {"$ref": "#/$defs/ulid"}},
      "additionalProperties": false
    },
    "gather_parameters": {
      "type": "object", "required": ["resource_node_id", "resource_definition_id", "requested_quantity"],
      "properties": {"resource_node_id": {"$ref": "#/$defs/entity_ref"}, "resource_definition_id": {"$ref": "#/$defs/stable_ref"}, "requested_quantity": {"type": "integer", "minimum": 1, "maximum": 99}},
      "additionalProperties": false
    },
    "explore_parameters": {
      "type": "object", "required": ["area_id", "exploration_mode", "maximum_game_minutes"],
      "properties": {"area_id": {"$ref": "#/$defs/stable_ref"}, "exploration_mode": {"enum": ["survey", "search_resource", "search_route", "patrol"]}, "maximum_game_minutes": {"type": "integer", "minimum": 1, "maximum": 360}},
      "additionalProperties": false
    },
    "cast_spell_parameters": {
      "type": "object", "required": ["spell_id", "target_refs", "aim_point", "declared_purpose"],
      "properties": {"spell_id": {"$ref": "#/$defs/stable_ref"}, "target_refs": {"type": "array", "maxItems": 8, "uniqueItems": true, "items": {"$ref": "#/$defs/entity_ref"}}, "aim_point": {"oneOf": [{"$ref": "#/$defs/world_point"}, {"type": "null"}]}, "declared_purpose": {"enum": ["utility", "healing", "defense", "combat", "ritual"]}},
      "additionalProperties": false
    },
    "start_encounter_parameters": {
      "type": "object", "required": ["target_entity_ids", "reason_id", "preferred_resolution"],
      "properties": {"target_entity_ids": {"type": "array", "minItems": 1, "maxItems": 4, "uniqueItems": true, "items": {"$ref": "#/$defs/entity_ref"}}, "reason_id": {"$ref": "#/$defs/stable_ref"}, "preferred_resolution": {"enum": ["deescalate", "defend", "capture", "drive_off"]}},
      "additionalProperties": false
    },
    "combat_action_parameters": {
      "type": "object", "required": ["encounter_id", "turn_index", "action_option_id", "target_combatant_ids"],
      "properties": {"encounter_id": {"$ref": "#/$defs/ulid"}, "turn_index": {"type": "integer", "minimum": 0}, "action_option_id": {"$ref": "#/$defs/stable_ref"}, "target_combatant_ids": {"type": "array", "maxItems": 4, "uniqueItems": true, "items": {"$ref": "#/$defs/ulid"}}},
      "additionalProperties": false
    },
    "build_parameters": {
      "type": "object", "required": ["building_template_id", "parcel_id", "permit_id", "orientation_degrees"],
      "properties": {"building_template_id": {"$ref": "#/$defs/stable_ref"}, "parcel_id": {"$ref": "#/$defs/entity_ref"}, "permit_id": {"$ref": "#/$defs/ulid"}, "orientation_degrees": {"enum": [0, 90, 180, 270]}},
      "additionalProperties": false
    },
    "repair_parameters": {
      "type": "object", "required": ["target_structure_id", "repair_definition_id", "maximum_material_budget_copper_feather"],
      "properties": {"target_structure_id": {"$ref": "#/$defs/entity_ref"}, "repair_definition_id": {"$ref": "#/$defs/stable_ref"}, "maximum_material_budget_copper_feather": {"type": "integer", "minimum": 0, "maximum": 10000000}},
      "additionalProperties": false
    },
    "wait_parameters": {
      "type": "object", "required": ["duration_game_minutes", "reason_id"],
      "properties": {"duration_game_minutes": {"type": "integer", "minimum": 1, "maximum": 120}, "reason_id": {"$ref": "#/$defs/stable_ref"}},
      "additionalProperties": false
    },
    "observe_parameters": {
      "type": "object", "required": ["subject_ref", "observation_mode", "duration_game_minutes"],
      "properties": {"subject_ref": {"$ref": "#/$defs/entity_ref"}, "observation_mode": {"enum": ["visual", "listen", "inspect", "assess"]}, "duration_game_minutes": {"type": "integer", "minimum": 0, "maximum": 60}},
      "additionalProperties": false
    }
  },
  "additionalProperties": false
}
```

`move_to.destination_kind=semantic_node` 要求顶层 `destination_id` 非 null 且 `world_point=null/absent`；`world_point` 则要求 `destination_id=null` 且参数中存在点。其他跨字段约束由同版本 semantic validator 强制并列入 DOC-AI-005。

服务器 decode 后追加：

```text
proposal_id, actor_id, world_id, observed_revision, observed_game_time,
prompt_id, prompt_hash, model_policy_id, provider_request_id,
input_tokens, output_tokens, received_at_monotonic_ms
```

这些字段若出现在模型 JSON 中因 `additionalProperties=false` 被拒绝。

## 5. 规则与不变量

- `RULE-AI-019`：19 个 action 值各自恰好映射一个 `$defs/*_parameters`；不存在默认/开放参数分支。
- `RULE-AI-020`：所有 object（包括 parameters）拒绝额外字段；数字有限、有界，ID/单位遵从 DOC-FOUNDATION-006。
- `RULE-AI-021`：`priority` 是 actor 偏好信号，不等于 TIME priority class；服务器按安全、玩家阻塞和 deadline 重新分类。
- `RULE-AI-022`：`expected_duration_minutes` 是估计，不驱动结算；TIME/owner 生成真实 deadline/work contract。
- `RULE-AI-023`：Schema/semantic/Domain validation 全部成功才可构造 ValidatedIntent。
- `RULE-AI-024`：Schema version 不兼容、未知 action 或额外字段一律 fail closed。

## 6. 正常流程

provider bytes 先做 UTF-8、大小和单 JSON object 检查；Draft 2020-12 validator strict decode；执行 discriminator/跨字段 semantic checks；服务器追加可信 envelope；进入 DOC-AI-010 Domain validation。

## 7. 边界情况

空字符串、NaN/Infinity、重复 array 值、超限文本、ULID 小写、稳定 ID 大写、错误 action/parameters 组合、模型伪造 actor/revision 均拒绝。`spoken_text=null` 合法；空字符串仅表示无可听内容但优先规范为 null。

## 8. 错误与降级

错误返回 JSON Pointer、keyword 和 reason code，不回显隐藏值。只允许一次白名单 shape repair；不得把未知字段丢弃后继续，也不得自动选择另一 action。

## 9. 安全与性能

模型响应上限 16 KiB、nesting depth 8、arrays 按各分支限幅。Schema 随应用只读发布、启动时编译缓存；禁止世界存档覆盖 `$id`。

## 10. 验收标准

- canonical code block 可由标准 JSON parser 与 Draft 2020-12 validator 加载。
- 每个 action 有正例、缺字段、额外字段、错分支和边界值 fixture。
- server-only 字段注入被拒绝；合法 Proposal canonical round-trip 相等。
- catalog enum、if/then 分支和 `$defs` 数量均为 19 且集合相等。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-AI-013` | Schema compile 与 canonical round-trip |
| `TEST-AI-014` | 19 action discriminator 全覆盖 |
| `TEST-AI-015` | additionalProperties/range/ID negative corpus |
| `TEST-AI-016` | server envelope spoof 拒绝 |

## 12. 关联文档

- `DOC-AI-005`：Action 语义、owner 与 cross-field checks
- `DOC-AI-010`：validation outcome
- `DOC-FOUNDATION-006`：ID、时间、坐标与单位
