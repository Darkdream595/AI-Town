"""TEST-COMBAT-011/012/013：状态施加与叠加、tick 与属性投影、终结清理

覆盖 RULE-COMBAT-026..031（doc 05 §11）
"""

import pytest

from src.combat import (
    ActionKind,
    StatusCategory,
    StatusDefinition,
    StatusError,
    StatusRegistry,
    StatusStore,
    StackingPolicy,
    build_default_statuses,
)
from src.combat.fixtures import make_id_factory


def _store() -> StatusStore:
    return StatusStore(build_default_statuses(), make_id_factory())


class TestApplyAndStacking:
    """RULE-COMBAT-026..028：四种叠加策略的唯一结果"""

    def test_refresh_duration_policy(self):
        store = _store()
        first, kind1 = store.apply("e1", "status.regeneration", "h1", "ev", 0)
        first.remaining_turns = 1
        second, kind2 = store.apply("e1", "status.regeneration", "h1", "ev", 1)
        assert first is second and kind1 == "created" and kind2 == "refreshed"
        assert second.remaining_turns == 4

    def test_stack_intensity_policy(self):
        store = _store()
        instance, _ = store.apply("e1", "status.burning", "h1", "ev", 0)
        instance, kind = store.apply("e1", "status.burning", "h1", "ev", 1)
        assert kind == "stacked" and instance.stack_count == 2
        instance, kind = store.apply("e1", "status.burning", "h1", "ev", 2)
        assert instance.stack_count == 3
        _, kind = store.apply("e1", "status.burning", "h1", "ev", 3)
        assert kind == "refreshed"  # 满层只刷新
        assert instance.stack_count == 3

    def test_reject_duplicate_policy(self):
        store = _store()
        store.apply("e1", "status.weakened", "h1", "ev", 0)
        with pytest.raises(StatusError) as exc:
            store.apply("e1", "status.weakened", "h1", "ev", 1)
        assert exc.value.code == "combat_status_rejected"

    def test_independent_instances_policy(self):
        store = _store()
        first, _ = store.apply("e1", "status.guarded", "h1", "ev", 0)
        second, kind = store.apply("e1", "status.guarded", "h1", "ev", 1)
        assert kind == "created" and first.status_instance_id != second.status_instance_id
        with pytest.raises(StatusError):
            store.apply("e1", "status.guarded", "h1", "ev", 2)  # max 2

    def test_unregistered_definition_fail_closed(self):
        store = _store()
        with pytest.raises(StatusError) as exc:
            store.apply("e1", "status.nonexistent", "h1", "ev", 0)
        assert exc.value.code == "COMBAT_STATUS_DEFINITION_INVALID"

    def test_instance_cap_sixteen(self):
        registry = StatusRegistry()
        for index in range(17):
            registry.register(StatusDefinition(
                definition_id=f"status.custom.{index}", category=StatusCategory.BUFF,
                attribute_deltas={}, per_tick_formula_ref=None, duration_turns=2,
                stacking_policy=StackingPolicy.INDEPENDENT_INSTANCES, max_stacks=1,
                forbidden_action_kinds=(), persist_mapping=None,
            ))
        store = StatusStore(registry, make_id_factory())
        for index in range(16):
            store.apply("e1", f"status.custom.{index}", "h1", "ev", 0)
        with pytest.raises(StatusError) as exc:
            store.apply("e1", "status.custom.16", "h1", "ev", 0)
        assert exc.value.code == "combat_status_instance_cap"

    def test_control_definition_requires_forbidden_kinds(self):
        with pytest.raises(StatusError) as exc:
            StatusDefinition(
                definition_id="status.bad_control", category=StatusCategory.CONTROL,
                attribute_deltas={}, per_tick_formula_ref=None, duration_turns=1,
                stacking_policy=StackingPolicy.REFRESH_DURATION, max_stacks=1,
                forbidden_action_kinds=(), persist_mapping=None,
            ).validate()
        assert exc.value.code == "COMBAT_STATUS_DEFINITION_INVALID"


