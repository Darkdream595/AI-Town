"""TEST-EVENT-016..018：天气 Catalog、转移矩阵、投影与环境统计（DOC-EVENT-006）"""

import pytest

from src.events import WeatherError, default_catalog
from src.events.constants import WEATHER_IDS
from src.events.rng import weather_stream_name
from event_helpers import make_world, occ
from src.events.fixtures import SCENE_FOREST, SCENE_TOWN


def _eval(world, key, region_id, season, game_time):
    return world.on_occurrence(occ(
        "weather_eval", key, game_time,
        payload={"region_id": region_id, "season": season},
    ))


# -- TEST-EVENT-016：Catalog 固定 9 项与新 region 初始状态 -------------------------


def test_catalog_fixed_nine_entries():
    catalog = default_catalog()
    assert tuple(catalog.keys()) == WEATHER_IDS
    # 灾害不是天气：Catalog 不含任何灾害条目
    assert not any("disaster" in wid or "fire" in wid or "flood" in wid
                   for wid in catalog)


def test_weather_service_rejects_drifted_catalog():
    world, _fakes = make_world()
    broken = default_catalog()
    broken["firestorm"] = broken["clear"]
    from src.events.weather import WeatherService, TransitionMatrix
    from src.events.rng import EventRngHub
    with pytest.raises(WeatherError) as exc:
        WeatherService(broken, TransitionMatrix(broken),
                       EventRngHub("00" * 16), world.event_log)
    assert exc.value.code == "weather_catalog_drift"


def test_new_region_initial_clear_zero():
    world, _fakes = make_world()
    state = world.weather.register_region("region.new", game_time=0)
    assert state.weather_id == "clear"
    assert state.intensity == 0.0


def test_transition_row_sum_tolerance():
    world, _fakes = make_world()
    with pytest.raises(WeatherError) as exc:
        world.weather_matrix.register_rows(
            "region.x", "spring",
            {"clear": {"clear": 0.5, "cloudy": 0.4}})
    assert exc.value.code == "transition_row_invalid"
    # 容差 1e-9 内放行
    world.weather_matrix.register_rows(
        "region.y", "spring",
        {"clear": {"clear": 0.5, "cloudy": 0.5 + 5e-10}})


def test_unknown_weather_id_in_rows():
    world, _fakes = make_world()
    with pytest.raises(WeatherError) as exc:
        world.weather_matrix.register_rows(
            "region.x", "spring", {"clear": {"firestorm": 1.0}})
    assert exc.value.code == "weather_id_unknown"
    with pytest.raises(WeatherError):
        world.weather_matrix.register_rows(
            "region.x", "spring", {"firestorm": {"clear": 1.0}})


# -- TEST-EVENT-017：矩阵约束、最短持续、确定性抽样 ---------------------------------


def test_mana_anomaly_requires_magic_region():
    world, _fakes = make_world()
    with pytest.raises(WeatherError) as exc:
        world.weather_matrix.register_rows(
            SCENE_TOWN, "spring", {"clear": {"mana_anomaly": 1.0}})
    assert exc.value.code == "anomaly_requires_magic_region"


def test_cold_snap_snow_mutual_exclusion():
    world, _fakes = make_world()
    with pytest.raises(WeatherError) as exc:
        world.weather_matrix.register_rows(
            SCENE_FOREST, "winter", {"snow": {"magical_cold_snap": 1.0}})
    assert exc.value.code == "cold_snap_snow_exclusive"
    with pytest.raises(WeatherError):
        world.weather_matrix.register_rows(
            SCENE_FOREST, "winter", {"magical_cold_snap": {"snow": 1.0}})


def test_min_duration_holds_weather():
    world, _fakes = make_world()
    # clear 最短 60 分钟：30 分钟评估不转移
    result = _eval(world, "w1", SCENE_TOWN, "spring", 30)
    assert result["result"]["status"] == "held"
    assert world.weather.get(SCENE_TOWN).weather_id == "clear"


def test_deterministic_sampling_across_worlds():
    world_a, _ = make_world()
    world_b, _ = make_world()
    results_a, results_b = [], []
    for step in range(20):
        game_time = (step + 1) * 60
        results_a.append(_eval(world_a, f"wa-{step}", SCENE_TOWN, "summer",
                               game_time)["result"])
        results_b.append(_eval(world_b, f"wa-{step}", SCENE_TOWN, "summer",
                               game_time)["result"])
    assert results_a == results_b
    # 20 次评估中至少出现过一次转移（流确实被消耗）
    assert any(r["status"] == "changed" for r in results_a)


def test_stream_naming():
    assert weather_stream_name(SCENE_TOWN) == "event.weather.crown_creek_town"
    assert weather_stream_name(SCENE_FOREST) == "event.weather.twilight_whisper_forest"


def test_evaluation_idempotent_by_occurrence_key():
    world, _fakes = make_world()
    first = _eval(world, "w2", SCENE_TOWN, "spring", 60)
    stats_after_first = dict(world.weather.get(SCENE_TOWN).environment_stats)
    second = _eval(world, "w2", SCENE_TOWN, "spring", 60)
    assert first["status"] == "processed"
    assert second["status"] == "replayed"
    # 重放不重复累积环境统计
    assert world.weather.get(SCENE_TOWN).environment_stats == stats_after_first


# -- TEST-EVENT-018：投影白名单、环境统计、wet 推导 ----------------------------------


def test_projection_only_whitelisted_fields():
    world, _fakes = make_world()
    projection = world.weather.projection(SCENE_TOWN, 42)
    assert set(projection) == {"weather_id", "intensity", "revision", "game_time"}
    assert projection["game_time"] == 42


def test_environment_stats_accumulate_per_hour():
    world, _fakes = make_world()
    # 强制当前天气为 rain.light（soil_moisture +1.0/h）
    state = world.weather.get(SCENE_TOWN)
    state.weather_id = "rain.light"
    state.intensity = 0.3
    state.since_game_time = 0
    _eval(world, "w3", SCENE_TOWN, "spring", 60)   # 1 小时
    assert world.weather.get(SCENE_TOWN).environment_stats["soil_moisture"] == 1.0
    _eval(world, "w4", SCENE_TOWN, "spring", 180)  # 再 2 小时
    assert world.weather.get(SCENE_TOWN).environment_stats["soil_moisture"] >= 2.0


def test_version_increments_on_change():
    world, _fakes = make_world()
    state = world.weather.get(SCENE_TOWN)
    initial_version = state.version
    for step in range(30):
        _eval(world, f"w5-{step}", SCENE_TOWN, "autumn", (step + 1) * 60)
        if state.version > initial_version:
            break
    assert state.version > initial_version
    projection = world.weather.projection(SCENE_TOWN, 9999)
    assert projection["revision"] == state.version


def test_wet_derivation_for_fire_points():
    world, _fakes = make_world()
    assert world.weather.is_wet(SCENE_TOWN) is False
    state = world.weather.get(SCENE_TOWN)
    state.weather_id = "rain.heavy"
    assert world.weather.is_wet(SCENE_TOWN) is True
    # environment 服务经 weather_wetness 绑定取到同一推导
    world.environment.register_flammable_point(
        SCENE_TOWN, SCENE_TOWN, {"x": 1, "y": 1})
    assert world.magic_port.flammable_state({"x": 1, "y": 1})["wet"] is True
    state.weather_id = "clear"
    assert world.magic_port.flammable_state({"x": 1, "y": 1})["wet"] is False
