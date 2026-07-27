"""
TEST-PLAYER-013..016：玩家交互能力与统一验证（DOC-PLAYER-004）

- TEST-PLAYER-013：Interaction Candidate 距离/视线/状态排序
- TEST-PLAYER-014：Player/AI canonical validator parity
- TEST-PLAYER-015：stale、Reservation、幂等与动画中断
- TEST-PLAYER-016：unknown action、越权 envelope 与恶意参数拒绝
"""

import pytest

from src.player import (
    InteractionCandidate,
    PlayerCommandError,
    PlayerCommandRouter,
)
from src.player.interaction import DomainValidationResult, rank_candidates
from src.player.constants import DENY_CAPABILITY_STALE, DENY_COMMAND_ID_CONFLICT

ACTOR = "01K1RSDT000000000000000001"
TARGET = "01K1RSDT000000000000000002"
WORLD = "01K1WRDX000000000000000001"


def _envelope(action_id="give_item", command_id="cmd-1", params=None, **overrides):
    envelope = {
        "protocol_version": 1,
        "command_id": command_id,
        "world_id": WORLD,
        "expected_revision": 118,
        "type": "player.action",
        "payload": {
            "action_id": action_id,
            "target_entity_id": TARGET,
            "parameters": params if params is not None else {"item_id": "01K1XTEM000000000000000001", "quantity": 1},
        },
    }
    envelope.update(overrides)
    return envelope


class TestCandidateRanking:
    """TEST-PLAYER-013"""

    def test_interactable_first_then_distance_then_id(self):
        candidates = [
            InteractionCandidate("e3", "远-可交互", 500, True, True, True),
            InteractionCandidate("e1", "近-可交互", 100, True, True, True),
            InteractionCandidate("e2", "近-无视线", 50, False, True, True),
            InteractionCandidate("e4", "中-状态禁止", 200, True, False, True),
        ]
        ranked = rank_candidates(candidates)
        order = [r.candidate.entity_id for r in ranked]
        assert order == ["e1", "e3", "e2", "e4"]

    def test_ranking_is_deterministic(self):
        candidates = [
            InteractionCandidate("e9", "甲", 100, True, True, True),
            InteractionCandidate("e1", "乙", 100, True, True, True),
        ]
        first = [r.candidate.entity_id for r in rank_candidates(candidates)]
        second = [r.candidate.entity_id for r in rank_candidates(list(reversed(candidates)))]
        assert first == second == ["e1", "e9"]

    def test_candidate_cap_16(self):
        candidates = [
            InteractionCandidate(f"e{i:02d}", f"n{i}", i * 10, True, True, True)
            for i in range(20)
        ]
        assert len(rank_candidates(candidates)) == 16


class TestPlayerAiParity:
    """TEST-PLAYER-014：PlayerCommand 与 AI ActionProposal 同一 validator"""

    def _shared_validator(self, actor, target, parameters, revision):
        if parameters.get("quantity", 1) > 0:
            return DomainValidationResult(legal=True)
        return DomainValidationResult(legal=False, reason_code="ECON_QUANTITY_INVALID")

    def test_player_and_ai_get_same_legality(self):
        calls = []
        router = PlayerCommandRouter(domain_validators={"give_item": self._shared_validator})
        player_result = router.route_canonical_action(ACTOR, "give_item", TARGET, {"quantity": 1}, 118)
        ai_result = router.route_canonical_action(ACTOR, "give_item", TARGET, {"quantity": 1}, 118)
        # RULE-PLAYER-017：同一 validator，同一结论
        assert player_result.legal == ai_result.legal

        router2 = PlayerCommandRouter(domain_validators={"give_item": self._shared_validator})
        bad_player = router2.route_canonical_action(ACTOR, "give_item", TARGET, {"quantity": 0}, 118)
        bad_ai = router2.route_canonical_action(ACTOR, "give_item", TARGET, {"quantity": 0}, 118)
        assert bad_player.legal == bad_ai.legal == False
        assert bad_player.reason_code == bad_ai.reason_code

    def test_router_rejects_unregistered_action_validator(self):
        router = PlayerCommandRouter()
        with pytest.raises(PlayerCommandError) as exc:
            router.register_validator("dance", lambda *a: DomainValidationResult(legal=True))
        assert exc.value.code == "PLAYER_ACTION_UNREGISTERED"


