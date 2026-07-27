"""TEST-EVENT-025..027：施工阶段机、材料劳动、升级路径、停滞检测（DOC-EVENT-009）"""

import pytest

from src.events import ConstructionError
from event_helpers import (
    COTTAGE_MATERIALS,
    PHASES,
    build_cottage_full,
    make_world,
    occ,
    place_cottage,
    work_all_phases,
)
from src.events.fixtures import SCENE_TOWN


def _session(world, command_id, building_id, profession, minutes,
             game_time=0, expected_phase=None, efficiency=10_000,
             expected_version=None):
    building = world.buildings.get(building_id)
    return world.construction.submit_work_session(
        command_id=command_id, building_id=building_id,
        profession=profession, labor_game_minutes=minutes,
        efficiency_bps=efficiency, game_time=game_time,
        expected_phase=expected_phase or building.construction_phase,
        expected_version=(
            expected_version if expected_version is not None else building.version
        ),
    )


# -- TEST-EVENT-025：阶段顺序、劳动累计、材料门槛 ------------------------------------


def test_phase_order_violation():
    world, fakes = make_world()
    building = place_cottage(world, fakes)
    with pytest.raises(ConstructionError) as exc:
        _session(world, "w1", building.building_id, "laborer", 120,
                 expected_phase="clearing")
    assert exc.value.code == "phase_order_violation"


def test_profession_missing():
    world, fakes = make_world()
    building = place_cottage(world, fakes)
    with pytest.raises(ConstructionError) as exc:
        _session(world, "w2", building.building_id, "blacksmith", 60,
                 expected_phase="planning")
    assert exc.value.code == "profession_missing"


def test_labor_accumulates_with_efficiency():
    world, fakes = make_world()
    building = place_cottage(world, fakes)
    # 60 分钟需求：30 分钟 × 50% 效率 = 15；再 90 分钟 × 100% = 90，合计 105 ≥ 60
    _session(world, "w3a", building.building_id, "architect", 30, efficiency=5_000)
    site = world.construction.site_of(building.building_id)
    assert site.labor_progress["planning"] == 15
    assert world.buildings.get(building.building_id).construction_phase == "planning"
    _session(world, "w3b", building.building_id, "architect", 90)
    assert world.buildings.get(building.building_id).construction_phase == "clearing"


def test_materials_gate_phase_completion():
    world, fakes = make_world()
    building = place_cottage(world, fakes)
    # planning/clearing 无材料需求，推进到 foundation_work
    _session(world, "w4a", building.building_id, "architect", 60,
             expected_phase="planning")
    _session(world, "w4b", building.building_id, "laborer", 120,
             expected_phase="clearing", game_time=1)
    # foundation_work 需要 stone 10：只交 5 → 劳动满也不完成
    world.construction.deliver_materials("m4", building.building_id,
                                         {"item.stone": 5}, 2)
    _session(world, "w4c", building.building_id, "mason", 240,
             expected_phase="foundation_work", game_time=3)
    assert world.buildings.get(building.building_id).construction_phase == "foundation_work"
    short_logs = [e for e in world.event_log.entries()
                  if e["event_type"] == "construction.materials_insufficient"]
    assert short_logs and short_logs[-1]["payload"]["missing"] == {"item.stone": 10}
    # 补足材料后下一会话完成阶段
    world.construction.deliver_materials("m4b", building.building_id,
                                         {"item.stone": 5}, 4)
    _session(world, "w4d", building.building_id, "mason", 1,
             expected_phase="foundation_work", game_time=5)
    assert world.buildings.get(building.building_id).construction_phase == "structure_work"
    site = world.construction.site_of(building.building_id)
    assert site.materials_escrow["item.stone"] == 0  # 材料在阶段完成时消耗


def test_deliver_to_non_construction_rejected():
    world, fakes = make_world()
    building = build_cottage_full(world, fakes)
    with pytest.raises(ConstructionError) as exc:
        world.construction.deliver_materials("m5", building.building_id,
                                             {"item.stone": 1}, 100)
    assert exc.value.code == "building_state_invalid"


