"""TEST-EVENT-022..024：放置校验链、候选快照原子性、AI 提案 Schema（DOC-EVENT-008）"""

import pytest

from src.events import PlacementError, validate_ai_build_proposal
from event_helpers import build_cottage_full, make_world, place_cottage
from src.events.fixtures import SCENE_TOWN


def _submit(world, fakes, command_id="p1", parcel_id="parcel.town.1",
            template_id="building.cottage", orientation=0, xy=(4, 4),
            requester="resident.mayor", game_time=0, revision_delta=0,
            appropriation=None):
    scene_id = world.parcels.get(parcel_id).scene_id
    revision = fakes.map_port.current_revision(scene_id) + revision_delta
    return world.placement.submit_build(
        command_id=command_id, parcel_id=parcel_id, building_template_id=template_id,
        orientation=orientation, footprint_xy=xy, budget_source="treasury",
        expected_revision=revision, requester_id=requester, game_time=game_time,
        appropriation_evidence_id=appropriation,
    )


def _assert_no_state_change(world, fakes):
    assert world.buildings.all() == []
    assert fakes.map_port.patches == []
    assert world.diff_log.entries(SCENE_TOWN) == []
    assert fakes.map_port.current_revision(SCENE_TOWN) == 0


# -- TEST-EVENT-022：权利、Zoning、Footprint、Orientation ---------------------------


def test_deed_right_missing():
    world, fakes = make_world()
    with pytest.raises(PlacementError) as exc:
        _submit(world, fakes)
    assert exc.value.code == "deed_right_missing"
    _assert_no_state_change(world, fakes)


def test_appropriation_evidence_alternative():
    world, fakes = make_world()
    building = _submit(world, fakes, appropriation="appropriation.decree.1")
    assert building.parcel_id == "parcel.town.1"


def test_zoning_violation():
    world, fakes = make_world()
    fakes.econ.grant_build_right("resident.mayor", "parcel.town.2")
    with pytest.raises(PlacementError) as exc:
        _submit(world, fakes, parcel_id="parcel.town.2")
    assert exc.value.code == "zoning_violation"
    _assert_no_state_change(world, fakes)


def test_footprint_out_of_parcel():
    world, fakes = make_world()
    fakes.econ.grant_build_right("resident.mayor", "parcel.town.1")
    with pytest.raises(PlacementError) as exc:
        _submit(world, fakes, xy=(62, 4))  # 62+4 > 64
    assert exc.value.code == "footprint_out_of_parcel"
    _assert_no_state_change(world, fakes)


def test_orientation_transforms_footprint():
    world, fakes = make_world()
    fakes.econ.grant_build_right("resident.mayor", "parcel.town.1")
    building = _submit(world, fakes, orientation=90, xy=(4, 4))
    # 4x3 旋转 90° → 3x4
    assert building.footprint == {"x": 4, "y": 4, "w": 3, "h": 4}
    # 旋转后超出边界同样被拦截
    world2, fakes2 = make_world()
    fakes2.econ.grant_build_right("resident.mayor", "parcel.town.1")
    with pytest.raises(PlacementError) as exc:
        _submit(world2, fakes2, orientation=90, xy=(62, 60))
    assert exc.value.code == "footprint_out_of_parcel"


def test_orientation_invalid():
    world, fakes = make_world()
    fakes.econ.grant_build_right("resident.mayor", "parcel.town.1")
    with pytest.raises(PlacementError) as exc:
        _submit(world, fakes, orientation=45)
    assert exc.value.code == "orientation_invalid"


# -- TEST-EVENT-023：相交、入口、关键路径、清理、失败原子性 ----------------------------


def test_overlap_detected():
    world, fakes = make_world()
    place_cottage(world, fakes, command_id="o1", x=4, y=4)
    with pytest.raises(PlacementError) as exc:
        _submit(world, fakes, command_id="o2", xy=(6, 5))
    assert exc.value.code == "overlap_detected"


def test_reserved_parcel_rejected():
    world, fakes = make_world()
    fakes.econ.grant_build_right("resident.mayor", "parcel.town.reserved")
    with pytest.raises(PlacementError) as exc:
        _submit(world, fakes, parcel_id="parcel.town.reserved", xy=(4, 68))
    assert exc.value.code == "overlap_detected"


