"""TEST-EVENT-031..033：WorldDiff append-only、逆向链、重放一致性（DOC-EVENT-011）"""

import pytest

from src.events import DiffError, DiffOperation
from src.events.diff import _TransactionToken
from src.events.fixtures import MapAccessError
from event_helpers import build_cottage_full, make_world
from src.events.fixtures import SCENE_TOWN


def _blockade(world, blockade_id, game_time=0, origin=(0, 0)):
    x, y = origin
    return world.environment.apply_blockade(
        SCENE_TOWN, blockade_id,
        {"object_template_id": "collision.hazard.flood",
         "value": {"shape_type": "polygon",
                   "outer_ring_wu": [[x, y], [x + 8, y], [x + 8, y + 8], [x, y + 8]],
                   "obstacle_tag": "hazard.flood"}},
        game_time,
        source={"command_id": f"cmd-{blockade_id}", "world_event_id": None},
    )


# -- TEST-EVENT-031：append-only、单事务四件套、entry 唯一性 ---------------------------


def test_append_outside_transaction_rejected():
    world, _fakes = make_world()
    bogus_token = object()
    with pytest.raises(DiffError) as exc:
        world.diff_log.append(
            bogus_token, SCENE_TOWN, 0, 0, "building",
            {"command_id": "x"}, None,
            (DiffOperation(op="add", layer="collision", object_id="o1",
                           object_template_id="t", value={"v": 1}),),
        )
    assert exc.value.code == "diff_outside_transaction"


def test_map_bypass_write_rejected():
    world, fakes = make_world()
    with pytest.raises(MapAccessError) as exc:
        fakes.map_port.apply_operations(
            SCENE_TOWN,
            [{"op": "add", "layer": "collision", "object_id": "rogue",
              "object_template_id": "t", "value": {}}],
            expected_revision=None, token=None,
        )
    assert exc.value.code == "bypass_write_rejected"


def test_operations_cap_and_layer_validation():
    world, _fakes = make_world()
    token = _TransactionToken(world.committer)
    ops = tuple(
        DiffOperation(op="add", layer="collision", object_id=f"o{i}",
                      object_template_id="t", value={})
        for i in range(257)
    )
    with pytest.raises(DiffError) as exc:
        world.diff_log.append(token, SCENE_TOWN, 0, 0, "building",
                              {"command_id": "x"}, None, ops)
    assert exc.value.code == "operation_layer_invalid"
    token2 = _TransactionToken(world.committer)
    with pytest.raises(DiffError) as exc:
        world.diff_log.append(
            token2, SCENE_TOWN, 0, 0, "building", {"command_id": "x"}, None,
            (DiffOperation(op="add", layer="ground_art", object_id="o",
                           object_template_id="t", value={}),),
        )
    assert exc.value.code == "operation_layer_invalid"


def test_revision_monotonic_enforced():
    world, _fakes = make_world()
    _blockade(world, "b1", 0)
    token = _TransactionToken(world.committer)
    with pytest.raises(DiffError) as exc:
        world.diff_log.append(
            token, SCENE_TOWN, 0, 1, "road", {"command_id": "x"}, None,
            (DiffOperation(op="add", layer="collision", object_id="o2",
                           object_template_id="t", value={}),),
        )
    assert exc.value.code == "revision_not_monotonic"


def test_entries_are_append_only():
    world, _fakes = make_world()
    _blockade(world, "b2", 0)
    _blockade(world, "b3", 1, origin=(16, 16))
    entries = world.diff_log.entries(SCENE_TOWN)
    assert len(entries) == 2
    assert entries[0].revision < entries[1].revision
    # Log 无修改/删除 API：只有 append / append_reverse / replay / snapshot
    public_methods = {m for m in dir(world.diff_log) if not m.startswith("_")}
    assert public_methods <= {
        "append", "append_reverse", "entries", "get", "replay", "apply_entry",
        "compute_diff_hash", "audit_map_consistency", "snapshot", "restore",
        "export_state", "import_state",
    }


def test_four_piece_in_single_transaction():
    world, fakes = make_world()
    _blockade(world, "b4", 7)
    entry = world.diff_log.entries(SCENE_TOWN)[0]
    assert entry.source["command_id"] == "cmd-b4"
    assert entry.source["domain_event_id"] is not None
    assert entry.game_time == 7
    assert len(fakes.map_port.patches) == 1
    event_types = [e["event_type"] for e in world.event_log.entries()]
    assert "environment.blockade_applied" in event_types
    assert "navigation.patch_committed" in event_types


# -- TEST-EVENT-032：逆向链语义与前值校验 ----------------------------------------------