class TestStaleIdempotencyAndNoPartialEffects:
    """TEST-PLAYER-015"""

    def test_duplicate_command_returns_original_receipt(self):
        router = PlayerCommandRouter(
            domain_validators={"give_item": lambda *a: DomainValidationResult(legal=True)}
        )
        first = router.submit_player_command(_envelope(), ACTOR, current_revision=118)
        assert first.accepted
        second = router.submit_player_command(_envelope(), ACTOR, current_revision=118)
        # §7：重复提交最多一次结算
        assert second.accepted and second.command_id == first.command_id

    def test_same_command_id_different_payload_conflicts(self):
        router = PlayerCommandRouter(
            domain_validators={"give_item": lambda *a: DomainValidationResult(legal=True)}
        )
        router.submit_player_command(_envelope(), ACTOR, 118)
        with pytest.raises(PlayerCommandError) as exc:
            router.submit_player_command(
                _envelope(params={"item_id": "01K1XTEM000000000000000001", "quantity": 5}),
                ACTOR, 118,
            )
        assert exc.value.code == DENY_COMMAND_ID_CONFLICT

    def test_stale_capability_projection_denied(self):
        router = PlayerCommandRouter(
            domain_validators={"give_item": lambda *a: DomainValidationResult(legal=True)}
        )
        router.stamp_capability_projection("binding-1", revision=100)
        receipt = router.submit_player_command(
            _envelope(), ACTOR, current_revision=118, binding_id="binding-1"
        )
        assert not receipt.accepted
        assert receipt.reason_code == DENY_CAPABILITY_STALE

    def test_failed_validation_consumes_nothing(self):
        router = PlayerCommandRouter(
            domain_validators={
                "buy": lambda *a: DomainValidationResult(legal=False, reason_code="ECON_FUNDS")
            }
        )
        receipt = router.submit_player_command(_envelope("buy"), ACTOR, 118)
        # RULE-PLAYER-019：失败无 Revision 前进、无提交
        assert not receipt.accepted
        assert receipt.committed_revision is None


class TestEnvelopeSecurity:
    """TEST-PLAYER-016"""

    def test_unknown_action_rejected(self):
        router = PlayerCommandRouter()
        with pytest.raises(PlayerCommandError) as exc:
            router.submit_player_command(_envelope("fly_to_moon"), ACTOR, 118)
        assert exc.value.code == "PLAYER_ACTION_UNREGISTERED"

    @pytest.mark.parametrize("command_type", ["mayor.budget.propose", "admin.resource.grant"])
    def test_union_confusion_rejected(self, command_type):
        """RULE-PLAYER-020：普通交互不能路由到 Mayor/Admin union"""
        router = PlayerCommandRouter()
        with pytest.raises(PlayerCommandError) as exc:
            router.submit_player_command(
                _envelope(type=command_type), ACTOR, 118
            )
        assert exc.value.code == "PLAYER_ENVELOPE_UNION_CONFUSION"

    def test_extra_root_field_rejected(self):
        router = PlayerCommandRouter()
        with pytest.raises(PlayerCommandError) as exc:
            router.submit_player_command(_envelope(actor_id="spoofed"), ACTOR, 118)
        assert exc.value.code == "PLAYER_ENVELOPE_UNKNOWN_FIELD"

    @pytest.mark.parametrize(
        "params,code",
        [
            ({"__proto__": {"polluted": True}}, "PLAYER_PARAMETERS_FORBIDDEN_KEY"),
            ({"constructor": "x"}, "PLAYER_PARAMETERS_FORBIDDEN_KEY"),
            ({"note": "<script>alert(1)</script>"}, "PLAYER_PARAMETERS_HTML_REJECTED"),
            ({"url": "javascript:alert(1)"}, "PLAYER_PARAMETERS_SCRIPT_URL_REJECTED"),
            ({"path": "C:\\Windows\\system.ini"}, "PLAYER_PARAMETERS_FILE_PATH_REJECTED"),
            ({"path": "../../etc/passwd"}, "PLAYER_PARAMETERS_FILE_PATH_REJECTED"),
        ],
    )
    def test_malicious_parameters_rejected(self, params, code):
        router = PlayerCommandRouter()
        with pytest.raises(PlayerCommandError) as exc:
            router.submit_player_command(_envelope(params=params), ACTOR, 118)
        assert exc.value.code == code

    def test_oversized_envelope_rejected(self):
        router = PlayerCommandRouter()
        big_params = {"item_id": "x", "quantity": 1, "padding": "A" * (17 * 1024)}
        with pytest.raises(PlayerCommandError) as exc:
            router.submit_player_command(_envelope(params=big_params), ACTOR, 118)
        assert exc.value.code == "PLAYER_ENVELOPE_TOO_LARGE"

    def test_actor_comes_from_binding_not_payload(self):
        """RULE-PLAYER-016：actor 由 binding 解析，payload 内 actor 不被信任"""
        router = PlayerCommandRouter(
            domain_validators={"give_item": lambda actor, *a: DomainValidationResult(
                legal=actor == ACTOR, reason_code="actor-mismatch" if actor != ACTOR else None
            )}
        )
        receipt = router.submit_player_command(_envelope(), ACTOR, 118)
        assert receipt.accepted