def test_entrance_unreachable():
    world, fakes = make_world()
    fakes.econ.grant_build_right("resident.mayor", "parcel.town.1")
    fakes.map_port.entrance_walkable_hook = lambda _s, _f: False
    with pytest.raises(PlacementError) as exc:
        _submit(world, fakes)
    assert exc.value.code == "entrance_unreachable"
    _assert_no_state_change(world, fakes)


def test_critical_route_cut():
    world, fakes = make_world()
    fakes.econ.grant_build_right("resident.mayor", "parcel.town.1")
    fakes.map_port.critical_routes_hook = lambda _s, _ops: False
    with pytest.raises(PlacementError) as exc:
        _submit(world, fakes)
    assert exc.value.code == "critical_route_cut"
    _assert_no_state_change(world, fakes)


def test_parcel_not_cleared():
    world, fakes = make_world()
    building = build_cottage_full(world, fakes)
    # 损毁成瓦砾但不清理
    world.buildings.apply_damage("d1", building.building_id, "fire", 90, 100)
    world.buildings.demolish("dm1", building.building_id, 101)
    # demolish 连带清理瓦砾 → 重新制造未清理瓦砾场景
    building2 = build_cottage_full(world, fakes, command_id="p-full-2",
                                   parcel_id="parcel.forest.1")
    fakes.econ.grant_build_right("resident.mayor", "parcel.forest.1")
    world.buildings.apply_damage("d2", building2.building_id, "fire", 90, 200)
    with pytest.raises(PlacementError) as exc:
        _submit(world, fakes, command_id="p3", parcel_id="parcel.forest.1",
                xy=(20, 20))
    assert exc.value.code == "parcel_not_cleared"


def test_validation_failure_leaves_no_trace():
    world, fakes = make_world()
    fakes.econ.grant_build_right("resident.mayor", "parcel.town.1")
    for xy in ((70, 4),):  # 依次触发不同失败
        with pytest.raises(PlacementError):
            _submit(world, fakes, xy=xy)
    fakes.map_port.critical_routes_hook = lambda _s, _ops: False
    with pytest.raises(PlacementError):
        _submit(world, fakes)
    _assert_no_state_change(world, fakes)


# -- TEST-EVENT-024：AI 提案 Schema、单事务幂等、expected_revision --------------------


def test_ai_build_proposal_strict_schema():
    valid = {"parcel_id": "parcel.town.1",
             "building_template_id": "building.cottage",
             "budget_source": "treasury"}
    assert validate_ai_build_proposal(valid) == valid
    # 注入字段一律拒绝
    for injected in ("footprint", "permission", "owner_id", "orientation"):
        with pytest.raises(PlacementError) as exc:
            validate_ai_build_proposal({**valid, injected: "x"})
        assert exc.value.code == "ai_build_proposal_invalid"
    with pytest.raises(PlacementError):
        validate_ai_build_proposal({"parcel_id": "p"})
    with pytest.raises(PlacementError):
        validate_ai_build_proposal("not a dict")


def test_submit_single_transaction_and_idempotent():
    world, fakes = make_world()
    fakes.econ.grant_build_right("resident.mayor", "parcel.town.1")
    first = _submit(world, fakes, command_id="tx-1")
    patches = len(fakes.map_port.patches)
    second = _submit(world, fakes, command_id="tx-1")
    assert first.building_id == second.building_id
    assert len(fakes.map_port.patches) == patches  # 幂等：不产生第二笔
    # 单事务四件套：建筑 + patch + event + diff
    entries = world.diff_log.entries(SCENE_TOWN)
    assert len(entries) == 1
    event_types = [e["event_type"] for e in world.event_log.entries()]
    assert "building.placed" in event_types
    assert "navigation.patch_committed" in event_types


def test_stale_revision_rejected():
    world, fakes = make_world()
    fakes.econ.grant_build_right("resident.mayor", "parcel.town.1")
    with pytest.raises(PlacementError) as exc:
        _submit(world, fakes, revision_delta=99)
    assert exc.value.code == "stale_revision"
    _assert_no_state_change(world, fakes)
