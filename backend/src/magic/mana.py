"""
Mana 与恢复（DOC-MAGIC-003）

- REQ-MAGIC-005：整数 Mana，0 <= current <= max = 60 + max(SchoolSkill)
- REQ-MAGIC-006：恢复经周期任务确定性结算，禁止逐 Tick 浮点累积
- RULE-MAGIC-010：regen = floor(base × tide_q1000/1000 × activity_mult)
- RULE-MAGIC-011：tide 合成并夹取 500..1500，缺失按 1000 降级
- RULE-MAGIC-012：枯竭 <10 进入、>=30 解除，无中间抖动
- RULE-MAGIC-013：消耗只在施法提交事务内，(caster, source_event) 幂等
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .constants import (
    ACTIVITY_MULT,
    EXHAUSTION_ENTER_THRESHOLD,
    EXHAUSTION_EXIT_THRESHOLD,
    MANA_BASE_REGEN,
    MANA_MAX_BASE,
    MANA_MAX_CAP,
    REGEN_BATCH_CAP,
    TIDE_Q1000_DEFAULT,
    TIDE_Q1000_MAX,
    TIDE_Q1000_MIN,
    ActivityKind,
)


class ManaError(Exception):
    """Mana 操作失败；code 复用 DES-MAGIC-005 reason 集"""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


def compose_tide_q1000(
    starweave_q1000: Optional[int],
    ley_anchor_bonus_q1000: int = 0,
) -> Tuple[int, bool]:
    """RULE-MAGIC-011：合成并夹取；返回 (tide_q1000, degraded)"""
    if starweave_q1000 is None:
        return TIDE_Q1000_DEFAULT, True
    tide = starweave_q1000 + ley_anchor_bonus_q1000
    return max(TIDE_Q1000_MIN, min(TIDE_Q1000_MAX, tide)), False


def mana_max_for(max_school_skill_rating: int) -> int:
    """REQ-MAGIC-005：mana_max = 60 + max rating，范围 60..160"""
    if max_school_skill_rating < 0 or max_school_skill_rating > 100:
        raise ManaError("magic_skill_rating_invalid", str(max_school_skill_rating))
    return min(MANA_MAX_CAP, MANA_MAX_BASE + max_school_skill_rating)


def regen_increment(tide_q1000: int, activity: ActivityKind) -> int:
    """RULE-MAGIC-010：floor(base × tide/1000 × mult)；Encounter 内为 0"""
    return (MANA_BASE_REGEN * tide_q1000 * ACTIVITY_MULT[activity]) // 1000


@dataclass
class CasterState:
    """DES-MAGIC-003 的运行时形态；MAGIC 是 Mana 唯一真值 owner"""

    caster_id: str
    mana_current: int
    mana_max: int
    mana_exhausted: bool = False
    cooldowns: Dict[str, int] = field(default_factory=dict)  # spell_id -> ready_at_game_time
    state_revision: int = 0
    caster_schema_version: int = 1

    def refresh_exhaustion(self) -> None:
        """RULE-MAGIC-012：阈值状态机只在状态变化点求值"""
        if not self.mana_exhausted and self.mana_current < EXHAUSTION_ENTER_THRESHOLD:
            self.mana_exhausted = True
        elif self.mana_exhausted and self.mana_current >= EXHAUSTION_EXIT_THRESHOLD:
            self.mana_exhausted = False


@dataclass(frozen=True)
class ManaRegenResult:
    occurrence_key: str
    settled: Tuple[str, ...]  # 成功结算的 caster_id
    skipped: Tuple[str, ...]  # 单 caster 失败跳过并记录诊断
    degraded_tide: bool


class CasterRegistry:
    """CasterState 聚合：注册、恢复结算与消耗幂等"""

    def __init__(self) -> None:
        self._casters: Dict[str, CasterState] = {}
        self._consume_idempotency: Dict[Tuple[str, str], int] = {}
        self._regen_idempotency: Dict[str, ManaRegenResult] = {}

    def register_caster(self, caster_id: str, max_school_skill_rating: int) -> CasterState:
        if caster_id in self._casters:
            raise ManaError("magic_caster_conflict", caster_id)
        mana_max = mana_max_for(max_school_skill_rating)
        # 新居民初始化：满 Mana、无冷却、无枯竭
        state = CasterState(caster_id=caster_id, mana_current=mana_max, mana_max=mana_max)
        self._casters[caster_id] = state
        return state

    def get(self, caster_id: str) -> CasterState:
        state = self._casters.get(caster_id)
        if state is None:
            raise ManaError("MAGIC_CASTER_UNKNOWN", caster_id)
        return state

    def update_skill_rating(self, caster_id: str, max_school_skill_rating: int) -> None:
        """mana_max 增长时 current 保持不变，不自动补满"""
        state = self.get(caster_id)
        state.mana_max = mana_max_for(max_school_skill_rating)
        if state.mana_current > state.mana_max:
            # SchoolSkill 无降级路径；出现即数据损坏
            raise ManaError("magic_mana_corrupt", caster_id)
        state.state_revision += 1

    # -- 周期恢复 --

    def settle_mana_regeneration(
        self,
        occurrence_key: str,
        caster_ids: List[str],
        activity_by_caster: Dict[str, ActivityKind],
        starweave_q1000: Optional[int] = None,
        ley_anchor_bonus_by_caster: Optional[Dict[str, int]] = None,
    ) -> ManaRegenResult:
        """REQ-MAGIC-006/RULE-TIME-048：occurrence 幂等；catch-up 逐 occurrence 调用"""
        if occurrence_key in self._regen_idempotency:
            return self._regen_idempotency[occurrence_key]
        settled: List[str] = []
        skipped: List[str] = []
        degraded_any = False
        for caster_id in caster_ids[:REGEN_BATCH_CAP]:
            try:
                state = self.get(caster_id)
                activity = activity_by_caster.get(caster_id, ActivityKind.NORMAL)
                bonus = (ley_anchor_bonus_by_caster or {}).get(caster_id, 0)
                tide, degraded = compose_tide_q1000(starweave_q1000, bonus)
                degraded_any = degraded_any or degraded
                increment = regen_increment(tide, activity)
                state.mana_current = min(state.mana_max, state.mana_current + increment)
                state.refresh_exhaustion()
                state.state_revision += 1
                settled.append(caster_id)
            except ManaError:
                # 单 caster 失败只跳过并记录，不阻塞批次
                skipped.append(caster_id)
        result = ManaRegenResult(
            occurrence_key=occurrence_key,
            settled=tuple(settled),
            skipped=tuple(skipped),
            degraded_tide=degraded_any,
        )
        self._regen_idempotency[occurrence_key] = result
        return result

    # -- 消耗 --

    def consume_mana(
        self,
        source_event_id: str,
        caster_id: str,
        amount: int,
        expected_state_revision: int,
    ) -> int:
        """RULE-MAGIC-013：与 SpellCastCommitted 同一事务；同事件最多扣一次"""
        idem_key = (caster_id, source_event_id)
        if idem_key in self._consume_idempotency:
            return self._consume_idempotency[idem_key]
        state = self.get(caster_id)
        if expected_state_revision != state.state_revision:
            raise ManaError(
                "stale_revision",
                f"expected {expected_state_revision}, at {state.state_revision}",
            )
        if state.mana_exhausted:
            raise ManaError("MAGIC_CASTER_EXHAUSTED", caster_id)
        if amount <= 0 or state.mana_current < amount:
            raise ManaError("MAGIC_MANA_INSUFFICIENT", caster_id)
        state.mana_current -= amount
        state.refresh_exhaustion()
        state.state_revision += 1
        self._consume_idempotency[idem_key] = amount
        return amount

    def check_castable(self, caster_id: str, mana_cost: int) -> None:
        """第 3 级前置：枯竭与 Mana 充足（不产生状态变化）"""
        state = self.get(caster_id)
        if state.mana_exhausted:
            raise ManaError("MAGIC_CASTER_EXHAUSTED", caster_id)
        if state.mana_current < mana_cost:
            raise ManaError("MAGIC_MANA_INSUFFICIENT", caster_id)

    def cooldown_ready(self, caster_id: str, spell_id: str, game_time: int) -> bool:
        state = self.get(caster_id)
        return game_time >= state.cooldowns.get(spell_id, 0)

    def set_cooldown(self, caster_id: str, spell_id: str, ready_at_game_time: int) -> None:
        state = self.get(caster_id)
        state.cooldowns[spell_id] = ready_at_game_time
