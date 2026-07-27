"""TEST-EVENT-028..030：损毁来源、阈值映射、瓦砾、修复分级、decay（DOC-EVENT-010）"""

import pytest

from src.events import BuildingError, BuildingTemplate
from event_helpers import build_cottage_full, make_world, occ, place_cottage
from src.events.fixtures import SCENE_TOWN, standard_building_templates


def _full(world, fakes, command_id="p-full"):
    return build_cottage_full(world, fakes, command_id=command_id)


# -- TEST-EVENT-028：来源约束与阈值唯一映射 ------------------------------------------


def test_damage_source_must_be_registered():
    world, fakes = make_world()
    building = _full(world, fakes)
    with pytest.raises(BuildingError) as exc:
        world.buildings.apply_damage("s1", building.building_id, "earthquake", 10, 0)
    assert exc.value.code == "damage_source_invalid"
    with pytest.raises(BuildingError) as exc:
        world.buildings.apply_damage("s2", building.building_id, "fire", -5, 0)
    assert exc.value.code == "damage_points_invalid"


def test_threshold_table_unique_mapping():
    world, fakes = make_world()
    building = _full(world, fakes)
    bid = building.building_id
    world.buildings.apply_damage("t1", bid, "combat", 5, 0)
    assert world.buildings.get(bid).physical_state == "intact"       # 0..9
    world.buildings.apply_damage("t2", bid, "combat", 5, 1)
    assert world.buildings.get(bid).physical_state == "lightly_damaged"   # 10..39
    world.buildings.apply_damage("t3", bid, "combat", 30, 2)
    assert world.buildings.get(bid).physical_state == "severely_damaged"  # 40..79
    world.buildings.apply_damage("t4", bid, "combat", 40, 3)
    assert world.buildings.get(bid).physical_state == "ruins"        # ≥80
    # 每次跨阈值恰好一个 diff entry
    assert len(world.diff_log.entries(SCENE_TOWN)) == len(fakes.map_port.patches)


def test_damage_on_construction_site_rejected():
    world, fakes = make_world()
    building = place_cottage(world, fakes)
    with pytest.raises(BuildingError) as exc:
        world.buildings.apply_damage("t5", building.building_id, "storm", 10, 0)
    assert exc.value.code == "building_state_invalid"


def test_no_crossing_means_no_diff_entry():
    world, fakes = make_world()
    building = _full(world, fakes)
    diffs_before = len(world.diff_log.entries(SCENE_TOWN))
    world.buildings.apply_damage("t6", building.building_id, "decay", 3, 0)
    assert world.buildings.get(building.building_id).damage_points == 3
    assert len(world.diff_log.entries(SCENE_TOWN)) == diffs_before


# -- TEST-EVENT-029：瓦砾原子生成、排他领取、转移回滚 ------------------------------------


def test_ruins_spawns_rubble_atomically():
    world, fakes = make_world()
    building = _full(world, fakes)
    bid = building.building_id
    world.buildings.apply_damage("r1", bid, "fire", 85, 100)
    building = world.buildings.get(bid)
    assert building.physical_state == "ruins"
    rubble = world.buildings.rubble_of(bid)
    assert rubble is not None
    # 同一事务：collision 上地图 + salvage 进 ECON 托管
    assert fakes.map_port.current_object(
        SCENE_TOWN, "collision", rubble.rubble_id) is not None
    pool = fakes.econ.salvage_escrows[rubble.salvage_pool_id]
    assert pool["resources"]["value"] == 15  # cottage salvage_value


def test_rubble_exclusive_claim_prevents_duplication():
    world, fakes = make_world()
    building = _full(world, fakes)
    world.buildings.apply_damage("r2", building.building_id, "fire", 85, 100)
    rubble = world.buildings.rubble_of(building.building_id)
    world.buildings.claim_rubble("cl-1", rubble.rubble_id, "resident.a", 101)
    with pytest.raises(BuildingError) as exc:
        world.buildings.claim_rubble("cl-2", rubble.rubble_id, "resident.b", 102)
    assert exc.value.code == "rubble_already_claimed"
    assert fakes.econ.salvage_escrows[rubble.salvage_pool_id]["claimed_by"] == "resident.a"


def test_rubble_cleanup_satisfies_parcel_cleared():
    world, fakes = make_world()
    building = _full(world, fakes)
    world.buildings.apply_damage("r3", building.building_id, "fire", 85, 100)
    rubble = world.buildings.rubble_of(building.building_id)
    assert world.buildings.parcel_has_rubble("parcel.town.1")
    world.buildings.claim_rubble("cl-3", rubble.rubble_id, "resident.a", 101)
    world.buildings.cleanup_rubble("cl-4", rubble.rubble_id, 102)
    assert not world.buildings.parcel_has_rubble("parcel.town.1")
    # 清理后 collision 移除（四件套）
    assert fakes.map_port.current_object(
        SCENE_TOWN, "collision", rubble.rubble_id) is None
    assert world.audit_invariants(103)["ok"]


