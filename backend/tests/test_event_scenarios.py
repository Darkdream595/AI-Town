"""TEST-EVENT-039/040：Scenario Fixture 全链场景（DOC-EVENT-012）

- 固定 Seed + 固定命令脚本 → 事件日志时间线与注册表钉死值逐条一致（RULE-EVENT-069）
- Oracle：audit_invariants / 预算从未超限 / 无重复事件 / Diff 重放一致 / 导出导入一致
"""

from src.events.constants import ACTIVE_WEIGHT_CAP
from src.events.fixtures import SCENARIO_FIXTURES, SCENE_FOREST

from event_helpers import (
    make_world,
    occ,
    run_scenario_construction,
    run_scenario_forest_fire,
)


def test_scenario_fixture_registry_complete():
    """两个全链场景注册完整：脚本存在、种子固定、预期时间线 revision 从 0 连续"""
    import event_helpers

    assert set(SCENARIO_FIXTURES) == {
        "scenario.event.forest_fire_full_chain",
        "scenario.event.construction_full_chain",
    }
    for fixture in SCENARIO_FIXTURES.values():
        assert callable(getattr(event_helpers, fixture.script)), fixture.script
        assert fixture.seed_hex and fixture.expected_timeline, fixture.fixture_id
        revisions = [revision for revision, _ in fixture.expected_timeline]
        assert revisions == list(range(len(revisions))), fixture.fixture_id


# -- TEST-EVENT-039：森林火灾全链 --------------------------------------------


def test_event_039_forest_fire_full_chain():
    fixture = SCENARIO_FIXTURES["scenario.event.forest_fire_full_chain"]
    world, fakes = make_world(seed_hex=fixture.seed_hex)
    artifacts = run_scenario_forest_fire(world, fakes)

    # 时间线与注册表钉死值逐条一致
    assert world.event_log.timeline() == list(fixture.expected_timeline)

    # Oracle：不变量（预算/生命周期/Diff Hash/Building Binding）
    audit = world.audit_invariants(world.test_clock["now"])
    assert audit["ok"], audit["violations"]
    # Oracle：预算从未超限
    assert audit["active_weight"] <= ACTIVE_WEIGHT_CAP

    # 事件终态归档；aftermath 零 pending
    event = world.engine.get(artifacts["fire_event_id"])
    assert event.state == "archived"
    assert world.aftermath.pending_count(artifacts["fire_event_id"]) == 0

    # 封路已 Reverse 重开：fire_line 障碍从 live layers 移除
    assert fakes.map_port.current_object(
        SCENE_FOREST, "collision", "blockade.fire.1") is None

    # 瓦砾排他领取并清理，parcel 恢复可建
    rubble_state = world.buildings.export_state()["rubble"][artifacts["rubble_id"]]
    assert rubble_state["claimed_by"] == "resident.hero" and rubble_state["cleaned"]
    assert not world.buildings.parcel_has_rubble(rubble_state["parcel_id"])
    assert fakes.econ.salvage_escrows[rubble_state["salvage_pool_id"]]["claimed_by"] == "resident.hero"

    # 营救奖励经 ECON 发放（赔偿链）
    assert any(
        reward["resident_id"] == "resident.hero" and reward["reward_kind"] == "currency"
        for reward in fakes.econ.rewards
    )

    # Oracle：无重复事件——同一 trigger occurrence 重放不产生新实例
    before = len(world.event_log)
    replayed = world.on_occurrence(occ(
        "trigger_eval", "s39-trig-1", 10,
        projection={"scene_id": SCENE_FOREST, "public": {"drought_days": 3}},
        source="state"))
    assert replayed["status"] == "replayed"
    assert len(world.event_log) == before
    instantiations = [
        entry for entry in world.event_log.entries()
        if entry["event_type"] == "world_event.instantiated"
        and entry["payload"]["event_template_id"] == "event.disaster.forest_fire"
    ]
    assert len(instantiations) == 1


# -- TEST-EVENT-040：建造全链 + 重放一致 ---------------------------------------


def test_event_040_construction_full_chain_replay_consistent():
    fixture = SCENARIO_FIXTURES["scenario.event.construction_full_chain"]
    world, fakes = make_world(seed_hex=fixture.seed_hex)
    artifacts = run_scenario_construction(world, fakes)

    # 时间线与注册表钉死值逐条一致
    assert world.event_log.timeline() == list(fixture.expected_timeline)

    # Oracle：不变量
    audit = world.audit_invariants(world.test_clock["now"])
    assert audit["ok"], audit["violations"]

    # 升级跨模板几何锚定 + 修复归零
    building = world.buildings.get(artifacts["building_id"])
    assert building.building_template_id == "building.manor"
    assert building.physical_state == "intact" and building.damage_points == 0
    assert building.geometry_key == "state:intact"

    # Oracle：导出 → 同种子新世界导入 → 日志 / Diff 重放 / 建筑状态完全一致
    state = world.export_state()
    world2, fakes2 = make_world(seed_hex=fixture.seed_hex)
    world2.import_state(state)
    assert world2.event_log.timeline() == world.event_log.timeline()
    for scene_id in fakes.map_port.scene_ids():
        replay_original = world.diff_log.replay(
            scene_id, fakes.map_port.base_layers(scene_id))
        replay_imported = world2.diff_log.replay(
            scene_id, fakes2.map_port.base_layers(scene_id))
        hash_original = world.diff_log.compute_diff_hash(replay_original)
        hash_imported = world2.diff_log.compute_diff_hash(replay_imported)
        assert hash_original == hash_imported == fakes.map_port.current_layers_hash(scene_id)
    assert (world2.buildings.get(artifacts["building_id"]).to_dict()
            == building.to_dict())
