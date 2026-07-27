"""
TEST-PLAYER-009..012：居民与镇长模式切换状态机（DOC-PLAYER-003）

- TEST-PLAYER-009：mode transition table 与双 Tab 幂等
- TEST-PLAYER-010：Mayor/Dialogue/Combat/Shutdown token 嵌套
- TEST-PLAYER-011：prohibited states 与 authority revocation
- TEST-PLAYER-012：middle-state crash、orphan token 与 focus recovery
"""

import pytest

from src.player import (
    ModeSwitchError,
    ModeSwitchStateMachine,
    PauseTokenLedger,
    PlayerMode,
    ProhibitedCondition,
)
from src.player.constants import (
    DENY_MAYOR_AUTHORITY_REVOKED,
    DENY_MODE_BLOCKED_COMBAT,
    DENY_MODE_BLOCKED_RESIDENT_STATE,
    DENY_MODE_BLOCKED_SYSTEM,
)

WORLD = "01K1WRDX000000000000000001"
BINDING = "01K1BNDG000000000000000001"


def _make(has_office=True, authority_version=3, revision=92):
    ledger = PauseTokenLedger(world_id=WORLD)
    sm = ModeSwitchStateMachine(
        binding_id=BINDING,
        pause_ledger=ledger,
        authority_probe=lambda binding_id, rev: (has_office, authority_version),
        initial_revision=revision,
    )
    return sm, ledger


def _enter_mayor(sm, cmd="cmd-1", revision=92):
    sm.request_mode_switch(cmd, PlayerMode.ENTERING_MAYOR, revision, 0, current_game_revision=revision)
    sm.request_mode_switch(f"{cmd}-b", PlayerMode.MAYOR_ACTIVE, revision, 1, current_game_revision=revision)


class TestTransitionTableAndIdempotency:
    """TEST-PLAYER-009"""

    def test_full_cycle_follows_state_machine(self):
        sm, ledger = _make()
        assert sm.mode is PlayerMode.RESIDENT_ACTIVE

        r1 = sm.request_mode_switch("cmd-1", PlayerMode.ENTERING_MAYOR, 92, 0)
        assert r1.aggregate.mode is PlayerMode.ENTERING_MAYOR
        assert r1.pause_token is not None
        assert ledger.is_paused()

        r2 = sm.request_mode_switch("cmd-2", PlayerMode.MAYOR_ACTIVE, 92, 1)
        assert r2.aggregate.mode is PlayerMode.MAYOR_ACTIVE

        r3 = sm.request_mode_switch("cmd-3", PlayerMode.LEAVING_MAYOR, 92, 2)
        assert r3.aggregate.mode is PlayerMode.LEAVING_MAYOR

        r4 = sm.request_mode_switch("cmd-4", PlayerMode.RESIDENT_ACTIVE, 92, 3)
        assert r4.aggregate.mode is PlayerMode.RESIDENT_ACTIVE
        assert not ledger.is_paused()  # 自己的 token 已释放

    def test_illegal_transition_rejected(self):
        sm, _ = _make()
        with pytest.raises(ModeSwitchError) as exc:
            sm.request_mode_switch("cmd-1", PlayerMode.MAYOR_ACTIVE, 92, 0)
        assert exc.value.code == "PLAYER_MODE_TRANSITION_INVALID"

    def test_double_tab_cannot_skip_intermediate_state(self):
        sm, _ = _make()
        sm.request_mode_switch("cmd-1", PlayerMode.ENTERING_MAYOR, 92, 0)
        # 双击 Tab：第二次同样请求 ENTERING_MAYOR 是非法转换（不能越过中间态）
        with pytest.raises(ModeSwitchError) as exc:
            sm.request_mode_switch("cmd-2", PlayerMode.ENTERING_MAYOR, 92, 1)
        assert exc.value.code == "PLAYER_MODE_TRANSITION_INVALID"

    def test_same_command_replay_returns_original(self):
        sm, _ = _make()
        first = sm.request_mode_switch("cmd-1", PlayerMode.ENTERING_MAYOR, 92, 0)
        replay = sm.request_mode_switch("cmd-1", PlayerMode.ENTERING_MAYOR, 92, 0)
        assert replay.replayed is True
        assert replay.aggregate.mode_version == first.aggregate.mode_version

    def test_same_command_different_payload_conflicts(self):
        sm, _ = _make()
        sm.request_mode_switch("cmd-1", PlayerMode.ENTERING_MAYOR, 92, 0)
        with pytest.raises(ModeSwitchError) as exc:
            sm.request_mode_switch("cmd-1", PlayerMode.ENTERING_MAYOR, 93, 0)
        assert exc.value.code == "PLAYER_MODE_COMMAND_CONFLICT"

    def test_stale_mode_version_rejected(self):
        sm, _ = _make()
        with pytest.raises(ModeSwitchError) as exc:
            sm.request_mode_switch("cmd-1", PlayerMode.ENTERING_MAYOR, 92, 7)
        assert exc.value.code == "PLAYER_MODE_VERSION_STALE"

    def test_failed_leave_returns_to_mayor_active(self):
        """mermaid：leaving_mayor -> mayor_active（close failed before release）"""
        sm, ledger = _make()
        _enter_mayor(sm)
        sm.request_mode_switch("cmd-3", PlayerMode.LEAVING_MAYOR, 92, 2)
        r = sm.request_mode_switch("cmd-4", PlayerMode.MAYOR_ACTIVE, 92, 3)
        assert r.aggregate.mode is PlayerMode.MAYOR_ACTIVE
        assert ledger.is_paused()


