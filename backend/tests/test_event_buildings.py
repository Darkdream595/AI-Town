"""TEST-EVENT-019..021：建筑六态、几何绑定、四件套、入住规则（DOC-EVENT-007）"""

import pytest

from src.events import BuildingError, BuildingTemplate
from event_helpers import build_cottage_full, make_world, place_cottage
from src.events.fixtures import SCENE_TOWN, standard_building_templates


# -- TEST-EVENT-019：六态与 Construction Phase 正交受约 -----------------------------


def test_six_physical_states_have_geometry():
    template = standard_building_templates()[0]
    for state in (
        "foundation", "construction", "intact",
        "lightly_damaged", "severely_damaged", "ruins",
    ):
        assert f"state:{state}" in template.state_geometry


def test_template_incomplete_geometry_rejected():
    geometry = dict(standard_building_templates()[0].state_geometry)
    del geometry["state:ruins"]
    with pytest.raises(BuildingError) as exc:
        BuildingTemplate(
            building_template_id="building.broken", name="残缺",
            footprint_wu=(4, 3), zoning_tags=frozenset({"residential"}),
            state_geometry=geometry, salvage_value=1, rebuild_cost=10,
        )
    assert exc.value.code == "template_geometry_incomplete"


def test_phase_constraint_through_lifecycle():
    world, fakes = make_world()
    building = place_cottage(world, fakes)
    # foundation/construction 必须携带有效 phase
    assert building.physical_state == "foundation"
    assert building.construction_phase == "planning"
    building.check_invariant()
    world.construction.deliver_materials("m1", building.building_id,
                                         {"item.stone": 10, "item.timber": 20,
                                          "item.nail": 5}, 0)
    from event_helpers import work_all_phases
    work_all_phases(world, building.building_id)
    building = world.buildings.get(building.building_id)
    # intact 后 phase 必须清空
    assert building.physical_state == "intact"
    assert building.construction_phase is None
    building.check_invariant()


def test_invariant_catches_illegal_combination():
    world, fakes = make_world()
    building = place_cottage(world, fakes)
    building.construction_phase = None  # foundation 无 phase = 违规
    with pytest.raises(BuildingError) as exc:
        building.check_invariant()
    assert exc.value.code == "building_state_invalid"


# -- TEST-EVENT-020：四件套同事务与场景上限 ------------------------------------------


def test_state_change_four_piece_atomic():
    world, fakes = make_world()
    building = build_cottage_full(world, fakes)
    patches_before = len(fakes.map_port.patches)
    diffs_before = len(world.diff_log.entries(SCENE_TOWN))
    log_before = len(world.event_log.entries())
    world.buildings.apply_damage("d1", building.building_id, "storm", 15, 100)
    # 恰好一个 patch、一个 diff entry、damaged+patch_committed 事件
    assert len(fakes.map_port.patches) == patches_before + 1
    entries = world.diff_log.entries(SCENE_TOWN)
    assert len(entries) == diffs_before + 1
    assert entries[-1].diff_kind == "building"
    assert entries[-1].subject_id == building.building_id
    new_types = [e["event_type"] for e in world.event_log.entries()[log_before:]]
    assert "building.damaged" in new_types
    assert "navigation.patch_committed" in new_types
    # 几何同步：lightly_damaged 的 cracks 已上地图
    crack_id = f"{building.building_id}.collision.cracks"
    assert fakes.map_port.current_object(SCENE_TOWN, "collision", crack_id) is not None


def test_each_map_change_has_exactly_one_diff_entry():
    world, fakes = make_world()
    building = build_cottage_full(world, fakes)
    patch_count = len(fakes.map_port.patches)
    diff_count = len(world.diff_log.entries(SCENE_TOWN))
    assert patch_count == diff_count  # 每次持久地图变更恰好一个 entry
    revisions = [e.revision for e in world.diff_log.entries(SCENE_TOWN)]
    assert revisions == sorted(revisions)  # 严格递增


def test_scene_building_cap(monkeypatch):
    import src.events.buildings as buildings_module
    monkeypatch.setattr(buildings_module, "SCENE_BUILDING_CAP", 1)
    world, fakes = make_world()
    place_cottage(world, fakes, command_id="cap-b1", x=4, y=4)
    # 同 scene 第二栋：单 Scene 上限拦截
    revision = fakes.map_port.current_revision(SCENE_TOWN)
    with pytest.raises(BuildingError) as exc:
        world.placement.submit_build(
            command_id="cap-b2", parcel_id="parcel.town.1",
            building_template_id="building.cottage", orientation=0,
            footprint_xy=(20, 40), budget_source="treasury",
            expected_revision=revision, requester_id="resident.mayor",
            game_time=0)
    assert exc.value.code == "scene_building_cap_exceeded"


# -- TEST-EVENT-021：禁入规则、所有权分离、拆除终态 ------------------------------------


def test_severely_damaged_forbids_entry():
    world, fakes = make_world()
    building = build_cottage_full(world, fakes)
    world.buildings.admit_occupant(building.building_id, "resident.a")
    world.buildings.apply_damage("d2", building.building_id, "storm", 45, 100)
    building = world.buildings.get(building.building_id)
    assert building.physical_state == "severely_damaged"
    assert building.interior_active is False
    assert building.occupants == []  # 已安全转移
    with pytest.raises(BuildingError) as exc:
        world.buildings.admit_occupant(building.building_id, "resident.b")
    assert exc.value.code == "building_entry_forbidden"


def test_ruins_has_no_interior():
    world, fakes = make_world()
    building = build_cottage_full(world, fakes)
    world.buildings.apply_damage("d3", building.building_id, "fire", 90, 100)
    building = world.buildings.get(building.building_id)
    assert building.physical_state == "ruins"
    assert building.interior_active is False
    with pytest.raises(BuildingError):
        world.buildings.admit_occupant(building.building_id, "resident.c")


def test_events_never_write_ownership():
    world, fakes = make_world()
    building = place_cottage(world, fakes)
    # Building 聚合不含 owner 字段；Deed 归 ECON 所有
    assert not hasattr(building, "owner_id")
    assert not hasattr(building, "deed_id")
    assert fakes.econ.has_build_right("resident.mayor", "parcel.town.1")


def test_demolish_terminal_and_id_never_reused():
    world, fakes = make_world()
    building = build_cottage_full(world, fakes)
    old_id = building.building_id
    world.buildings.demolish("demo-1", old_id, 200)
    assert world.buildings.get(old_id).removed is True
    with pytest.raises(BuildingError) as exc:
        world.buildings.demolish("demo-2", old_id, 201)
    assert exc.value.code == "building_state_invalid"
    # parcel 释放；新建筑拿到新 id
    new_building = place_cottage(world, fakes, command_id="cap-b3", x=4, y=4)
    assert new_building.building_id != old_id
    # 地图几何已清空
    assert fakes.map_port.current_object(
        SCENE_TOWN, "collision", f"{old_id}.collision.walls") is None
