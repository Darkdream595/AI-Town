"""
记忆、信念与社会认知数据模型

符合 DOC-MEMORY-001：MemoryRecordV1 strict Schema、五种封闭认知类型、Provenance。
- RULE-MEMORY-001：memory_kind 与 payload discriminator 必须一致
- RULE-MEMORY-003：非 tombstone 记录必须有来源
- RULE-MEMORY-005：SemanticBelief 不含 is_true/objective_truth 字段
- RULE-MEMORY-008：tombstoned 记录的 payload 必须为 null
"""

from __future__ import annotations

from typing import Any, Optional

import jsonschema

MEMORY_RECORD_SCHEMA_ID = "schema://ai-town/memory/record/v1"

#: 五种封闭认知类型
MEMORY_KINDS: tuple[str, ...] = (
    "episodic_memory",
    "semantic_belief",
    "social_impression",
    "commitment",
    "routine_knowledge",
)

MEMORY_STATES: tuple[str, ...] = ("active", "cold", "reactivated", "tombstoned")

SOURCE_KINDS: tuple[str, ...] = (
    "domain_event",
    "direct_observation",
    "testimony",
    "inference",
    "self_commitment",
    "routine_training",
)

_ULID_PATTERN = "^[0-9A-HJKMNP-TV-Z]{26}$"
_STABLE_PATTERN = "^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)+$"