class TestPauseTokenNesting:
    """TEST-PLAYER-010"""

    def test_mayor_token_composes_with_other_owners(self):
        sm, ledger = _make()
        # Dialogue / Combat token 先存在
        dialogue = ledger.acquire("cmd-d", owner="dialogue", reason="dialogue_input", revision=92)
        combat = ledger.acquire("cmd-c", owner="combat", reason="encounter", revision=92)
        _enter_mayor(sm)
        assert len(ledger.active_tokens()) == 3

        # 离开 Mayor 只释放自己的 token（RULE-PLAYER-013）
        sm.request_mode_switch("cmd-3", PlayerMode.LEAVING_MAYOR, 92, 2)
        sm.request_mode_switch("cmd-4", PlayerMode.RESIDENT_ACTIVE, 92, 3)
        remaining = {t.token_id for t in ledger.active_tokens()}
        assert remaining == {dialogue.token_id, combat.token_id}
        assert ledger.is_paused()  # 世界仍被其他 owner 暂停

    def test_player_cannot_release_other_owners_token(self):
        _, ledger = _make()
        dialogue = ledger.acquire("cmd-d", owner="dialogue", reason="dialogue_input", revision=92)
        from src.player import PauseTokenError

        with pytest.raises(PauseTokenError) as exc:
            ledger.release("cmd-x", dialogue.token_id, owner="player")
        assert exc.value.code == "PAUSE_TOKEN_OWNER_MISMATCH"

    def test_double_tab_produces_single_token(self):
        sm, ledger = _make()
        sm.request_mode_switch("cmd-1", PlayerMode.ENTERING_MAYOR, 92, 0)
        replay = sm.request_mode_switch("cmd-1", PlayerMode.ENTERING_MAYOR, 92, 0)
        assert replay.replayed
        # §10 验收：双击/乱序 Tab 不产生两个 token
        assert len(ledger.tokens_by_owner("player")) == 1


