"""
TEST-DIALOGUE-003/004/027：距离、视线、语言与宽限/Reservation（DOC-DIALOGUE-002）

- TEST-DIALOGUE-003：RULE-DIALOGUE-007/008 距离边界（95/96/97 + epsilon）与 LoS fail closed
- TEST-DIALOGUE-004：RULE-DIALOGUE-076 共通语言阈值 59/60/61 与选定确定性
- TEST-DIALOGUE-027：RULE-DIALOGUE-011 宽限期与 RULE-DIALOGUE-010 Reservation 泄漏检查
"""

import pytest

from src.dialogue.conditions import (
    EntitySnapshot,
    GraceTracker,
    ParticipationError,
    ParticipationValidator,
    ReservationLedger,
    ReservationState,
)
from src.dialogue.constants import (
    DISTANCE_EPSILON_WU,
    GRACE_PERIOD_GAME_MINUTES,
    PLAYER_LANGUAGE_ID,
    TALK_RANGE_WU,
)

from ai_helpers import ULID_A, ULID_B

SCENE = "region.crown_creek_town"
LANG_A = "language.crown_common"
LANG_B = "language.dusk_tongue"
LANG_C = "language.old_speech"


def _snap(
    entity_id: str,
    x: int,
    y: int,
    languages=None,
    available: bool = True,
    is_player: bool = False,
    scene: str = SCENE,
) -> EntitySnapshot:
    return EntitySnapshot(
        entity_id=entity_id,
        scene_id=scene,
        x_wu=x,
        y_wu=y,
        available=available,
        language_proficiencies=languages if languages is not None else {LANG_A: 100},
        is_player=is_player,
    )


class TestDistanceAndLineOfSight:
    """TEST-DIALOGUE-003"""

    def test_distance_boundary_95_96_accepted(self):
        validator = ParticipationValidator()
        for distance in (95, 96):
            language = validator.check_initiation(_snap(ULID_A, 0, 0), _snap(ULID_B, distance, 0))
            assert language == LANG_A

    def test_distance_97_rejected(self):
        validator = ParticipationValidator()
        with pytest.raises(ParticipationError) as excinfo:
            validator.check_initiation(_snap(ULID_A, 0, 0), _snap(ULID_B, 97, 0))
        assert excinfo.value.code == "DIALOGUE_OUT_OF_RANGE"

    def test_distance_epsilon_edge(self):
        validator = ParticipationValidator()
        # sqrt(96²+3²) ≈ 96.047 ≤ 96+1/16 → 接受
        assert validator.check_initiation(_snap(ULID_A, 0, 0), _snap(ULID_B, 96, 3)) == LANG_A
        # sqrt(96²+4²) ≈ 96.083 > 96+1/16 → 拒绝
        with pytest.raises(ParticipationError) as excinfo:
            validator.check_initiation(_snap(ULID_A, 0, 0), _snap(ULID_B, 96, 4))
        assert excinfo.value.code == "DIALOGUE_OUT_OF_RANGE"
        assert DISTANCE_EPSILON_WU == 1.0 / 16.0
        assert TALK_RANGE_WU == 96.0

    def test_different_scene_rejected(self):
        validator = ParticipationValidator()
        with pytest.raises(ParticipationError) as excinfo:
            validator.check_initiation(
                _snap(ULID_A, 0, 0), _snap(ULID_B, 10, 0, scene="region.duskwood")
            )
        assert excinfo.value.code == "DIALOGUE_NOT_SAME_SCENE"

    def test_line_of_sight_required(self):
        validator = ParticipationValidator(los_query=lambda a, b, scene: False)
        with pytest.raises(ParticipationError) as excinfo:
            validator.check_initiation(_snap(ULID_A, 0, 0), _snap(ULID_B, 10, 0))
        assert excinfo.value.code == "DIALOGUE_NO_LINE_OF_SIGHT"

    def test_line_of_sight_query_failure_fails_closed(self):
        def _broken(a, b, scene):
            raise RuntimeError("MAP unavailable")

        validator = ParticipationValidator(los_query=_broken)
        with pytest.raises(ParticipationError) as excinfo:
            validator.check_initiation(_snap(ULID_A, 0, 0), _snap(ULID_B, 10, 0))
        assert excinfo.value.code == "DIALOGUE_NO_LINE_OF_SIGHT"

    def test_target_unavailable_rejected(self):
        validator = ParticipationValidator()
        with pytest.raises(ParticipationError) as excinfo:
            validator.check_initiation(_snap(ULID_A, 0, 0), _snap(ULID_B, 10, 0, available=False))
        assert excinfo.value.code == "DIALOGUE_TARGET_UNAVAILABLE"


