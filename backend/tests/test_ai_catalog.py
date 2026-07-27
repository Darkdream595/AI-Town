"""
测试 Action Catalog 与跨字段语义表

覆盖 TEST-AI-017/018（DOC-AI-005 §11）
"""

import pytest

from src.ai import ACTION_CATALOG, validate_cross_field_semantics
from src.ai.schema import proposal_from_dict

from ai_helpers import ULID_B, make_valid_proposal


class TestCatalogIntegrity:
    """TEST-AI-017：catalog 行均能解析 owner、参数 ref、committed event"""

    def test_catalog_has_19_entries(self):
        assert len(ACTION_CATALOG) == 19

    @pytest.mark.parametrize(
        "action,entry", sorted(ACTION_CATALOG.items()), ids=sorted(ACTION_CATALOG.keys())
    )
    def test_entry_fields(self, action, entry):
        assert entry.action_id == action
        assert entry.parameters_ref == f"{action}_parameters"
        assert entry.owner_domain
        assert entry.committed_event


class TestCrossFieldSemantics:
    """TEST-AI-018：跨字段语义表"""

    @pytest.mark.parametrize("action", sorted(ACTION_CATALOG.keys()))
    def test_valid_fixtures_pass(self, action):
        proposal = proposal_from_dict(make_valid_proposal(action))
        assert validate_cross_field_semantics(proposal) == []

    def test_talk_target_required(self):
        payload = make_valid_proposal("talk")
        payload["target_entity_id"] = None
        proposal = proposal_from_dict(payload)
        violations = validate_cross_field_semantics(proposal)
        assert any(v.reason_code == "target_required" for v in violations)

    def test_buy_destination_required(self):
        payload = make_valid_proposal("buy")
        payload["destination_id"] = None
        proposal = proposal_from_dict(payload)
        violations = validate_cross_field_semantics(proposal)
        assert any(v.reason_code == "destination_required" for v in violations)

    def test_work_target_and_destination_must_be_null(self):
        # TEST-AI-018 指定负例：work 顶层 destination/target 非 null
        payload = make_valid_proposal("work")
        payload["target_entity_id"] = ULID_B
        payload["destination_id"] = "semantic_node.crown_creek.market"
        proposal = proposal_from_dict(payload)
        violations = validate_cross_field_semantics(proposal)
        reason_codes = {v.reason_code for v in violations}
        assert "target_must_be_null" in reason_codes
        assert "destination_must_be_null" in reason_codes

    def test_eat_target_must_be_null(self):
        payload = make_valid_proposal("eat")
        payload["target_entity_id"] = ULID_B
        proposal = proposal_from_dict(payload)
        violations = validate_cross_field_semantics(proposal)
        assert any(v.reason_code == "target_must_be_null" for v in violations)

    def test_move_to_semantic_node_requires_destination(self):
        payload = make_valid_proposal("move_to")
        payload["destination_id"] = None
        proposal = proposal_from_dict(payload)
        violations = validate_cross_field_semantics(proposal)
        assert any(v.reason_code == "destination_required" for v in violations)

    def test_move_to_world_point_mode(self):
        payload = make_valid_proposal("move_to")
        payload["destination_id"] = None
        payload["parameters"] = {
            "destination_kind": "world_point",
            "world_point": {"scene_id": "region.crown_creek_town", "x_wu": 100.0, "y_wu": 200.0},
            "arrival_radius_wu": 2.0,
            "movement_mode": "normal",
        }
        proposal = proposal_from_dict(payload)
        assert validate_cross_field_semantics(proposal) == []

    def test_move_to_world_point_mode_with_destination_rejected(self):
        payload = make_valid_proposal("move_to")
        payload["parameters"]["destination_kind"] = "world_point"
        payload["parameters"]["world_point"] = {
            "scene_id": "region.crown_creek_town",
            "x_wu": 100.0,
            "y_wu": 200.0,
        }
        proposal = proposal_from_dict(payload)
        violations = validate_cross_field_semantics(proposal)
        assert any(v.reason_code == "destination_must_be_null" for v in violations)

    def test_unknown_action_flagged(self):
        payload = make_valid_proposal("wait")
        proposal = proposal_from_dict(payload)
        object.__setattr__(proposal, "action", "fly")
        violations = validate_cross_field_semantics(proposal)
        assert any(v.reason_code == "unknown_action" for v in violations)
