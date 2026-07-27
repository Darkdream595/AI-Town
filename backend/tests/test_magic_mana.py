"""
TEST-MAGIC-005..006：Mana 与恢复（DOC-MAGIC-003）

- TEST-MAGIC-005：tide 合成夹取与 regen 公式 Table Test
- TEST-MAGIC-006：枯竭状态机、消耗/恢复幂等、catch-up 聚合一致性
"""

import pytest

from src.magic import (
    ActivityKind,
    CasterRegistry,
    ManaError,
    compose_tide_q1000,
    mana_max_for,
    regen_increment,
)


def test_magic_005_tide_composition_table():
    # RULE-MAGIC-011：缺失按 1000 降级；合成后夹取 500..1500
    assert compose_tide_q1000(None) == (1000, True)
    assert compose_tide_q1000(1000) == (1000, False)
    assert compose_tide_q1000(100) == (500, False)
    assert compose_tide_q1000(5000) == (1500, False)
    # ley 锚点加成参与合成后再夹取（不叠加，单锚点 +100）
    assert compose_tide_q1000(1450, 100) == (1500, False)
    assert compose_tide_q1000(450, 100) == (550, False)


def test_magic_005_regen_formula_table():
    # RULE-MAGIC-010：floor(3 × tide/1000 × mult)，休息 2、常规 1、Encounter 0
    cases = [
        (500, ActivityKind.RESTING, 3),
        (500, ActivityKind.NORMAL, 1),
        (500, ActivityKind.ENCOUNTER, 0),
        (1000, ActivityKind.RESTING, 6),
        (1000, ActivityKind.NORMAL, 3),
        (1000, ActivityKind.ENCOUNTER, 0),
        (1500, ActivityKind.RESTING, 9),
        (1500, ActivityKind.NORMAL, 4),
        (1500, ActivityKind.ENCOUNTER, 0),
    ]
    for tide, activity, expected in cases:
        assert regen_increment(tide, activity) == expected, (tide, activity)
    # REQ-MAGIC-023：增量包络上限 9
    assert regen_increment(1500, ActivityKind.RESTING) <= 9


def test_magic_005_mana_max_bounds():
    assert mana_max_for(0) == 60
    assert mana_max_for(50) == 110
    assert mana_max_for(100) == 160
    for invalid in (-1, 101):
        with pytest.raises(ManaError) as exc:
            mana_max_for(invalid)
        assert exc.value.code == "magic_skill_rating_invalid"


def test_magic_006_exhaustion_state_machine():
    registry = CasterRegistry()
    registry.register_caster("r.a", 0)  # mana 60/60
    state = registry.get("r.a")
    # 消耗到 12：未枯竭
    registry.consume_mana("evt.1", "r.a", 48, state.state_revision)
    assert state.mana_current == 12 and not state.mana_exhausted
    # 消耗到 9：<10 进入枯竭
    registry.consume_mana("evt.2", "r.a", 3, state.state_revision)
    assert state.mana_current == 9 and state.mana_exhausted
    # 枯竭中恢复：10..29 保持枯竭（迟滞区间无抖动）
    registry.settle_mana_regeneration(
        "occ.1", ["r.a"], {"r.a": ActivityKind.RESTING}, starweave_q1000=1500
    )
    assert state.mana_current == 18 and state.mana_exhausted
    # 恢复到 >=30 解除枯竭
    registry.settle_mana_regeneration(
        "occ.2", ["r.a"], {"r.a": ActivityKind.RESTING}, starweave_q1000=1500
    )
    registry.settle_mana_regeneration(
        "occ.3", ["r.a"], {"r.a": ActivityKind.RESTING}, starweave_q1000=1500
    )
    assert state.mana_current == 36 and not state.mana_exhausted


