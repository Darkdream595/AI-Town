"""
ActionProposalV1 严格 Schema 与解码

符合 DOC-AI-004：canonical JSON Schema 的唯一机器真源。
- $id = schema://ai-town/ai/action-proposal/v1
- 19 个 action 各自恰好映射一个 $defs/*_parameters（RULE-AI-019）
- 所有 object 拒绝额外字段（RULE-AI-020）
- server-only 字段注入一律拒绝（TEST-AI-016）
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

import jsonschema

from .constants import ACTION_IDS

#: canonical schema 注册 ID（DES-AI-004）
ACTION_PROPOSAL_SCHEMA_ID = "schema://ai-town/ai/action-proposal/v1"

#: 模型响应上限 16 KiB（DOC-AI-004 §9）
MAX_RESPONSE_BYTES = 16 * 1024

#: 服务器 decode 后追加的 envelope 字段；出现在模型 JSON 中即拒绝
SERVER_ENVELOPE_FIELDS: tuple[str, ...] = (
    "proposal_id",
    "actor_id",
    "world_id",
    "observed_revision",
    "observed_game_time",
    "prompt_id",
    "prompt_hash",
    "model_policy_id",
    "provider_request_id",
    "input_tokens",
    "output_tokens",
    "received_at_monotonic_ms",
)

# Canonical JSON Schema（DOC-AI-004 §4 code block 的逐字段拷贝）
ACTION_PROPOSAL_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": ACTION_PROPOSAL_SCHEMA_ID,
    "type": "object",
    "required": [
        "goal",
        "action",
        "target_entity_id",
        "destination_id",
        "parameters",
        "spoken_text",
        "emotion",
        "priority",
        "expected_duration_minutes",
        "abort_conditions",
    ],
    "properties": {
        "goal": {"type": "string", "minLength": 1, "maxLength": 240},
        "action": {
            "enum": [
                "move_to",
                "talk",
                "work",
                "rest",
                "eat",
                "buy",
                "sell",
                "give_item",
                "use_object",
                "craft",
                "gather",
                "explore",
                "cast_spell",
                "start_encounter",
                "combat_action",
                "build",
                "repair",
                "wait",
                "observe",
            ]
        },
        "target_entity_id": {
            "oneOf": [{"$ref": "#/$defs/entity_ref"}, {"type": "null"}]
        },
        "destination_id": {
            "oneOf": [{"$ref": "#/$defs/stable_ref"}, {"type": "null"}]
        },
        "parameters": {"type": "object"},
        "spoken_text": {"oneOf": [{"type": "string", "maxLength": 280}, {"type": "null"}]},
        "emotion": {
            "enum": ["calm", "joy", "sadness", "anger", "fear", "anxiety", "disgust", "hope"]
        },
        "priority": {"type": "integer", "minimum": 0, "maximum": 100},
        "expected_duration_minutes": {"type": "integer", "minimum": 0, "maximum": 1440},
        "abort_conditions": {
            "type": "array",
            "maxItems": 8,
            "uniqueItems": True,
            "items": {
                "enum": [
                    "danger_detected",
                    "critical_need",
                    "health_restricted",
                    "target_unavailable",
                    "destination_unreachable",
                    "permission_denied",
                    "resource_unavailable",
                    "reservation_conflict",
                    "deadline_missed",
                    "shop_closed",
                    "insufficient_funds",
                    "quote_changed",
                    "combat_started",
                    "player_interrupt",
                    "world_event_changed",
                    "action_no_longer_useful",
                ]
            },
        },
    },
    "allOf": [
        {
            "if": {"properties": {"action": {"const": action}}},
            "then": {"properties": {"parameters": {"$ref": f"#/$defs/{action}_parameters"}}},
        }
        for action in [
            "move_to",
            "talk",
            "work",
            "rest",
            "eat",
            "buy",
            "sell",
            "give_item",
            "use_object",
            "craft",
            "gather",
            "explore",
            "cast_spell",
            "start_encounter",
            "combat_action",
            "build",
            "repair",
            "wait",
            "observe",
        ]
    ],
    "$defs": {
        "ulid": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
        "stable_ref": {
            "type": "string",
            "pattern": "^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)+$",
            "maxLength": 128,
        },
        "entity_ref": {
            "type": "string",
            "anyOf": [
                {"pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
                {"pattern": "^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)+$"},
            ],
            "maxLength": 128,
        },
        "world_point": {
            "type": "object",
            "required": ["scene_id", "x_wu", "y_wu"],
            "properties": {
                "scene_id": {"$ref": "#/$defs/stable_ref"},
                "x_wu": {"type": "number", "minimum": 0, "maximum": 8192},
                "y_wu": {"type": "number", "minimum": 0, "maximum": 8192},
            },
            "additionalProperties": False,
        },
        "move_to_parameters": {
            "type": "object",
            "required": ["destination_kind", "arrival_radius_wu", "movement_mode"],
            "properties": {
                "destination_kind": {"enum": ["semantic_node", "world_point"]},
                "world_point": {"oneOf": [{"$ref": "#/$defs/world_point"}, {"type": "null"}]},
                "arrival_radius_wu": {"type": "number", "minimum": 0, "maximum": 64},
                "movement_mode": {"enum": ["normal", "cautious", "urgent"]},
            },
            "additionalProperties": False,
        },
        "talk_parameters": {
            "type": "object",
            "required": ["topic_id", "conversation_intent", "privacy"],
            "properties": {
                "topic_id": {"$ref": "#/$defs/stable_ref"},
                "conversation_intent": {
                    "enum": ["greet", "ask", "inform", "request", "negotiate", "comfort", "warn", "apologize"]
                },
                "privacy": {"enum": ["public", "private_requested"]},
            },
            "additionalProperties": False,
        },
        "work_parameters": {
            "type": "object",
            "required": ["employment_contract_id", "shift_id", "workplace_id"],
            "properties": {
                "employment_contract_id": {"$ref": "#/$defs/ulid"},
                "shift_id": {"$ref": "#/$defs/ulid"},
                "workplace_id": {"$ref": "#/$defs/entity_ref"},
            },
            "additionalProperties": False,
        },
        "rest_parameters": {
            "type": "object",
            "required": ["rest_kind", "minimum_game_minutes", "rest_node_id"],
            "properties": {
                "rest_kind": {"enum": ["short_break", "sleep", "recover"]},
                "minimum_game_minutes": {"type": "integer", "minimum": 1, "maximum": 720},
                "rest_node_id": {"$ref": "#/$defs/stable_ref"},
            },
            "additionalProperties": False,
        },
        "eat_parameters": {
            "type": "object",
            "required": ["item_or_batch_id", "quantity"],
            "properties": {
                "item_or_batch_id": {"$ref": "#/$defs/ulid"},
                "quantity": {"type": "integer", "minimum": 1, "maximum": 32},
            },
            "additionalProperties": False,
        },
        "buy_parameters": {
            "type": "object",
            "required": ["item_definition_id", "quantity", "maximum_unit_price_copper_feather", "quote_id"],
            "properties": {
                "item_definition_id": {"$ref": "#/$defs/stable_ref"},
                "quantity": {"type": "integer", "minimum": 1, "maximum": 99},
                "maximum_unit_price_copper_feather": {"type": "integer", "minimum": 0, "maximum": 1000000},
                "quote_id": {"oneOf": [{"$ref": "#/$defs/ulid"}, {"type": "null"}]},
            },
            "additionalProperties": False,
        },
        "sell_parameters": {
            "type": "object",
            "required": ["item_or_batch_id", "quantity", "minimum_unit_price_copper_feather", "quote_id"],
            "properties": {
                "item_or_batch_id": {"$ref": "#/$defs/ulid"},
                "quantity": {"type": "integer", "minimum": 1, "maximum": 99},
                "minimum_unit_price_copper_feather": {"type": "integer", "minimum": 0, "maximum": 1000000},
                "quote_id": {"oneOf": [{"$ref": "#/$defs/ulid"}, {"type": "null"}]},
            },
            "additionalProperties": False,
        },
        "give_item_parameters": {
            "type": "object",
            "required": ["item_or_batch_id", "quantity", "gift_intent"],
            "properties": {
                "item_or_batch_id": {"$ref": "#/$defs/ulid"},
                "quantity": {"type": "integer", "minimum": 1, "maximum": 99},
                "gift_intent": {"enum": ["gift", "return", "fulfill_commitment", "aid"]},
            },
            "additionalProperties": False,
        },
        "use_object_parameters": {
            "type": "object",
            "required": ["object_id", "interaction_id"],
            "properties": {
                "object_id": {"$ref": "#/$defs/entity_ref"},
                "interaction_id": {"$ref": "#/$defs/stable_ref"},
            },
            "additionalProperties": False,
        },
        "craft_parameters": {
            "type": "object",
            "required": ["recipe_id", "recipe_version", "quantity", "target_inventory_id"],
            "properties": {
                "recipe_id": {"$ref": "#/$defs/stable_ref"},
                "recipe_version": {"type": "integer", "minimum": 1},
                "quantity": {"type": "integer", "minimum": 1, "maximum": 32},
                "target_inventory_id": {"$ref": "#/$defs/ulid"},
            },
            "additionalProperties": False,
        },
        "gather_parameters": {
            "type": "object",
            "required": ["resource_node_id", "resource_definition_id", "requested_quantity"],
            "properties": {
                "resource_node_id": {"$ref": "#/$defs/entity_ref"},
                "resource_definition_id": {"$ref": "#/$defs/stable_ref"},
                "requested_quantity": {"type": "integer", "minimum": 1, "maximum": 99},
            },
            "additionalProperties": False,
        },
        "explore_parameters": {
            "type": "object",
            "required": ["area_id", "exploration_mode", "maximum_game_minutes"],
            "properties": {
                "area_id": {"$ref": "#/$defs/stable_ref"},
                "exploration_mode": {"enum": ["survey", "search_resource", "search_route", "patrol"]},
                "maximum_game_minutes": {"type": "integer", "minimum": 1, "maximum": 360},
            },
            "additionalProperties": False,
        },
        "cast_spell_parameters": {
            "type": "object",
            "required": ["spell_id", "target_refs", "aim_point", "declared_purpose"],
            "properties": {
                "spell_id": {"$ref": "#/$defs/stable_ref"},
                "target_refs": {
                    "type": "array",
                    "maxItems": 8,
                    "uniqueItems": True,
                    "items": {"$ref": "#/$defs/entity_ref"},
                },
                "aim_point": {"oneOf": [{"$ref": "#/$defs/world_point"}, {"type": "null"}]},
                "declared_purpose": {"enum": ["utility", "healing", "defense", "combat", "ritual"]},
            },
            "additionalProperties": False,
        },
        "start_encounter_parameters": {
            "type": "object",
            "required": ["target_entity_ids", "reason_id", "preferred_resolution"],
            "properties": {
                "target_entity_ids": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 4,
                    "uniqueItems": True,
                    "items": {"$ref": "#/$defs/entity_ref"},
                },
                "reason_id": {"$ref": "#/$defs/stable_ref"},
                "preferred_resolution": {"enum": ["deescalate", "defend", "capture", "drive_off"]},
            },
            "additionalProperties": False,
        },
        "combat_action_parameters": {
            "type": "object",
            "required": ["encounter_id", "turn_index", "action_option_id", "target_combatant_ids"],
            "properties": {
                "encounter_id": {"$ref": "#/$defs/ulid"},
                "turn_index": {"type": "integer", "minimum": 0},
                "action_option_id": {"$ref": "#/$defs/stable_ref"},
                "target_combatant_ids": {
                    "type": "array",
                    "maxItems": 4,
                    "uniqueItems": True,
                    "items": {"$ref": "#/$defs/ulid"},
                },
            },
            "additionalProperties": False,
        },
        "build_parameters": {
            "type": "object",
            "required": ["building_template_id", "parcel_id", "permit_id", "orientation_degrees"],
            "properties": {
                "building_template_id": {"$ref": "#/$defs/stable_ref"},
                "parcel_id": {"$ref": "#/$defs/entity_ref"},
                "permit_id": {"$ref": "#/$defs/ulid"},
                "orientation_degrees": {"enum": [0, 90, 180, 270]},
            },
            "additionalProperties": False,
        },
        "repair_parameters": {
            "type": "object",
            "required": ["target_structure_id", "repair_definition_id", "maximum_material_budget_copper_feather"],
            "properties": {
                "target_structure_id": {"$ref": "#/$defs/entity_ref"},
                "repair_definition_id": {"$ref": "#/$defs/stable_ref"},
                "maximum_material_budget_copper_feather": {"type": "integer", "minimum": 0, "maximum": 10000000},
            },
            "additionalProperties": False,
        },
        "wait_parameters": {
            "type": "object",
            "required": ["duration_game_minutes", "reason_id"],
            "properties": {
                "duration_game_minutes": {"type": "integer", "minimum": 1, "maximum": 120},
                "reason_id": {"$ref": "#/$defs/stable_ref"},
            },
            "additionalProperties": False,
        },
        "observe_parameters": {
            "type": "object",
            "required": ["subject_ref", "observation_mode", "duration_game_minutes"],
            "properties": {
                "subject_ref": {"$ref": "#/$defs/entity_ref"},
                "observation_mode": {"enum": ["visual", "listen", "inspect", "assess"]},
                "duration_game_minutes": {"type": "integer", "minimum": 0, "maximum": 60},
            },
            "additionalProperties": False,
        },
    },
    "additionalProperties": False,
}


@dataclass(frozen=True)
class SchemaError:
    """单个 Schema 校验错误（DOC-AI-004 §8：JSON Pointer、keyword、reason code）"""

    pointer: str
    keyword: str
    reason_code: str


class SchemaDecodeError(Exception):
    """strict decode 失败"""

    def __init__(self, errors: list[SchemaError]):
        self.errors = errors
        summary = "; ".join(f"{e.pointer}: {e.keyword} ({e.reason_code})" for e in errors[:4])
        super().__init__(f"schema decode failed: {summary}")


@dataclass(frozen=True)
class DecodedProposal:
    """strict decode 后的模型提案（不含 server envelope）"""

    goal: str
    action: str
    target_entity_id: Optional[str]
    destination_id: Optional[str]
    parameters: dict[str, Any]
    spoken_text: Optional[str]
    emotion: str
    priority: int
    expected_duration_minutes: int
    abort_conditions: tuple[str, ...]
    raw: dict[str, Any] = field(compare=False)


_validator: Optional[jsonschema.Draft202012Validator] = None


def get_compiled_validator() -> jsonschema.Draft202012Validator:
    """启动时编译缓存（DOC-AI-004 §9）"""
    global _validator
    if _validator is None:
        jsonschema.Draft202012Validator.check_schema(ACTION_PROPOSAL_SCHEMA)
        _validator = jsonschema.Draft202012Validator(ACTION_PROPOSAL_SCHEMA)
    return _validator


def schema_action_ids() -> list[str]:
    """从 canonical schema 提取 action enum（供一致性测试）"""
    return list(ACTION_PROPOSAL_SCHEMA["properties"]["action"]["enum"])


def schema_branch_ids() -> list[str]:
    """从 allOf if/then 提取 discriminator 分支"""
    return [branch["if"]["properties"]["action"]["const"] for branch in ACTION_PROPOSAL_SCHEMA["allOf"]]


def schema_parameter_def_ids() -> list[str]:
    """从 $defs 提取 *_parameters 定义名（去掉后缀）"""
    return [
        name[: -len("_parameters")]
        for name in ACTION_PROPOSAL_SCHEMA["$defs"]
        if name.endswith("_parameters")
    ]


def _check_finite_numbers(value: Any, pointer: str = "") -> list[SchemaError]:
    """拒绝 NaN/Infinity（RULE-AI-020：数字有限、有界）"""
    errors: list[SchemaError] = []
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            errors.append(
                SchemaError(pointer=pointer or "/", keyword="finite", reason_code="non_finite_number")
            )
    elif isinstance(value, dict):
        for key, item in value.items():
            errors.extend(_check_finite_numbers(item, f"{pointer}/{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            errors.extend(_check_finite_numbers(item, f"{pointer}/{index}"))
    return errors


def decode_proposal(raw_bytes: bytes) -> DecodedProposal:
    """
    provider bytes -> strict decoded artifact（DOC-AI-004 §6）

    - UTF-8、大小、单 JSON object 检查
    - Draft 2020-12 strict decode
    - NaN/Infinity 拒绝
    - server-only 字段注入拒绝（additionalProperties=false 之外的显式 defense-in-depth）
    """
    if len(raw_bytes) > MAX_RESPONSE_BYTES:
        raise SchemaDecodeError(
            [SchemaError(pointer="/", keyword="maxBytes", reason_code="response_too_large")]
        )
    if len(raw_bytes) == 0:
        raise SchemaDecodeError(
            [SchemaError(pointer="/", keyword="minBytes", reason_code="empty_response")]
        )
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SchemaDecodeError(
            [SchemaError(pointer="/", keyword="encoding", reason_code="invalid_utf8")]
        ) from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SchemaDecodeError(
            [SchemaError(pointer="/", keyword="json", reason_code="invalid_json")]
        ) from exc
    if not isinstance(payload, dict):
        raise SchemaDecodeError(
            [SchemaError(pointer="/", keyword="type", reason_code="not_single_object")]
        )

    errors: list[SchemaError] = []
    for server_field in SERVER_ENVELOPE_FIELDS:
        if server_field in payload:
            errors.append(
                SchemaError(
                    pointer=f"/{server_field}",
                    keyword="serverOnly",
                    reason_code="server_field_spoof",
                )
            )

    errors.extend(_check_finite_numbers(payload))

    for err in get_compiled_validator().iter_errors(payload):
        pointer = "/" + "/".join(str(part) for part in err.absolute_path) if err.absolute_path else "/"
        errors.append(
            SchemaError(
                pointer=pointer,
                keyword=err.validator if isinstance(err.validator, str) else "schema",
                reason_code="schema_violation",
            )
        )

    if errors:
        raise SchemaDecodeError(errors)

    return DecodedProposal(
        goal=payload["goal"],
        action=payload["action"],
        target_entity_id=payload["target_entity_id"],
        destination_id=payload["destination_id"],
        parameters=dict(payload["parameters"]),
        spoken_text=payload["spoken_text"],
        emotion=payload["emotion"],
        priority=payload["priority"],
        expected_duration_minutes=payload["expected_duration_minutes"],
        abort_conditions=tuple(payload["abort_conditions"]),
        raw=payload,
    )


def proposal_from_dict(payload: dict[str, Any]) -> DecodedProposal:
    """从已解析 dict 构造（等价 strict decode，用于内部 fixture）"""
    return decode_proposal(json.dumps(payload, ensure_ascii=False).encode("utf-8"))


def canonical_action_set() -> frozenset[str]:
    """catalog/schema/常量三方一致性基准（RULE-AI-025）"""
    return frozenset(ACTION_IDS)


_ULID_PATTERN = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


def is_valid_ulid(value: str) -> bool:
    """ULID 格式检查（与 schema $defs/ulid 一致）"""
    return bool(_ULID_PATTERN.match(value))