def test_site_inventory_conflict_on_payload_mismatch():
    world, fakes = make_world()
    building = place_cottage(world, fakes)
    world.construction.deliver_materials("m6", building.building_id,
                                         {"item.stone": 5}, 0)
    # 同 command_id 同载荷 = 幂等；不同载荷 = 冲突
    world.construction.deliver_materials("m6", building.building_id,
                                         {"item.stone": 5}, 0)
    with pytest.raises(ConstructionError) as exc:
        world.construction.deliver_materials("m6", building.building_id,
                                             {"item.stone": 99}, 0)
    assert exc.value.code == "site_inventory_conflict"


def test_version_stale_on_session():
    world, fakes = make_world()
    building = place_cottage(world, fakes)
    with pytest.raises(ConstructionError) as exc:
        _session(world, "w7", building.building_id, "architect", 60,
                 expected_version=building.version + 7)
    assert exc.value.code == "version_stale"


# -- TEST-EVENT-026：几何同步、升级路径、无降级 ----------------------------------------


def test_geometric_sync_per_phase():
    world, fakes = make_world()
    building = place_cottage(world, fakes)
    world.construction.deliver_materials("m8", building.building_id,
                                         dict(COTTAGE_MATERIALS), 0)
    bid = building.building_id
    _session(world, "w8a", bid, "architect", 60, expected_phase="planning")
    _session(world, "w8b", bid, "laborer", 120, expected_phase="clearing",
             game_time=1)
    path_obj = fakes.map_port.current_object(
        SCENE_TOWN, "walkability", f"{bid}.walkability.site_path")
    assert path_obj is not None  # clearing 完成几何同步
    _session(world, "w8c", bid, "mason", 240, expected_phase="foundation_work",
             game_time=2)
    assert fakes.map_port.current_object(
        SCENE_TOWN, "collision", f"{bid}.collision.foundation") is not None
    _session(world, "w8d", bid, "carpenter", 480, expected_phase="structure_work",
             game_time=3)
    building = world.buildings.get(bid)
    assert building.physical_state == "construction"  # structure_work 后进入施工态
    assert fakes.map_port.current_object(
        SCENE_TOWN, "collision", f"{bid}.collision.walls") is not None
    _session(world, "w8e", bid, "carpenter", 120, expected_phase="fitting",
             game_time=4)
    _session(world, "w8f", bid, "architect", 30, expected_phase="acceptance",
             game_time=5)
    building = world.buildings.get(bid)
    assert building.physical_state == "intact"
    assert building.interior_active is True
    # intact 几何：foundation 移除，interior 语义节点上线
    assert fakes.map_port.current_object(
        SCENE_TOWN, "collision", f"{bid}.collision.foundation") is None
    assert fakes.map_port.current_object(
        SCENE_TOWN, "semantic", f"{bid}.semantic.room") is not None
    # 审计：diff hash 与地图一致
    assert world.audit_invariants(10)["ok"]


def test_upgrade_path_and_template_swap():
    world, fakes = make_world()
    building = build_cottage_full(world, fakes)
    bid = building.building_id
    world.construction.start_upgrade("up-1", bid, "building.manor", 100,
                                     expected_version=building.version)
    building = world.buildings.get(bid)
    assert building.physical_state == "construction"
    assert building.construction_phase == "planning"
    assert building.upgrade_target == "building.manor"
    # 升级期走对称施工（manor 需求 scale=2）
    world.construction.deliver_materials(
        "up-m", bid, {"item.stone": 20, "item.timber": 40, "item.nail": 10}, 101)
    manor_phases = [("planning", "architect", 120), ("clearing", "laborer", 240),
                    ("foundation_work", "mason", 480),
                    ("structure_work", "carpenter", 960),
                    ("fitting", "carpenter", 240), ("acceptance", "architect", 60)]
    for index, (phase, profession, minutes) in enumerate(manor_phases):
        current = world.buildings.get(bid)
        world.construction.submit_work_session(
            f"up-w{index}", bid, profession, minutes, 10_000, 102 + index,
            expected_phase=phase, expected_version=current.version)
    building = world.buildings.get(bid)
    assert building.building_template_id == "building.manor"
    assert building.physical_state == "intact"
    assert building.upgrade_target is None
    assert world.audit_invariants(200)["ok"]