def test_magic_006_exhausted_cast_rejected():
    registry = CasterRegistry()
    registry.register_caster("r.a", 0)
    state = registry.get("r.a")
    registry.consume_mana("evt.1", "r.a", 55, state.state_revision)
    assert state.mana_exhausted
    with pytest.raises(ManaError) as exc:
        registry.check_castable("r.a", 5)
    assert exc.value.code == "MAGIC_CASTER_EXHAUSTED"
    with pytest.raises(ManaError) as exc2:
        registry.consume_mana("evt.2", "r.a", 5, state.state_revision)
    assert exc2.value.code == "MAGIC_CASTER_EXHAUSTED"


def test_magic_006_consume_idempotent_and_stale_revision():
    registry = CasterRegistry()
    registry.register_caster("r.a", 0)
    state = registry.get("r.a")
    # RULE-MAGIC-013：同 (caster, source_event) 最多扣一次
    registry.consume_mana("evt.x", "r.a", 20, state.state_revision)
    registry.consume_mana("evt.x", "r.a", 20, state.state_revision + 999)
    assert state.mana_current == 40
    # revision 不匹配按 stale_revision 拒绝
    with pytest.raises(ManaError) as exc:
        registry.consume_mana("evt.y", "r.a", 5, state.state_revision + 1)
    assert exc.value.code == "stale_revision"
    # Mana 不可交易/转移：只有消耗与周期恢复两个变化源
    with pytest.raises(ManaError) as exc2:
        registry.consume_mana("evt.z", "r.a", 0, state.state_revision)
    assert exc2.value.code == "MAGIC_MANA_INSUFFICIENT"


def test_magic_006_regen_occurrence_idempotent_and_catchup():
    registry = CasterRegistry()
    registry.register_caster("r.a", 0)
    state = registry.get("r.a")
    registry.consume_mana("evt.1", "r.a", 30, state.state_revision)
    # 同 occurrence_key 重复结算只生效一次
    first = registry.settle_mana_regeneration(
        "occ.daily.1", ["r.a"], {"r.a": ActivityKind.NORMAL}, starweave_q1000=1000
    )
    after_first = state.mana_current
    second = registry.settle_mana_regeneration(
        "occ.daily.1", ["r.a"], {"r.a": ActivityKind.NORMAL}, starweave_q1000=1000
    )
    assert first == second
    assert state.mana_current == after_first == 33

    # catch-up 聚合 == 逐次结算：离线 3 个 occurrence 一并调用
    registry2 = CasterRegistry()
    registry2.register_caster("r.a", 0)
    state2 = registry2.get("r.a")
    registry2.consume_mana("evt.1", "r.a", 30, state2.state_revision)
    for occurrence in ("occ.daily.1", "occ.daily.2", "occ.daily.3"):
        registry.settle_mana_regeneration(
            occurrence, ["r.a"], {"r.a": ActivityKind.NORMAL}, starweave_q1000=1000
        )
        registry2.settle_mana_regeneration(
            occurrence, ["r.a"], {"r.a": ActivityKind.NORMAL}, starweave_q1000=1000
        )
    assert state.mana_current == state2.mana_current == 39


def test_magic_006_regen_batch_cap_and_skip():
    registry = CasterRegistry()
    for index in range(70):
        registry.register_caster(f"r.{index}", 0)
    result = registry.settle_mana_regeneration(
        "occ.cap", [f"r.{index}" for index in range(70)] + ["r.ghost"],
        {"r.ghost": ActivityKind.NORMAL}, starweave_q1000=1000,
    )
    # REGEN_BATCH_CAP=64：超出顺延，未注册 caster 被跳过不阻塞批次
    assert len(result.settled) == 64
    assert result.skipped == ()
    assert not result.degraded_tide
    # 缺失 tide 按降级结算并标记
    degraded = registry.settle_mana_regeneration("occ.deg", ["r.0"], {})
    assert degraded.degraded_tide


def test_magic_006_skill_growth_does_not_refill():
    registry = CasterRegistry()
    registry.register_caster("r.a", 0)
    state = registry.get("r.a")
    registry.consume_mana("evt.1", "r.a", 30, state.state_revision)
    registry.update_skill_rating("r.a", 50)
    assert state.mana_max == 110
    assert state.mana_current == 30  # 上限增长不自动补满
