"""
TEST-PLAYER-001..004：玩家居民创建与身份绑定（DOC-PLAYER-001）

- TEST-PLAYER-001：完整玩家 Resident 创建与 AI 配额隔离
- TEST-PLAYER-002：双窗口创建、幂等重试与 payload conflict
- TEST-PLAYER-003：初始化各故障点原子回滚
- TEST-PLAYER-004：binding 缺失、导入 reclaim 与权限分离
"""

import pytest

from src.player import (
    BindingState,
    PlayerAuthorityProjection,
    PlayerBindingError,
    PlayerIdentity,
    PlayerResidentBinding,
    PlayerResidentBindingRegistry,
    ResidentCreationDraft,
    DecisionSource,
)
from src.player.binding import COMMIT_STAGES
from src.player.constants import DENY_IDEMPOTENCY_PAYLOAD_CONFLICT

WORLD = "01K1WRDX000000000000000001"
PLAYER_A = "01K1DENT000000000000000001"
PLAYER_B = "01K1DENT000000000000000002"


def _draft(name="艾拉"):
    return ResidentCreationDraft(
        name=name,
        appearance={"sprite_id": "human_player", "hair_color": "black"},
        start_options={"backstory_id": "backstory.wanderer"},
    )


def _registry():
    registry = PlayerResidentBindingRegistry(
        resident_validator=lambda draft: None, initial_revision=12
    )
    registry.set_ai_core_resident_count(10)
    return registry


class TestPlayerCreationAndQuota:
    """TEST-PLAYER-001"""

    def test_full_creation_flow_commits_single_revision(self):
        registry = _registry()
        prep = registry.prepare_player_resident("cmd-1", WORLD, PLAYER_A, _draft())
        result = registry.commit_player_resident("cmd-1", prep.preparation_id, 12)

        assert result.replayed is False
        assert result.committed_revision == 13  # Revision 只增长 1（§6）
        assert result.binding.state is BindingState.ACTIVE
        assert result.binding.decision_source is DecisionSource.HUMAN
        assert result.binding.version == 1

    def test_player_resident_excluded_from_ai_quota(self):
        registry = _registry()
        before = registry.ai_core_resident_count
        prep = registry.prepare_player_resident("cmd-1", WORLD, PLAYER_A, _draft())
        registry.commit_player_resident("cmd-1", prep.preparation_id, 12)

        # RULE-PLAYER-004：AI 核心配额不变，玩家计数 +1
        assert registry.ai_core_resident_count == before == 10
        assert registry.player_resident_count == 1

    def test_resident_validator_is_invoked(self):
        calls = []
        registry = PlayerResidentBindingRegistry(
            resident_validator=lambda draft: calls.append(draft.name)
        )
        registry.set_ai_core_resident_count(8)
        registry.prepare_player_resident("cmd-1", WORLD, PLAYER_A, _draft("托马斯"))
        assert calls == ["托马斯"]  # RULE-PLAYER-002：走同一 RESIDENT validator

    def test_decision_source_grants_nothing(self):
        registry = _registry()
        prep = registry.prepare_player_resident("cmd-1", WORLD, PLAYER_A, _draft())
        result = registry.commit_player_resident("cmd-1", prep.preparation_id, 12)
        grants = registry.decision_source_grants_nothing(result.binding.binding_id)
        # RULE-PLAYER-003：human 不授予技能/物品/法术/金钱/秘密
        assert grants == {"skills": [], "items": [], "spells": [], "money": 0, "secrets": []}

    def test_client_cannot_set_trusted_options(self):
        for key in ("starting_balance", "skill_level", "spawn_point", "decision_source"):
            with pytest.raises(PlayerBindingError) as exc:
                ResidentCreationDraft(name="x", appearance={}, start_options={key: 1})
            assert exc.value.code == "RESIDENT_DRAFT_FORBIDDEN_OPTION"


