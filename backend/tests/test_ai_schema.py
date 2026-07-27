"""
测试 ActionProposal 严格 Schema

覆盖 TEST-AI-013/014/015/016/046（DOC-AI-004 §11）
"""

import json

import pytest

from src.ai import (
    ACTION_CATALOG,
    SERVER_ENVELOPE_FIELDS,
    SchemaDecodeError,
    catalog_action_set,
    decode_proposal,
    schema_action_ids,
    schema_branch_ids,
    schema_parameter_def_ids,
)
from src.ai.constants import ACTION_IDS
from src.ai.schema import ACTION_PROPOSAL_SCHEMA, get_compiled_validator

from ai_helpers import ULID_B, make_proposal_bytes, make_valid_proposal


class TestSchemaCompile:
    """TEST-AI-013：Schema compile 与 canonical round-trip"""

    def test_schema_compiles(self):
        validator = get_compiled_validator()
        assert validator is not None

    def test_schema_id(self):
        assert ACTION_PROPOSAL_SCHEMA["$id"] == "schema://ai-town/ai/action-proposal/v1"

    @pytest.mark.parametrize("action", ACTION_IDS)
    def test_valid_proposal_round_trip(self, action):
        payload = make_valid_proposal(action)
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        decoded = decode_proposal(raw)
        assert decoded.action == action
        assert decoded.raw == payload


class TestDiscriminatorCoverage:
    """TEST-AI-014 / TEST-AI-046：19 action discriminator 全覆盖且集合相等"""

    def test_action_enum_count(self):
        assert len(schema_action_ids()) == 19

    def test_enum_branch_defs_catalog_sets_equal(self):
        expected = frozenset(ACTION_IDS)
        assert frozenset(schema_action_ids()) == expected
        assert frozenset(schema_branch_ids()) == expected
        assert frozenset(schema_parameter_def_ids()) == expected
        assert catalog_action_set() == expected
        assert frozenset(ACTION_CATALOG.keys()) == expected


class TestNegativeCorpus:
    """TEST-AI-015：additionalProperties/range/ID negative corpus"""

    def test_missing_required_field_rejected(self):
        payload = make_valid_proposal("wait")
        del payload["goal"]
        with pytest.raises(SchemaDecodeError):
            decode_proposal(json.dumps(payload).encode("utf-8"))

    def test_extra_field_rejected(self):
        payload = make_valid_proposal("wait")
        payload["unexpected_field"] = 1
        with pytest.raises(SchemaDecodeError):
            decode_proposal(json.dumps(payload).encode("utf-8"))

    def test_extra_parameters_field_rejected(self):
        payload = make_valid_proposal("wait")
        payload["parameters"]["rogue"] = True
        with pytest.raises(SchemaDecodeError):
            decode_proposal(json.dumps(payload).encode("utf-8"))

    def test_priority_out_of_range_rejected(self):
        with pytest.raises(SchemaDecodeError):
            decode_proposal(make_proposal_bytes("wait", priority=101))

    def test_priority_bool_rejected(self):
        # JSON 中 bool 不是 integer
        with pytest.raises(SchemaDecodeError):
            decode_proposal(make_proposal_bytes("wait", priority=True))

    def test_lowercase_ulid_rejected(self):
        payload = make_valid_proposal("eat")
        payload["parameters"]["item_or_batch_id"] = "01k1ab2cd3ef4gh5jk6mnp7qrs"
        with pytest.raises(SchemaDecodeError):
            decode_proposal(json.dumps(payload).encode("utf-8"))

    def test_uppercase_stable_ref_rejected(self):
        payload = make_valid_proposal("wait")
        payload["parameters"]["reason_id"] = "Reason.Wait_For_Shop"
        with pytest.raises(SchemaDecodeError):
            decode_proposal(json.dumps(payload).encode("utf-8"))

    def test_wrong_parameters_branch_rejected(self):
        # wait 的 action 配 move_to 的 parameters → 错分支
        payload = make_valid_proposal("wait")
        payload["parameters"] = {
            "destination_kind": "semantic_node",
            "world_point": None,
            "arrival_radius_wu": 2.0,
            "movement_mode": "normal",
        }
        with pytest.raises(SchemaDecodeError):
            decode_proposal(json.dumps(payload).encode("utf-8"))

    def test_unknown_action_rejected(self):
        payload = make_valid_proposal("wait")
        payload["action"] = "fly"
        with pytest.raises(SchemaDecodeError):
            decode_proposal(json.dumps(payload).encode("utf-8"))

    def test_nan_rejected(self):
        raw = b'{"goal":"g","action":"wait","target_entity_id":null,"destination_id":null,"parameters":{"duration_game_minutes":NaN,"reason_id":"reason.a.b"},"spoken_text":null,"emotion":"calm","priority":1,"expected_duration_minutes":1,"abort_conditions":[]}'
        with pytest.raises(SchemaDecodeError):
            decode_proposal(raw)

    def test_duplicate_abort_conditions_rejected(self):
        with pytest.raises(SchemaDecodeError):
            decode_proposal(
                make_proposal_bytes("wait", abort_conditions=["danger_detected", "danger_detected"])
            )

    def test_overlong_spoken_text_rejected(self):
        with pytest.raises(SchemaDecodeError):
            decode_proposal(make_proposal_bytes("talk", spoken_text="x" * 281))

    def test_empty_response_rejected(self):
        with pytest.raises(SchemaDecodeError):
            decode_proposal(b"")

    def test_oversized_response_rejected(self):
        with pytest.raises(SchemaDecodeError):
            decode_proposal(b" " * (16 * 1024 + 1))

    def test_non_object_rejected(self):
        with pytest.raises(SchemaDecodeError):
            decode_proposal(b"[1,2,3]")


class TestServerEnvelopeSpoof:
    """TEST-AI-016：server-only 字段注入被拒绝"""

    @pytest.mark.parametrize("server_field", list(SERVER_ENVELOPE_FIELDS)[:6])
    def test_server_field_spoof_rejected(self, server_field):
        payload = make_valid_proposal("wait")
        payload[server_field] = ULID_B if server_field.endswith("_id") else 1
        with pytest.raises(SchemaDecodeError) as exc_info:
            decode_proposal(json.dumps(payload).encode("utf-8"))
        assert any(e.reason_code == "server_field_spoof" for e in exc_info.value.errors)
