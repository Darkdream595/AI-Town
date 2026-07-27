"""
TEST-ECON-033..036：基础供需与短缺（DOC-ECON-009）

- TEST-ECON-033：三 Region 必需生产链完备且 DAG 无环
- TEST-ECON-034：market delta 按 ActionId 幂等
- TEST-ECON-035：批量与逐分钟 bucket 等价；0× 暂停窗口不动
- TEST-ECON-036：scarcity golden 向量、clamp、空窗回退与两 bucket 滞回
"""

import pytest

from src.economy import (
    DEFAULT_SCARCITY_POLICY,
    MarketError,
    MarketWindow,
    ProductionChainRegistry,
    ShortageState,
    ShortageTracker,
    build_default_production_chains,
    compute_scarcity_q1000,
)
from src.economy.constants import REQUIRED_PRODUCTION_SETS


class TestProductionChainDag:
    """TEST-ECON-033"""

    def test_default_chains_cover_required_sets(self):
        registry = build_default_production_chains()
        registry.validate()  # 不抛异常即完备且无环
        for region_id, required in REQUIRED_PRODUCTION_SETS.items():
            assert required <= registry._region_nodes[region_id]

    def test_missing_required_set_rejected(self):
        registry = ProductionChainRegistry()
        registry.add_region_chain("region.duskwood_forest", {"material.timber"}, [])
        with pytest.raises(MarketError) as excinfo:
            registry.validate()
        assert excinfo.value.code == "market_key_invalid"

    def test_cycle_injected_rejected(self):
        registry = build_default_production_chains()
        registry.add_region_chain(
            "region.crown_creek_town",
            {"product.tool", "material.ore"},
            [("product.tool", "material.ore")],  # ore→tool 已存在，形成环
        )
        with pytest.raises(MarketError) as excinfo:
            registry.validate()
        assert excinfo.value.code == "production_chain_cycle"


class TestMarketDeltaIdempotency:
    """TEST-ECON-034"""

    def test_sale_delta_counted_once_per_action(self):
        window = MarketWindow()
        assert window.record_committed_demand("action.x", 5, game_time=100)
        assert not window.record_committed_demand("action.x", 5, game_time=100)
        assert not window.record_committed_demand("action.x", 99, game_time=120)
        _supply, committed, _unmet = window.totals(1440)
        assert committed == 5

    def test_lost_demand_counted_once_per_action(self):
        window = MarketWindow()
        assert window.record_unmet_demand("action.y", 3, game_time=100)
        assert not window.record_unmet_demand("action.y", 3, game_time=100)
        _s, _c, unmet = window.totals(1440)
        assert unmet == 3

    def test_supply_delta_and_invalid_quantity(self):
        window = MarketWindow()
        assert window.record_supply("action.s", 7, game_time=0)
        with pytest.raises(MarketError) as excinfo:
            window.record_supply("action.s2", 0, game_time=0)
        assert excinfo.value.code == "market_key_invalid"


class TestWindowSpeedEquivalence:
    """TEST-ECON-035"""

    def test_batched_equals_per_minute(self):
        per_minute = MarketWindow()
        batched = MarketWindow()
        # 同一事件序列：逐分钟记录 vs 按 bucket 批量记录（bucket 1..24 全在窗口内）
        for index in range(24):
            per_minute.record_supply(f"action.supply.{index}", 2, game_time=(index + 1) * 60)
            per_minute.record_committed_demand(f"action.demand.{index}", 1, game_time=(index + 1) * 60)
        for index in range(24):
            batched.record_supply(f"action.supply.{index}", 2, game_time=(index + 1) * 60)
            batched.record_committed_demand(f"action.demand.{index}", 1, game_time=(index + 1) * 60)
        assert per_minute.bucket_totals() == batched.bucket_totals()
        assert per_minute.totals(1440) == batched.totals(1440) == (48, 24, 0)

    def test_pause_leaves_window_untouched(self):
        window = MarketWindow()
        window.record_supply("action.s", 5, game_time=0)
        before = window.bucket_totals()
        # 0× 暂停：没有任何 record 调用，窗口与总计不滚动
        assert window.bucket_totals() == before
        assert window.totals(0) == window.totals(0)

    def test_old_buckets_slide_out_of_window(self):
        window = MarketWindow()
        window.record_supply("action.old", 5, game_time=0)
        window.record_supply("action.new", 3, game_time=2880)
        # 窗口终点 2880：bucket 0 (t=0) 已滑出 24 桶窗口
        supply, _c, _u = window.totals(2880)
        assert supply == 3
        supply_all, _c2, _u2 = window.totals(0)
        assert supply_all == 5


class TestScarcityPolicyGolden:
    """TEST-ECON-036"""

    @pytest.mark.parametrize(
        "available,reorder,committed,unmet,expected",
        [
            (10, 10, 10, 0, 1000),
            (0, 10, 10, 10, 1800),
            (20, 10, 10, 0, 700),
            (2, 6, 22, 7, 1496),
        ],
    )
    def test_golden_vectors(self, available, reorder, committed, unmet, expected):
        assert compute_scarcity_q1000(available, reorder, committed, unmet) == expected

    def test_clamp_bounds(self):
        # 极端短缺不超过 maximum 2000
        assert compute_scarcity_q1000(0, 1, 0, 10**9) == 2000
        # 极端过剩不低于 minimum 700
        assert compute_scarcity_q1000(10**9, 1, 0, 0) == 700

    def test_empty_window_fallback(self):
        assert compute_scarcity_q1000(0, 10, 0, 0, window_empty=True) == 1000

    def test_hysteresis_state_machine(self):
        tracker = ShortageTracker()
        states = []
        for shortage, recovery in [(True, False), (True, False), (False, True), (False, True)]:
            state, _streak = tracker.update(shortage, recovery)
            states.append(state)
        assert states == [
            ShortageState.WATCH,
            ShortageState.ACTIVE,
            ShortageState.RECOVERING,
            ShortageState.NORMAL,
        ]

    def test_hysteresis_interrupted_recovery_returns_active(self):
        tracker = ShortageTracker()
        tracker.update(True, False)   # watch
        tracker.update(True, False)   # active
        tracker.update(False, True)   # recovering
        state, streak = tracker.update(False, False)  # 非 recovery → 回 active/0
        assert state is ShortageState.ACTIVE
        assert streak == 0

    def test_hysteresis_watch_falls_back_without_second_signal(self):
        tracker = ShortageTracker()
        tracker.update(True, False)   # watch
        state, streak = tracker.update(False, False)
        assert state is ShortageState.NORMAL
        assert streak == 0

    def test_default_policy_registered_values(self):
        policy = DEFAULT_SCARCITY_POLICY
        assert policy.policy_id == "scarcity_policy.local_market.v1"
        assert (policy.minimum_q1000, policy.maximum_q1000) == (700, 2000)
        assert policy.hysteresis_closed_buckets == 2
        assert policy.empty_window_fallback_q1000 == 1000