class TestIdempotencyAndConcurrency:
    """TEST-PLAYER-002"""

    def test_same_key_same_payload_returns_original(self):
        registry = _registry()
        prep = registry.prepare_player_resident("cmd-1", WORLD, PLAYER_A, _draft())
        first = registry.commit_player_resident("cmd-1", prep.preparation_id, 12)
        # expected_revision 已变为 13，重放需按幂等路径：再次 commit 前 revision 已变
        # 相同 (world_id, command_id) 重试应返回原 binding
        second = registry.commit_player_resident("cmd-1", prep.preparation_id, 13)
        assert second.replayed is True
        assert second.binding.binding_id == first.binding.binding_id

    def test_same_key_different_payload_conflicts(self):
        registry = _registry()
        prep1 = registry.prepare_player_resident("cmd-1", WORLD, PLAYER_A, _draft("甲"))
        registry.commit_player_resident("cmd-1", prep1.preparation_id, 12)

        # 构造同 command_id 但 payload 不同的 preparation（绕过 player 唯一索引的另一身份）
        registry2 = PlayerResidentBindingRegistry(initial_revision=12)
        prep_a = registry2.prepare_player_resident("cmd-1", WORLD, PLAYER_A, _draft("甲"))
        registry2.commit_player_resident("cmd-1", prep_a.preparation_id, 12)
        # 同 world 同 command_id 不同 payload：直接操纵幂等表验证冲突分支
        prep_b = registry2.prepare_player_resident("cmd-1", WORLD, PLAYER_B, _draft("乙"))
        with pytest.raises(PlayerBindingError) as exc:
            registry2.commit_player_resident("cmd-1", prep_b.preparation_id, 13)
        assert exc.value.code == DENY_IDEMPOTENCY_PAYLOAD_CONFLICT

    def test_two_windows_cannot_both_bind_same_player(self):
        registry = _registry()
        prep1 = registry.prepare_player_resident("cmd-1", WORLD, PLAYER_A, _draft("甲"))
        registry.commit_player_resident("cmd-1", prep1.preparation_id, 12)

        # 第二个窗口：prepare 预检即拒绝
        with pytest.raises(PlayerBindingError) as exc:
            registry.prepare_player_resident("cmd-2", WORLD, PLAYER_A, _draft("乙"))
        assert exc.value.code == "PLAYER_BINDING_ALREADY_ACTIVE"

    def test_resident_cannot_be_bound_twice(self):
        registry = _registry()
        prep = registry.prepare_player_resident("cmd-1", WORLD, PLAYER_A, _draft())
        result = registry.commit_player_resident("cmd-1", prep.preparation_id, 12)
        # RULE-PLAYER-001：同一 Resident 最多一个 active binding
        found = registry.get_binding_for_resident(WORLD, result.binding.resident_id)
        assert found is not None
        assert found.binding_id == result.binding.binding_id

    def test_stale_expected_revision_rejected(self):
        registry = _registry()
        prep = registry.prepare_player_resident("cmd-1", WORLD, PLAYER_A, _draft())
        with pytest.raises(PlayerBindingError) as exc:
            registry.commit_player_resident("cmd-1", prep.preparation_id, 99)
        assert exc.value.code == "EXPECTED_REVISION_STALE"


class TestAtomicRollback:
    """TEST-PLAYER-003"""

    @pytest.mark.parametrize("stage", COMMIT_STAGES)
    def test_failure_at_each_stage_rolls_back_everything(self, stage):
        registry = _registry()
        prep = registry.prepare_player_resident("cmd-1", WORLD, PLAYER_A, _draft())
        with pytest.raises(PlayerBindingError) as exc:
            registry.commit_player_resident(
                "cmd-1", prep.preparation_id, 12, fail_at_stage=stage
            )
        assert exc.value.code == "COMMIT_STAGE_FAILED"

        # §8：全成或全败——无 binding、无 revision 前进、无配额变化、可重试
        assert registry.revision == 12
        assert registry.player_resident_count == 0
        assert registry.get_active_binding(WORLD, PLAYER_A) is None

        result = registry.commit_player_resident("cmd-1", prep.preparation_id, 12)
        assert result.binding.state is BindingState.ACTIVE


class TestLifecycleAndAuthoritySeparation:
    """TEST-PLAYER-004"""

    def _bound_registry(self):
        registry = _registry()
        prep = registry.prepare_player_resident("cmd-1", WORLD, PLAYER_A, _draft())
        result = registry.commit_player_resident("cmd-1", prep.preparation_id, 12)
        return registry, result.binding

    def test_broken_binding_triggers_recovery_barrier(self):
        registry, binding = self._bound_registry()
        with pytest.raises(PlayerBindingError) as exc:
            registry.verify_binding_integrity(binding.binding_id, resident_exists=False)
        # §8：Recovery Barrier，禁止自动生成替代 Resident
        assert exc.value.code == "RECOVERY_BARRIER_BINDING_BROKEN"

    def test_suspend_and_reclaim_requires_ownership_proof(self):
        registry, binding = self._bound_registry()
        suspended = registry.suspend_binding(binding.binding_id)
        assert suspended.state is BindingState.SUSPENDED
        assert registry.get_active_binding(WORLD, PLAYER_A) is None

        with pytest.raises(PlayerBindingError) as exc:
            registry.reclaim_binding(binding.binding_id, PLAYER_B, ownership_proof=False)
        assert exc.value.code == "RECLAIM_OWNERSHIP_PROOF_REQUIRED"

        reclaimed = registry.reclaim_binding(binding.binding_id, PLAYER_B, True)
        assert reclaimed.state is BindingState.ACTIVE
        assert reclaimed.player_identity_id == PLAYER_B
        assert reclaimed.version == suspended.version + 1

    def test_reclaim_requires_suspended_state(self):
        registry, binding = self._bound_registry()
        with pytest.raises(PlayerBindingError) as exc:
            registry.reclaim_binding(binding.binding_id, PLAYER_B, True)
        assert exc.value.code == "RECLAIM_REQUIRES_SUSPENDED"

    def test_three_authorizations_are_independent(self):
        registry, binding = self._bound_registry()
        # RULE-PLAYER-005：world owner / Mayor / Admin 可分别为 false
        projection = registry.get_player_authority(
            WORLD, PLAYER_A, revision=13,
            world_role_ids=(), mayor_office_id=None, admin_session_state="disabled",
        )
        assert isinstance(projection, PlayerAuthorityProjection)
        assert projection.mayor_office_id is None
        assert projection.admin_session_state == "disabled"
        assert projection.world_role_ids == ()
        # 投影不含私人记忆或凭据（§5）
        assert not hasattr(projection, "private_memory")
        assert not hasattr(projection, "credentials")