# Canonical JSON Schema（DOC-MEMORY-001 §4 code block 拷贝）
MEMORY_RECORD_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": MEMORY_RECORD_SCHEMA_ID,
    "type": "object",
    "required": [
        "schema_version",
        "memory_id",
        "world_id",
        "memory_owner_id",
        "memory_kind",
        "state",
        "created_at_revision",
        "created_at_game_time",
        "last_reactivated_game_time",
        "importance_q1000",
        "confidence_q1000",
        "subject_refs",
        "semantic_tags",
        "provenance",
        "access_policy_id",
        "payload",
        "record_version",
    ],
    "properties": {
        "schema_version": {"const": 1},
        "memory_id": {"type": "string", "pattern": _ULID_PATTERN},
        "world_id": {"type": "string", "pattern": _ULID_PATTERN},
        "memory_owner_id": {"type": "string", "pattern": _ULID_PATTERN},
        "memory_kind": {"enum": list(MEMORY_KINDS)},
        "state": {"enum": list(MEMORY_STATES)},
        "created_at_revision": {"type": "integer", "minimum": 0},
        "created_at_game_time": {"type": "integer", "minimum": 0},
        "last_reactivated_game_time": {"type": ["integer", "null"], "minimum": 0},
        "importance_q1000": {"type": "integer", "minimum": 0, "maximum": 1000},
        "confidence_q1000": {"type": "integer", "minimum": 0, "maximum": 1000},
        "subject_refs": {
            "type": "array",
            "maxItems": 32,
            "uniqueItems": True,
            "items": {"type": "string", "minLength": 1, "maxLength": 128},
        },
        "semantic_tags": {
            "type": "array",
            "maxItems": 32,
            "uniqueItems": True,
            "items": {"type": "string", "pattern": _STABLE_PATTERN},
        },
        "provenance": {"$ref": "#/$defs/provenance"},
        "access_policy_id": {"type": "string", "pattern": _ULID_PATTERN},
        "payload": {
            "oneOf": [
                {"$ref": "#/$defs/episodic"},
                {"$ref": "#/$defs/belief"},
                {"$ref": "#/$defs/impression"},
                {"$ref": "#/$defs/commitment"},
                {"$ref": "#/$defs/routine"},
                {"type": "null"},
            ]
        },
        "record_version": {"type": "integer", "minimum": 1},
    },
    "allOf": [
        {
            "if": {"properties": {"state": {"const": "tombstoned"}}},
            "then": {"properties": {"payload": {"type": "null"}}},
            "else": {"properties": {"payload": {"not": {"type": "null"}}}},
        },
        # 文档 code block 的 kind 判别无条件生效，与 §4 文本「其他状态必须匹配」矛盾：
        # tombstoned + payload=null 永远无法通过 kind 检查。按 §4 文本意图，
        # kind 判别仅在非 tombstoned 状态生效（state 为顶层 required，判定确定）。
        {
            "if": {"properties": {"memory_kind": {"const": "episodic_memory"}, "state": {"enum": ["active", "cold", "reactivated"]}}},
            "then": {"properties": {"payload": {"$ref": "#/$defs/episodic"}}},
        },
        {
            "if": {"properties": {"memory_kind": {"const": "semantic_belief"}, "state": {"enum": ["active", "cold", "reactivated"]}}},
            "then": {"properties": {"payload": {"$ref": "#/$defs/belief"}}},
        },
        {
            "if": {"properties": {"memory_kind": {"const": "social_impression"}, "state": {"enum": ["active", "cold", "reactivated"]}}},
            "then": {"properties": {"payload": {"$ref": "#/$defs/impression"}}},
        },
        {
            "if": {"properties": {"memory_kind": {"const": "commitment"}, "state": {"enum": ["active", "cold", "reactivated"]}}},
            "then": {"properties": {"payload": {"$ref": "#/$defs/commitment"}}},
        },
        {
            "if": {"properties": {"memory_kind": {"const": "routine_knowledge"}, "state": {"enum": ["active", "cold", "reactivated"]}}},
            "then": {"properties": {"payload": {"$ref": "#/$defs/routine"}}},
        },
    ],
    "$defs": {
        "provenance": {
            "type": "object",
            "required": [
                "source_kind",
                "source_event_ids",
                "origin_actor_id",
                "direct_observer_id",
                "derived_from_memory_ids",
                "transform_rule_ids",
                "source_revision",
            ],
            "properties": {
                "source_kind": {"enum": list(SOURCE_KINDS)},
                "source_event_ids": {
                    "type": "array",
                    "maxItems": 16,
                    "uniqueItems": True,
                    "items": {"type": "string", "pattern": _ULID_PATTERN},
                },
                "origin_actor_id": {"type": ["string", "null"], "pattern": _ULID_PATTERN},
                "direct_observer_id": {"type": ["string", "null"], "pattern": _ULID_PATTERN},
                "derived_from_memory_ids": {
                    "type": "array",
                    "maxItems": 64,
                    "uniqueItems": True,
                    "items": {"type": "string", "pattern": _ULID_PATTERN},
                },
                "transform_rule_ids": {
                    "type": "array",
                    "maxItems": 16,
                    "items": {"type": "string", "pattern": "^RULE-MEMORY-[0-9]{3}$"},
                },
                "source_revision": {"type": "integer", "minimum": 0},
            },
            "anyOf": [
                {"properties": {"source_event_ids": {"minItems": 1}}},
                {"properties": {"derived_from_memory_ids": {"minItems": 1}}},
            ],
            "additionalProperties": False,
        },
        "episodic": {
            "type": "object",
            "required": [
                "kind",
                "representation",
                "summary_text",
                "participant_ids",
                "location_ids",
                "emotion_id",
                "emotion_intensity_q1000",
                "source_memory_ids",
            ],
            "properties": {
                "kind": {"const": "episodic_memory"},
                "representation": {"enum": ["direct_episode", "consolidated_summary"]},
                "summary_text": {"type": "string", "minLength": 1, "maxLength": 1024},
                "participant_ids": {
                    "type": "array",
                    "maxItems": 16,
                    "uniqueItems": True,
                    "items": {"type": "string", "minLength": 1, "maxLength": 128},
                },
                "location_ids": {
                    "type": "array",
                    "maxItems": 8,
                    "uniqueItems": True,
                    "items": {"type": "string", "minLength": 1, "maxLength": 128},
                },
                "emotion_id": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
                "emotion_intensity_q1000": {"type": "integer", "minimum": 0, "maximum": 1000},
                "source_memory_ids": {
                    "type": "array",
                    "maxItems": 64,
                    "uniqueItems": True,
                    "items": {"type": "string", "pattern": _ULID_PATTERN},
                },
            },
            "additionalProperties": False,
        },
        "belief": {
            "type": "object",
            "required": ["kind", "claim", "evidence_memory_ids", "contradiction_memory_ids"],
            "properties": {
                "kind": {"const": "semantic_belief"},
                "claim": {
                    "type": "object",
                    "required": ["predicate_id", "subject_ref", "object_value"],
                    "properties": {
                        "predicate_id": {"type": "string", "pattern": _STABLE_PATTERN},
                        "subject_ref": {"type": "string", "minLength": 1, "maxLength": 128},
                        "object_value": {"type": ["string", "number", "integer", "boolean", "null"]},
                    },
                    "additionalProperties": False,
                },
                "evidence_memory_ids": {
                    "type": "array",
                    "maxItems": 32,
                    "uniqueItems": True,
                    "items": {"type": "string", "pattern": _ULID_PATTERN},
                },
                "contradiction_memory_ids": {
                    "type": "array",
                    "maxItems": 32,
                    "uniqueItems": True,
                    "items": {"type": "string", "pattern": _ULID_PATTERN},
                },
            },
            "additionalProperties": False,
        },
        "impression": {
            "type": "object",
            "required": ["kind", "target_resident_id", "trait_id", "valence_q1000", "evidence_memory_ids"],
            "properties": {
                "kind": {"const": "social_impression"},
                "target_resident_id": {"type": "string", "pattern": _ULID_PATTERN},
                "trait_id": {"type": "string", "pattern": _STABLE_PATTERN},
                "valence_q1000": {"type": "integer", "minimum": -1000, "maximum": 1000},
                "evidence_memory_ids": {
                    "type": "array",
                    "maxItems": 32,
                    "uniqueItems": True,
                    "items": {"type": "string", "pattern": _ULID_PATTERN},
                },
            },
            "additionalProperties": False,
        },
        "commitment": {
            "type": "object",
            "required": [
                "kind",
                "commitment_id",
                "promisor_id",
                "beneficiary_ids",
                "terms_id",
                "deadline_game_time",
                "status",
            ],
            "properties": {
                "kind": {"const": "commitment"},
                "commitment_id": {"type": "string", "pattern": _ULID_PATTERN},
                "promisor_id": {"type": "string", "pattern": _ULID_PATTERN},
                "beneficiary_ids": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 16,
                    "uniqueItems": True,
                    "items": {"type": "string", "pattern": _ULID_PATTERN},
                },
                "terms_id": {"type": "string", "pattern": _STABLE_PATTERN},
                "deadline_game_time": {"type": ["integer", "null"], "minimum": 0},
                "status": {
                    "enum": ["proposed", "accepted", "fulfilled", "breached", "released", "expired"]
                },
            },
            "additionalProperties": False,
        },
        "routine": {
            "type": "object",
            "required": ["kind", "procedure_id", "step_action_ids", "proficiency_q1000", "last_success_event_id"],
            "properties": {
                "kind": {"const": "routine_knowledge"},
                "procedure_id": {"type": "string", "pattern": _STABLE_PATTERN},
                "step_action_ids": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 32,
                    "items": {"type": "string", "pattern": _STABLE_PATTERN},
                },
                "proficiency_q1000": {"type": "integer", "minimum": 0, "maximum": 1000},
                "last_success_event_id": {"type": ["string", "null"], "pattern": _ULID_PATTERN},
            },
            "additionalProperties": False,
        },
    },
    "additionalProperties": False,
}

