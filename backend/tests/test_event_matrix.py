"""覆盖矩阵审计 + magic event_port 契约（DOC-EVENT-012 §11 / REQ-MAGIC-024）

- RULE-EVENT-001..072 → TEST-EVENT-001..040 零缺口，且引用的测试真实存在
- magic 侧 EFFECT_PORT_CALLS 的 EVENT handler 方法并集 ⊆ EVENT_MAGIC_PORT_METHODS
- 端口行为：未注册点 / 天气湿标记 / 点火熄灭 / 净化阈值 / 加固写入 / 灵体安抚
"""

import re
from pathlib import Path

import pytest

from src.events.environment import EVENT_MAGIC_PORT_METHODS, EnvironmentError
from src.events.fixtures import TEST_COVERAGE_MATRIX, SCENE_TOWN, audit_coverage
from src.magic.balance import EFFECT_PORT_CALLS

from event_helpers import build_cottage_full, make_world

#: magic 侧 EFFECT_PORT_CALLS 中 owner 为 EVENT 域的 handler
EVENT_SIDE_EFFECTS = (
    "magic.effect.ignite",
    "magic.effect.extinguish",
    "magic.effect.purify_anomaly",
    "magic.effect.reinforce_structure",
    "magic.effect.soothe_spirit",
)


# -- 覆盖矩阵 ---------------------------------------------------------------

def test_rule_coverage_zero_gap():
    """RULE-EVENT-001..072 → 测试映射零缺口"""
    assert audit_coverage() == []


def test_every_referenced_test_id_exists():
    """矩阵引用的 TEST-EVENT-001..040 在测试套件源码中真实存在"""
    suite_dir = Path(__file__).resolve().parent
    corpus = ""
    for path in suite_dir.glob("test_event_*.py"):
        corpus += path.read_text(encoding="utf-8")
    present = set(re.findall(r"TEST-EVENT-\d{3}", corpus))
    referenced = {test_id for ids in TEST_COVERAGE_MATRIX.values() for test_id in ids}
    missing = referenced - present
    assert not missing, f"matrix references without tests: {sorted(missing)}"
    assert present >= {f"TEST-EVENT-{index:03d}" for index in range(1, 41)}


# -- magic event_port 封闭枚举契约 ----------------------------------------------

def test_magic_event_port_contract_closed_enum():
    """EVENT handler 端口方法并集 == EVENT_MAGIC_PORT_METHODS，且全部可调"""
    union = set()
    for effect_id in EVENT_SIDE_EFFECTS:
        union |= set(EFFECT_PORT_CALLS[effect_id])
    assert union == set(EVENT_MAGIC_PORT_METHODS)
    world, _fakes = make_world()
    for method in sorted(EVENT_MAGIC_PORT_METHODS):
        assert callable(getattr(world.magic_port, method))


# -- 端口行为 ---------------------------------------------------------------

def test_magic_port_flammable_state_and_fire_cycle():
    world, _fakes = make_world()
    aim = {"scene_id": SCENE_TOWN, "x": 1, "y": 1}
    # 未注册点
    assert world.magic_port.flammable_state(aim) == {
        "registered": False, "active": False, "wet": False}
    # 注册后 dry；降水天气 → wet（绑定同一推导）
    world.environment.register_flammable_point(SCENE_TOWN, SCENE_TOWN, aim)
    assert world.magic_port.flammable_state(aim)["registered"] is True
    assert world.magic_port.flammable_state(aim)["wet"] is False
    world.weather.get(SCENE_TOWN).weather_id = "rain.heavy"
    assert world.magic_port.flammable_state(aim)["wet"] is True
    world.weather.get(SCENE_TOWN).weather_id = "clear"
    # 点燃 / 熄灭
    world.magic_port.ignite(aim, "ev.spark.1")
    assert world.magic_port.flammable_state(aim)["active"] is True
    world.magic_port.extinguish(aim, "ev.spark.1")
    assert world.magic_port.flammable_state(aim)["active"] is False
    # 未点燃时熄灭 → 拒绝
    with pytest.raises(EnvironmentError) as excinfo:
        world.magic_port.extinguish(aim)
    assert excinfo.value.code == "fire_not_active"


def test_magic_port_purify_anomaly_to_threshold():
    world, _fakes = make_world()
    aim = {"scene_id": SCENE_TOWN, "x": 9, "y": 9}
    world.environment.register_anomaly(SCENE_TOWN, SCENE_TOWN, aim, purify_threshold=10)
    world.magic_port.purify_anomaly(aim, 4, "ev.purify.1")
    anomaly = world.environment.export_state()["anomalies"][
        next(iter(world.environment.export_state()["anomalies"]))]
    assert anomaly["purify_progress"] == 4 and anomaly["cleared"] is False
    world.magic_port.purify_anomaly(aim, 6, "ev.purify.2")
    anomaly = world.environment.export_state()["anomalies"][
        next(iter(world.environment.export_state()["anomalies"]))]
    assert anomaly["purify_progress"] == 10 and anomaly["cleared"] is True
    # 已清除 / 未注册 → anomaly_unknown
    with pytest.raises(EnvironmentError) as excinfo:
        world.magic_port.purify_anomaly(aim, 1)
    assert excinfo.value.code == "anomaly_unknown"
    with pytest.raises(EnvironmentError) as excinfo:
        world.magic_port.purify_anomaly({"scene_id": SCENE_TOWN, "x": 0, "y": 0}, 1)
    assert excinfo.value.code == "anomaly_unknown"


def test_magic_port_reinforce_structure_writes_building():
    world, fakes = make_world()
    building = build_cottage_full(world, fakes, command_id="mx-place")
    world.magic_port.reinforce_structure(building.building_id, 5000, 1440, "ev.ward.1")
    reinforced = world.buildings.get(building.building_id)
    assert reinforced.reinforcement == {"bps": 5000, "until": 1440}


def test_magic_port_soothe_spirit():
    world, _fakes = make_world()
    world.environment.register_spirit("spirit.1", SCENE_TOWN, source="event")
    world.magic_port.soothe_spirit("spirit.1", "ev.soothe.1")
    assert world.environment.spirit_state("spirit.1") == {"soothed": True}
    with pytest.raises(EnvironmentError) as excinfo:
        world.magic_port.soothe_spirit("spirit.ghost")
    assert excinfo.value.code == "spirit_unknown"