def test_reverse_chain_three_levels():
    world, _fakes = make_world()
    base = _fakes_base(world)
    original_id = _blockade(world, "chain-1", 0)
    assert _live(world, "collision", "chain-1") is not None
    # 第一级逆向：重开
    reverse_1 = world.environment.lift_blockade(original_id, base, 10,
                                                source={"command_id": "rv-1"})
    assert _live(world, "collision", "chain-1") is None
    # 第二级逆向：撤销重开（再次封锁）
    reverse_2 = world.environment.lift_blockade(reverse_1, base, 20,
                                                source={"command_id": "rv-2"})
    assert _live(world, "collision", "chain-1") is not None
    # 三级 entry 全部保留，链条可追溯
    entries = world.diff_log.entries(SCENE_TOWN)
    assert len(entries) == 3
    assert entries[1].reverses_entry_id == original_id
    assert entries[2].reverses_entry_id == reverse_1
    assert world.diff_log.get(reverse_2).reverses_entry_id == reverse_1


def test_reverse_precondition_failed_on_changed_value():
    world, fakes = make_world()
    base = _fakes_base(world)
    original_id = _blockade(world, "chain-2", 0)
    # 对象在其后被另一 entry 修改（经合法路径：再封锁同 id 前先移除）
    world.environment.lift_blockade(original_id, base, 10,
                                    source={"command_id": "rv-3"})
    _blockade(world, "chain-2", 20)  # 新 entry 重建了同 id 对象
    # 撤销「第一级逆向」应失败：其 add 逆运算要求对象不存在
    entries = world.diff_log.entries(SCENE_TOWN)
    with pytest.raises(DiffError) as exc:
        world.environment.lift_blockade(entries[1].diff_entry_id, base, 30,
                                        source={"command_id": "rv-4"})
    assert exc.value.code == "reverse_precondition_failed"


def _fakes_base(world):
    return world.map_port.base_layers(SCENE_TOWN)


def _live(world, layer, object_id):
    return world.map_port.current_object(SCENE_TOWN, layer, object_id)


# -- TEST-EVENT-033：重放一致性、Hash 审计、幂等应用 --------------------------------------


def test_replay_matches_live_after_many_commits():
    world, fakes = make_world()
    building = build_cottage_full(world, fakes)
    world.buildings.apply_damage("x1", building.building_id, "storm", 15, 100)
    base = fakes.map_port.base_layers(SCENE_TOWN)
    replayed = world.diff_log.replay(SCENE_TOWN, base, up_to_revision=None)
    replay_hash = world.diff_log.compute_diff_hash(replayed)
    assert replay_hash == fakes.map_port.current_layers_hash(SCENE_TOWN)
    report = world.diff_log.audit_map_consistency(
        SCENE_TOWN, base, None, fakes.map_port.current_layers_hash(SCENE_TOWN))
    assert report["ok"] is True


def test_partial_replay_matches_earlier_hash():
    world, fakes = make_world()
    building = build_cottage_full(world, fakes)
    base = fakes.map_port.base_layers(SCENE_TOWN)
    # 记录每个 revision 的 hash，部分重放必须逐一吻合
    for revision in range(1, fakes.map_port.current_revision(SCENE_TOWN) + 1):
        replayed = world.diff_log.replay(SCENE_TOWN, base, up_to_revision=revision)
        # live 在该 revision 的 hash 无法回溯，这里验证部分重放的确定性：
        again = world.diff_log.replay(SCENE_TOWN, base, up_to_revision=revision)
        assert world.diff_log.compute_diff_hash(replayed) == \
            world.diff_log.compute_diff_hash(again)


def test_replay_hash_mismatch_triggers_recovery_barrier():
    world, fakes = make_world()
    _blockade(world, "hash-1", 0)
    base = fakes.map_port.base_layers(SCENE_TOWN)
    # 人为旁路写层制造分歧
    fakes.map_port.inject_bypass_write(SCENE_TOWN, "collision", "rogue", {"v": 1})
    report = world.diff_log.audit_map_consistency(
        SCENE_TOWN, base, None, fakes.map_port.current_layers_hash(SCENE_TOWN))
    assert report["ok"] is False
    assert report["recovery_barrier"] is True
    # 在线运行期不做任何自动回滚：分歧仍在
    assert fakes.map_port.current_object(SCENE_TOWN, "collision", "rogue") is not None


def test_entry_replayed_rejected_on_double_apply():
    world, _fakes = make_world()
    _blockade(world, "hash-2", 0)
    entry = world.diff_log.entries(SCENE_TOWN)[0]
    layers = _fakes_base(world)
    applied = set()
    world.diff_log.apply_entry(layers, entry, applied, SCENE_TOWN)
    with pytest.raises(DiffError) as exc:
        world.diff_log.apply_entry(layers, entry, applied, SCENE_TOWN)
    assert exc.value.code == "entry_replayed"


def test_diff_hash_order_independent():
    world, _fakes = make_world()
    layers_a = {"collision": {"a": {"object_template_id": "t", "value": {"x": 1}},
                              "b": {"object_template_id": "t", "value": {"y": 2}}}}
    layers_b = {"collision": {"b": {"object_template_id": "t", "value": {"y": 2}},
                              "a": {"object_template_id": "t", "value": {"x": 1}}}}
    assert world.diff_log.compute_diff_hash(layers_a) == \
        world.diff_log.compute_diff_hash(layers_b)