_record_validator: Optional[jsonschema.Draft202012Validator] = None


def get_record_validator() -> jsonschema.Draft202012Validator:
    global _record_validator
    if _record_validator is None:
        jsonschema.Draft202012Validator.check_schema(MEMORY_RECORD_SCHEMA)
        _record_validator = jsonschema.Draft202012Validator(MEMORY_RECORD_SCHEMA)
    return _record_validator


class MemorySchemaError(Exception):
    """MEMORY_SCHEMA_INVALID / MEMORY_KIND_MISMATCH"""

    def __init__(self, reason_code: str, detail: str):
        self.reason_code = reason_code
        super().__init__(f"{reason_code}: {detail}")


#: SemanticBelief 禁止出现的客观真值字段（RULE-MEMORY-005）
FORBIDDEN_TRUTH_FIELDS: frozenset[str] = frozenset({"is_true", "objective_truth"})


def validate_memory_record(record: dict[str, Any]) -> dict[str, Any]:
    """strict 校验 MemoryRecordV1；通过则原样返回"""
    errors = list(get_record_validator().iter_errors(record))
    if errors:
        first = errors[0]
        pointer = "/" + "/".join(str(p) for p in first.absolute_path) if first.absolute_path else "/"
        raise MemorySchemaError("MEMORY_SCHEMA_INVALID", f"{pointer}: {first.message}")

    if record["state"] != "tombstoned" and record["memory_kind"] == "semantic_belief":
        claim = record["payload"]["claim"]
        for forbidden in FORBIDDEN_TRUTH_FIELDS:
            if forbidden in claim:
                raise MemorySchemaError(
                    "MEMORY_SCHEMA_INVALID", f"SemanticBelief 禁止客观真值字段 {forbidden}"
                )

    # RULE-MEMORY-004：source_revision <= created_at_revision
    if record["provenance"]["source_revision"] > record["created_at_revision"]:
        raise MemorySchemaError(
            "MEMORY_SCHEMA_INVALID", "source_revision > created_at_revision"
        )
    return record


def memory_metadata_projection(record: dict[str, Any]) -> dict[str, Any]:
    """
    metadata-only 投影（RULE-MEMORY-007）

    不含 payload、summary_text、claim object 或 secret participant。
    """
    return {
        "memory_id": record["memory_id"],
        "memory_kind": record["memory_kind"],
        "state": record["state"],
        "memory_owner_id": record["memory_owner_id"],
        "created_at_revision": record["created_at_revision"],
        "created_at_game_time": record["created_at_game_time"],
        "last_reactivated_game_time": record["last_reactivated_game_time"],
        "importance_q1000": record["importance_q1000"],
        "confidence_q1000": record["confidence_q1000"],
        "subject_refs": list(record["subject_refs"]),
        "semantic_tags": list(record["semantic_tags"]),
        "access_policy_id": record["access_policy_id"],
        "record_version": record["record_version"],
    }
