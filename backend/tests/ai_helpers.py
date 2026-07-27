"""
AI 测试共享 fixture：19 个 Action 的合法 Proposal 模板

所有模板严格符合 DOC-AI-004 canonical schema 与 DOC-AI-005 跨字段语义表。
"""

from __future__ import annotations

import copy
import json
from typing import Any

ULID_A = "01K1AB2CD3EF4GH5JK6MNP7QRS"
ULID_B = "01K1AB2CD3EF4GH5JK6MNP7QRT"
ULID_C = "01K1AB2CD3EF4GH5JK6MNP7QRW"
ULID_D = "01K1AB2CD3EF4GH5JK6MNP7QRV"

STABLE_NODE = "semantic_node.crown_creek.market"
STABLE_AREA = "semantic_area.crown_creek.market"


def _base(action: str, parameters: dict[str, Any]) -> dict[str, Any]:
    return {
        "goal": "完成当日工作",
        "action": action,
        "target_entity_id": None,
        "destination_id": None,
        "parameters": parameters,
        "spoken_text": None,
        "emotion": "calm",
        "priority": 50,
        "expected_duration_minutes": 30,
        "abort_conditions": ["danger_detected"],
    }


VALID_PROPOSAL_TEMPLATES: dict[str, dict[str, Any]] = {
    "move_to": _base(
        "move_to",
        {"destination_kind": "semantic_node", "world_point": None, "arrival_radius_wu": 2.0, "movement_mode": "normal"},
    )
    | {"destination_id": STABLE_NODE},
    "talk": _base(
        "talk",
        {"topic_id": "topic.market.gossip", "conversation_intent": "greet", "privacy": "public"},
    )
    | {"target_entity_id": ULID_B},
    "work": _base(
        "work",
        {"employment_contract_id": ULID_A, "shift_id": ULID_B, "workplace_id": "building.crown_creek.apothecary"},
    ),
    "rest": _base(
        "rest",
        {"rest_kind": "sleep", "minimum_game_minutes": 360, "rest_node_id": "semantic_node.residence.elise_home"},
    )
    | {"destination_id": "semantic_node.residence.elise_home"},
    "eat": _base("eat", {"item_or_batch_id": ULID_A, "quantity": 1}),
    "buy": _base(
        "buy",
        {"item_definition_id": "item.herb.healing", "quantity": 2, "maximum_unit_price_copper_feather": 50, "quote_id": None},
    )
    | {"target_entity_id": ULID_B, "destination_id": STABLE_NODE},
    "sell": _base(
        "sell",
        {"item_or_batch_id": ULID_A, "quantity": 1, "minimum_unit_price_copper_feather": 30, "quote_id": None},
    )
    | {"target_entity_id": ULID_B, "destination_id": STABLE_NODE},
    "give_item": _base(
        "give_item",
        {"item_or_batch_id": ULID_A, "quantity": 1, "gift_intent": "gift"},
    )
    | {"target_entity_id": ULID_B},
    "use_object": _base(
        "use_object",
        {"object_id": "object.crown_creek.well", "interaction_id": "interaction.draw_water"},
    )
    | {"target_entity_id": "object.crown_creek.well"},
    "craft": _base(
        "craft",
        {"recipe_id": "recipe.potion.healing", "recipe_version": 1, "quantity": 1, "target_inventory_id": ULID_C},
    )
    | {"destination_id": "semantic_node.crown_creek.workshop"},
    "gather": _base(
        "gather",
        {"resource_node_id": "resource.duskwood.herb_patch", "resource_definition_id": "resource.herb.common", "requested_quantity": 3},
    )
    | {"target_entity_id": "resource.duskwood.herb_patch"},
    "explore": _base(
        "explore",
        {"area_id": STABLE_AREA, "exploration_mode": "survey", "maximum_game_minutes": 120},
    )
    | {"destination_id": STABLE_AREA},
    "cast_spell": _base(
        "cast_spell",
        {"spell_id": "spell.light.minor", "target_refs": [ULID_B], "aim_point": None, "declared_purpose": "utility"},
    ),
    "start_encounter": _base(
        "start_encounter",
        {"target_entity_ids": [ULID_B], "reason_id": "reason.defend_self", "preferred_resolution": "deescalate"},
    )
    | {"target_entity_id": ULID_B},
    "combat_action": _base(
        "combat_action",
        {"encounter_id": ULID_A, "turn_index": 0, "action_option_id": "combat.option.defend", "target_combatant_ids": [ULID_C]},
    ),
    "build": _base(
        "build",
        {"building_template_id": "building.cottage.small", "parcel_id": "parcel.crown_creek.north_1", "permit_id": ULID_D, "orientation_degrees": 90},
    )
    | {"destination_id": "parcel.crown_creek.north_1"},
    "repair": _base(
        "repair",
        {"target_structure_id": "structure.crown_creek.bridge", "repair_definition_id": "repair.wooden.basic", "maximum_material_budget_copper_feather": 500},
    )
    | {"target_entity_id": "structure.crown_creek.bridge"},
    "wait": _base(
        "wait",
        {"duration_game_minutes": 15, "reason_id": "reason.wait_for_shop_open"},
    ),
    "observe": _base(
        "observe",
        {"subject_ref": ULID_B, "observation_mode": "visual", "duration_game_minutes": 5},
    )
    | {"target_entity_id": ULID_B},
}


def make_valid_proposal(action: str) -> dict[str, Any]:
    """生成指定 action 的合法 proposal dict"""
    return copy.deepcopy(VALID_PROPOSAL_TEMPLATES[action])


def make_proposal_bytes(action: str, **overrides: Any) -> bytes:
    """生成合法 proposal 的 JSON bytes，可覆盖顶层字段"""
    payload = make_valid_proposal(action)
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def make_context_json(resident_id: str = ULID_A) -> str:
    """最小合法 DecisionContext canonical JSON"""
    context = {
        "schema_version": 1,
        "resident_id": resident_id,
        "observed_revision": 84,
        "observed_game_time": 1830,
        "self": {
            "resident_revision": 82,
            "identity_summary": {"display_name": "艾莉丝"},
            "personality_dimensions": {"caution": 68, "empathy": 71},
            "value_ids": ["value.community"],
            "need_bands": {"hunger": "warning", "fatigue": "normal", "safety": "normal"},
            "health_condition": "healthy",
            "capability_ids": ["ability.herbalism.identify_common"],
            "assignment_ids": ["profession.apothecary"],
        },
        "position": {
            "scene_id": "region.crown_creek_town",
            "semantic_area_ids": ["semantic_area.crown_creek.market"],
            "navigation_revision": 84,
        },
        "perceived_entities": [],
        "beliefs": [],
        "memories": [],
        "commitments": [],
        "available_action_ids": ["move_to", "observe", "wait"],
        "unknown_or_redacted": ["shop.ledger.private"],
        "visibility_proofs": [],
    }
    return json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