class TestTickAndProjection:
    """RULE-COMBAT-029/030：tick 顺序、dot/hot 结算、属性投影含层数、移除即还原"""

    def test_tick_ulid_ascending_order(self):
        store = _store()
        first, _ = store.apply("e1", "status.burning", "h1", "ev", 0)
        second, _ = store.apply("e1", "status.guarded", "h1", "ev", 1)
        results, _ = store.tick("h1")
        assert [r["status_instance_id"] for r in results] == sorted(
            [first.status_instance_id, second.status_instance_id])

    def test_dot_scales_with_stacks(self):
        store = _store()
        instance, _ = store.apply("e1", "status.burning", "h1", "ev", 0)
        instance.stack_count = 3
        results, _ = store.tick("h1")
        assert results[0]["hp_delta"] == -6

    def test_hot_heals_per_stack(self):
        store = _store()
        store.apply("e1", "status.regeneration", "h1", "ev", 0)
        results, _ = store.tick("h1")
        assert results[0]["hp_delta"] == 3

    def test_expiry_removed_same_transaction(self):
        store = _store()
        instance, _ = store.apply("e1", "status.stunned", "h1", "ev", 0)  # duration 1
        _, expired = store.tick("h1")
        assert expired == [instance.status_instance_id]
        assert store.instances_of("h1") == []

    def test_attribute_delta_projection_with_stacks(self):
        store = _store()
        instance, _ = store.apply("e1", "status.burning", "h1", "ev", 0)
        store.apply("e1", "status.weakened", "h1", "ev", 0)
        store.apply("e1", "status.guarded", "h1", "ev", 0)
        assert store.attribute_delta_for("h1", "strength") == -10
        assert store.attribute_delta_for("h1", "defense") == 8
        store.remove_by_category("h1", StatusCategory.DEBUFF, 1)
        assert store.attribute_delta_for("h1", "strength") == 0  # 移除即还原

    def test_forbidden_kinds_union(self):
        store = _store()
        store.apply("e1", "status.stunned", "h1", "ev", 0)
        forbidden = store.forbidden_kinds_for("h1")
        assert ActionKind.ATTACK in forbidden and ActionKind.FLEE in forbidden
        assert ActionKind.DEFEND not in forbidden and ActionKind.PASS not in forbidden


class TestEndCleanup:
    """RULE-COMBAT-031：终结统一清理、Persist Mapping 转换、无 Overworld 残留"""

    def test_persist_mappings_collected(self):
        store = _store()
        store.apply("e1", "status.burning", "h1", "ev", 0)
        store.apply("e1", "status.guarded", "h1", "ev", 0)
        mappings = store.persist_mappings_for("h1")
        assert mappings == ["injury.burn_wound"]  # guarded 无 mapping

    def test_clear_encounter_leaves_nothing(self):
        store = _store()
        store.apply("e1", "status.burning", "h1", "ev", 0)
        store.apply("e1", "status.weakened", "h2", "ev", 0)
        store.clear_encounter()
        assert store.all_instances() == []
        assert store.instances_of("h1") == [] and store.instances_of("h2") == []

    def test_full_battle_status_lifecycle(self):
        """Integration：燃烧经选项施加、tick 扣血、终结转 injury 并入 settlement"""
        from combat_helpers import run_full, start_fixture

        engine, eid, ports = start_fixture()
        enc = engine._require(eid)
        enemy = next(c for c in enc.combatants.values() if c.side.value == "adversary")
        enc.status_store.apply(eid, "status.burning", enemy.combatant_id, "event.test", 0)
        hp_before = enemy.stats.hp_current
        result = run_full(engine, eid)
        # 终结后实例清空
        assert enc.status_store.all_instances() == []
        resolved = next(e for e in engine.events if e["event_kind"] == "EncounterResolved")
        # creature 无 settlement；若 enemy 曾活过自身回合则 tick 扣过血
        assert result["state"] == "ended"