class TestSharedLanguage:
    """TEST-DIALOGUE-004"""

    def test_threshold_matrix_59_60_61(self):
        # 59 低于阈值 → 无共通语言
        with pytest.raises(ParticipationError) as excinfo:
            ParticipationValidator.select_shared_language(
                _snap(ULID_A, 0, 0, {LANG_A: 59}), _snap(ULID_B, 1, 0, {LANG_A: 100})
            )
        assert excinfo.value.code == "no_shared_language"
        # 60 恰好达标 → 通过；61 亦通过
        for level in (60, 61):
            language = ParticipationValidator.select_shared_language(
                _snap(ULID_A, 0, 0, {LANG_A: level}), _snap(ULID_B, 1, 0, {LANG_A: 60})
            )
            assert language == LANG_A

    def test_player_counts_as_crown_common_100(self):
        player = _snap(ULID_A, 0, 0, {}, is_player=True)
        resident_ok = _snap(ULID_B, 1, 0, {LANG_A: 60})
        assert ParticipationValidator.select_shared_language(player, resident_ok) == PLAYER_LANGUAGE_ID

        resident_weak = _snap(ULID_B, 1, 0, {LANG_A: 59})
        with pytest.raises(ParticipationError) as excinfo:
            ParticipationValidator.select_shared_language(player, resident_weak)
        assert excinfo.value.code == "no_shared_language"

    def test_highest_sum_wins(self):
        a = _snap(ULID_A, 0, 0, {LANG_A: 100, LANG_B: 60})
        b = _snap(ULID_B, 1, 0, {LANG_A: 61, LANG_B: 60})
        # LANG_A 之和 161 > LANG_B 之和 120
        assert ParticipationValidator.select_shared_language(a, b) == LANG_A

    def test_tie_breaks_by_language_id_lexicographic(self):
        a = _snap(ULID_A, 0, 0, {LANG_B: 90, LANG_C: 80})
        b = _snap(ULID_B, 1, 0, {LANG_B: 80, LANG_C: 90})
        # 两者之和均 170 → 字典序小者（dusk_tongue < old_speech）
        first = ParticipationValidator.select_shared_language(a, b)
        second = ParticipationValidator.select_shared_language(b, a)
        assert first == LANG_B
        assert second == LANG_B  # 选定与调用顺序无关（确定性）


class TestGracePeriodAndReservation:
    """TEST-DIALOGUE-027"""

    def test_grace_period_full_cycle(self):
        tracker = GraceTracker()
        assert tracker.on_tick("c1", in_range=False, current_game_time=100) is False
        assert tracker.in_grace("c1")
        assert tracker.on_tick("c1", in_range=False, current_game_time=109) is False
        # 第 10 游戏分钟宽限届满
        assert tracker.on_tick("c1", in_range=False, current_game_time=110) is True
        assert GRACE_PERIOD_GAME_MINUTES == 10

    def test_returning_in_range_clears_grace(self):
        tracker = GraceTracker()
        tracker.on_tick("c1", in_range=False, current_game_time=100)
        assert tracker.on_tick("c1", in_range=True, current_game_time=105) is False
        assert not tracker.in_grace("c1")
        # 再次超距重新计窗
        tracker.on_tick("c1", in_range=False, current_game_time=106)
        assert tracker.on_tick("c1", in_range=False, current_game_time=115) is False
        assert tracker.on_tick("c1", in_range=False, current_game_time=116) is True

    def test_custom_grace_period(self):
        tracker = GraceTracker(grace_period_game_minutes=3)
        tracker.on_tick("c1", in_range=False, current_game_time=10)
        assert tracker.on_tick("c1", in_range=False, current_game_time=12) is False
        assert tracker.on_tick("c1", in_range=False, current_game_time=13) is True

    def test_reservation_release_leaves_no_leak(self):
        ledger = ReservationLedger()
        created = ledger.create("c1", [ULID_A, ULID_B], expires_game_time=200)
        assert len(created) == 2
        assert ledger.has_leak()
        ledger.release_for_conversation("c1")
        assert not ledger.has_leak()
        assert ledger.granted_for("c1") == []
        assert all(r.state is ReservationState.RELEASED for r in created)

    def test_reservation_preempt_and_expire(self):
        ledger = ReservationLedger()
        [reservation] = ledger.create("c1", [ULID_A], expires_game_time=200)
        ledger.preempt(reservation.reservation_id)
        assert reservation.state is ReservationState.PREEMPTED
        assert not ledger.has_leak()

        ledger.create("c2", [ULID_B], expires_game_time=200)
        assert ledger.expire_overdue(200) == []  # 到期时刻本身不失效
        assert ledger.expire_overdue(201) == ["c2"]
        assert not ledger.has_leak()