def test_relocation_failure_rolls_back_entirely():
    world, fakes = make_world()
    building = _full(world, fakes)
    bid = building.building_id
    world.buildings.admit_occupant(bid, "resident.a")
    fakes.resident.fail_relocation = True
    patches_before = len(fakes.map_port.patches)
    diffs_before = len(world.diff_log.entries(SCENE_TOWN))
    with pytest.raises(BuildingError) as exc:
        world.buildings.apply_damage("r4", bid, "storm", 50, 100)
    assert exc.value.code == "occupant_relocation_failed"
    # 整笔回滚：状态、地图、diff、居住者全部不变
    building = world.buildings.get(bid)
    assert building.physical_state == "intact"
    assert building.damage_points == 0
    assert building.occupants == ["resident.a"]
    assert len(fakes.map_port.patches) == patches_before
    assert len(world.diff_log.entries(SCENE_TOWN)) == diffs_before


# -- TEST-EVENT-030：修复分级、重建防套利、decay ----------------------------------------


def test_light_repair_direct():
    world, fakes = make_world()
    building = _full(world, fakes)
    bid = building.building_id
    world.buildings.apply_damage("rp1", bid, "decay", 20, 0)
    world.buildings.repair("rp2", bid, labor_game_minutes=200,
                           materials={"item.timber": 2}, game_time=10)
    building = world.buildings.get(bid)
    assert building.damage_points == 0
    assert building.physical_state == "intact"
    # 材料经 ECON 结算
    assert fakes.econ.material_consumptions[-1]["materials"] == {"item.timber": 2}


def test_severe_repair_requires_valid_assessment():
    world, fakes = make_world()
    building = _full(world, fakes)
    bid = building.building_id
    world.buildings.apply_damage("rp3", bid, "storm", 50, 0)
    with pytest.raises(BuildingError) as exc:
        world.buildings.repair("rp4", bid, 500, {}, 10)
    assert exc.value.code == "assessment_required"
    assessment = world.buildings.assess_damage("rp5", bid, 10)
    world.buildings.repair("rp6", bid, 500, {}, 20,
                           assessment_id=assessment.assessment_id)
    assert world.buildings.get(bid).physical_state == "intact"


def test_expired_assessment_rejected():
    world, fakes = make_world()
    building = _full(world, fakes)
    bid = building.building_id
    world.buildings.apply_damage("rp7", bid, "storm", 50, 0)
    assessment = world.buildings.assess_damage("rp8", bid, 10,
                                               valid_duration=100)
    with pytest.raises(BuildingError) as exc:
        world.buildings.repair("rp9", bid, 500, {}, 200,
                               assessment_id=assessment.assessment_id)
    assert exc.value.code == "assessment_expired"


def test_ruins_not_repairable():
    world, fakes = make_world()
    building = _full(world, fakes)
    world.buildings.apply_damage("rp10", building.building_id, "fire", 85, 0)
    with pytest.raises(BuildingError) as exc:
        world.buildings.repair("rp11", building.building_id, 9999, {}, 10)
    assert exc.value.code == "building_state_invalid"


def test_repair_never_exceeds_intact():
    world, fakes = make_world()
    building = _full(world, fakes)
    bid = building.building_id
    world.buildings.apply_damage("rp12", bid, "decay", 15, 0)
    world.buildings.repair("rp13", bid, labor_game_minutes=100_000,
                           materials={}, game_time=10)
    building = world.buildings.get(bid)
    assert building.damage_points == 0
    assert building.physical_state == "intact"


def test_rebuild_cost_exceeds_salvage_at_registration():
    with pytest.raises(BuildingError) as exc:
        BuildingTemplate(
            building_template_id="building.arbitrage", name="套利",
            footprint_wu=(4, 3), zoning_tags=frozenset({"residential"}),
            state_geometry=standard_building_templates()[0].state_geometry,
            salvage_value=100, rebuild_cost=50,
        )
    assert exc.value.code == "template_arbitrage"


def test_decay_periodic_and_reinforcement():
    world, fakes = make_world()
    building = _full(world, fakes)
    bid = building.building_id
    world.buildings.reinforce(bid, 10_000, 1440 * 3, game_time=0)  # 全免 3 周期
    world.on_occurrence(occ("decay_eval", "decay-1", 1440))
    assert world.buildings.get(bid).damage_points == 0
    world.on_occurrence(occ("decay_eval", "decay-2", 2880))
    assert world.buildings.get(bid).damage_points == 0
    # 加固到期后恢复衰变
    world.on_occurrence(occ("decay_eval", "decay-3", 1440 * 4))
    assert world.buildings.get(bid).damage_points == 1
    decay_logs = [e for e in world.event_log.entries()
                  if e["event_type"] == "building.decay_eval"]
    assert len(decay_logs) == 3


def test_decay_crossing_threshold_goes_four_piece():
    world, fakes = make_world()
    building = _full(world, fakes)
    bid = building.building_id
    world.buildings.apply_damage("dc1", bid, "combat", 9, 0)  # intact 边缘
    diffs_before = len(world.diff_log.entries(SCENE_TOWN))
    world.on_occurrence(occ("decay_eval", "decay-4", 1440))  # +1 → 10 lightly
    building = world.buildings.get(bid)
    assert building.damage_points == 10
    assert building.physical_state == "lightly_damaged"
    assert len(world.diff_log.entries(SCENE_TOWN)) == diffs_before + 1