class TestProhibitedTransitions:
    """TEST-PLAYER-011"""

    @pytest.mark.parametrize(
        "condition,code",
        [
            (ProhibitedCondition.ENCOUNTER_ACTIVE, DENY_MODE_BLOCKED_COMBAT),
            (ProhibitedCondition.INCAPACITATED_OR_CAPTURED, DENY_MODE_BLOCKED_RESIDENT_STATE),
            (ProhibitedCondition.RECOVERY_OR_SHUTDOWN_BARRIER, DENY_MODE_BLOCKED_SYSTEM),
            (ProhibitedCondition.SAVE_SWITCHING, DENY_MODE_BLOCKED_SYSTEM),
            (ProhibitedCondition.ADMIN_CONFIRMATION_ACTIVE, DENY_MODE_BLOCKED_SYSTEM),
            (ProhibitedCondition.DIALOGUE_INPUT_MODAL, DENY_MODE_BLOCKED_SYSTEM),
        ],
    )
    def test_prohibited_conditions_block_entry(self, condition, code):
        sm, _ = _make()
        with pytest.raises(ModeSwitchError) as exc:
            sm.request_mode_switch(
                "cmd-1", PlayerMode.ENTERING_MAYOR, 92, 0, prohibited={condition}
            )
        assert exc.value.code == code

    def test_authority_revocation_blocks_entry(self):
        sm, _ = _make(has_office=False)
        with pytest.raises(ModeSwitchError) as exc:
            sm.request_mode_switch("cmd-1", PlayerMode.ENTERING_MAYOR, 92, 0)
        assert exc.value.code == DENY_MAYOR_AUTHORITY_REVOKED

    def test_admin_confirmation_blocks_leave(self):
        sm, _ = _make()
        _enter_mayor(sm)
        with pytest.raises(ModeSwitchError) as exc:
            sm.request_mode_switch(
                "cmd-3", PlayerMode.LEAVING_MAYOR, 92, 2,
                prohibited={ProhibitedCondition.ADMIN_CONFIRMATION_ACTIVE},
            )
        assert exc.value.code == DENY_MODE_BLOCKED_SYSTEM

    def test_force_safe_close_after_revocation(self):
        """§7.1：Mayor authority revoked → 强制安全关闭回 Resident"""
        sm, ledger = _make()
        _enter_mayor(sm)
        result = sm.force_safe_close("cmd-force")
        assert result.aggregate.mode is PlayerMode.RESIDENT_ACTIVE
        assert not ledger.tokens_by_owner("player")

    def test_revoked_authority_blocks_governance_via_mode_gate(self):
        """RULE-PLAYER-036 联动：revoked 后不能提交治理命令（mode 不可达）"""
        sm, _ = _make(has_office=True)
        _enter_mayor(sm)
        sm.force_safe_close("cmd-force")
        with pytest.raises(ModeSwitchError):
            sm.request_mode_switch("cmd-9", PlayerMode.MAYOR_ACTIVE, 92, 3)


class TestCrashRecovery:
    """TEST-PLAYER-012"""

    def test_mayor_active_with_live_token_restores_mayor(self):
        recovered = ModeSwitchStateMachine.adjudicate_crash_recovery(
            PlayerMode.MAYOR_ACTIVE, token_alive=True, stable_provable=True
        )
        assert recovered is PlayerMode.MAYOR_ACTIVE

    def test_resident_active_with_orphan_token_recovers_resident(self):
        recovered = ModeSwitchStateMachine.adjudicate_crash_recovery(
            PlayerMode.RESIDENT_ACTIVE, token_alive=True, stable_provable=True
        )
        # §8：孤儿 Mayor token 由 Recovery Barrier 审计后释放；mode 回 resident
        assert recovered is PlayerMode.RESIDENT_ACTIVE

    @pytest.mark.parametrize("middle", [PlayerMode.ENTERING_MAYOR, PlayerMode.LEAVING_MAYOR])
    def test_middle_state_provable_selects_stable(self, middle):
        recovered = ModeSwitchStateMachine.adjudicate_crash_recovery(
            middle, token_alive=True, stable_provable=True
        )
        assert recovered is PlayerMode.MAYOR_ACTIVE
        recovered = ModeSwitchStateMachine.adjudicate_crash_recovery(
            middle, token_alive=False, stable_provable=True
        )
        assert recovered is PlayerMode.RESIDENT_ACTIVE

    def test_middle_state_unprovable_stays_paused(self):
        # §8：无法证明时保持暂停，不让世界在未确认状态下运行
        recovered = ModeSwitchStateMachine.adjudicate_crash_recovery(
            PlayerMode.ENTERING_MAYOR, token_alive=True, stable_provable=False
        )
        assert recovered is PlayerMode.MAYOR_ACTIVE

    def test_orphan_token_force_release_by_recovery(self):
        _, ledger = _make()
        orphan = ledger.acquire("cmd-1", owner="player", reason="mayor_management", revision=92)
        released = ledger.force_release_orphan(orphan.token_id)
        assert released is not None
        assert not ledger.is_paused()