def test_upgrade_path_unknown_and_no_downgrade():
    world, fakes = make_world()
    building = build_cottage_full(world, fakes)
    with pytest.raises(ConstructionError) as exc:
        world.construction.start_upgrade("up-2", building.building_id,
                                         "building.castle", 100,
                                         expected_version=building.version)
    assert exc.value.code == "upgrade_path_unknown"
    # manor 没有注册任何升级目标 → 降级路径不存在
    world.construction.start_upgrade("up-3", building.building_id,
                                     "building.manor", 100,
                                     expected_version=building.version)
    building = world.buildings.get(building.building_id)
    world.construction.deliver_materials(
        "up-m2", building.building_id,
        {"item.stone": 20, "item.timber": 40, "item.nail": 10}, 101)
    for index, (phase, profession, minutes) in enumerate([
            ("planning", "architect", 120), ("clearing", "laborer", 240),
            ("foundation_work", "mason", 480), ("structure_work", "carpenter", 960),
            ("fitting", "carpenter", 240), ("acceptance", "architect", 60)]):
        current = world.buildings.get(building.building_id)
        world.construction.submit_work_session(
            f"up-w2-{index}", building.building_id, profession, minutes, 10_000,
            102 + index, expected_phase=phase, expected_version=current.version)
    manor = world.buildings.get(building.building_id)
    with pytest.raises(ConstructionError) as exc:
        world.construction.start_upgrade("up-4", manor.building_id,
                                         "building.cottage", 200,
                                         expected_version=manor.version)
    assert exc.value.code == "upgrade_path_unknown"


def test_upgrade_requires_intact():
    world, fakes = make_world()
    building = build_cottage_full(world, fakes)
    world.buildings.apply_damage("du", building.building_id, "storm", 15, 50)
    building = world.buildings.get(building.building_id)
    with pytest.raises(ConstructionError) as exc:
        world.construction.start_upgrade("up-5", building.building_id,
                                         "building.manor", 51,
                                         expected_version=building.version)
    assert exc.value.code == "building_state_invalid"


# -- TEST-EVENT-027：中断保留、停滞检测、恢复 ------------------------------------------


def test_interruption_preserves_progress_and_materials():
    world, fakes = make_world()
    building = place_cottage(world, fakes)
    world.construction.deliver_materials("m9", building.building_id,
                                         dict(COTTAGE_MATERIALS), 0)
    _session(world, "w9a", building.building_id, "architect", 30)
    site = world.construction.site_of(building.building_id)
    assert site.labor_progress["planning"] == 30
    assert site.materials_escrow["item.stone"] == 10  # 中断不丢材料
    # 很久以后继续：进度保留
    _session(world, "w9b", building.building_id, "architect", 30,
             game_time=5000)
    assert world.buildings.get(building.building_id).construction_phase == "clearing"


def test_stalled_detection_and_notification():
    world, fakes = make_world()
    building = place_cottage(world, fakes)
    _session(world, "w10", building.building_id, "architect", 10, game_time=0)
    # 4320 分钟无会话 → stalled + 通知 owner
    result = world.on_occurrence(occ(
        "construction_stall_check", "stall-1", 4321))
    assert result["result"]["stalled"] == [building.building_id]
    site = world.construction.site_of(building.building_id)
    assert site.stalled is True
    notifications = [n for n in fakes.resident.notifications
                     if n["kind"] == "construction_stalled"]
    assert len(notifications) == 1
    assert notifications[0]["content"]["building_id"] == building.building_id
    # 检查幂等：同 occurrence 重放
    replay = world.on_occurrence(occ("construction_stall_check", "stall-1", 4321))
    assert replay["status"] == "replayed"


def test_stalled_site_resumes_on_session():
    world, fakes = make_world()
    building = place_cottage(world, fakes)
    _session(world, "w11a", building.building_id, "architect", 10, game_time=0)
    world.on_occurrence(occ("construction_stall_check", "stall-2", 5000))
    site = world.construction.site_of(building.building_id)
    assert site.stalled is True
    _session(world, "w11b", building.building_id, "architect", 10, game_time=5001)
    assert site.stalled is False
    # 恢复后再次停滞可重新检测
    result = world.on_occurrence(occ(
        "construction_stall_check", "stall-3", 5001 + 4321))
    assert result["result"]["stalled"] == [building.building_id]


def test_completed_building_not_stalled():
    world, fakes = make_world()
    build_cottage_full(world, fakes)
    result = world.on_occurrence(occ(
        "construction_stall_check", "stall-4", 99999))
    assert result["result"]["stalled"] == []
