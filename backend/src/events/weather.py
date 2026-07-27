"""
天气系统（DOC-EVENT-006）

- Catalog 固定 9 项；室外 region 独立状态 (weather_id, intensity, since, environment_stats)
- 转移矩阵按 (region, season)，行和 = 1（容差 1e-9）
- mana_anomaly 只能由魔法条件行进入；magical_cold_snap 与 snow 不直接互转
- 评估 interval 30 分钟；抽样流 `event.weather.<region 末段>`
- 灾害不是天气：Catalog 不含灾害，灾害只经触发器
- projection 只含 weather_id/intensity/revision/game_time
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from .constants import (
    PRECIPITATION_WEATHERS,
    SEASONS,
    TRANSITION_ROW_TOLERANCE,
    WEATHER_IDS,
)
from .rng import EventRngHub


class WeatherError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True)
class WeatherCatalogEntry:
    weather_id: str
    allowed_intensity: Tuple[float, float]
    min_duration_game_minutes: int
    modifiers: dict = field(default_factory=dict)
    #: environment stat → 每 game hour 增量
    environment_effects: dict = field(default_factory=dict)
    is_anomaly: bool = False


def default_catalog() -> Dict[str, WeatherCatalogEntry]:
    """固定 9 项 Catalog；灾害不在其中"""
    return {
        "clear": WeatherCatalogEntry("clear", (0.0, 0.2), 60),
        "cloudy": WeatherCatalogEntry("cloudy", (0.1, 0.6), 60),
        "rain.light": WeatherCatalogEntry(
            "rain.light", (0.2, 0.5), 30,
            environment_effects={"soil_moisture": 1.0},
        ),
        "rain.heavy": WeatherCatalogEntry(
            "rain.heavy", (0.5, 0.9), 30,
            environment_effects={"soil_moisture": 3.0},
        ),
        "fog": WeatherCatalogEntry("fog", (0.2, 0.8), 60, modifiers={"visibility": -2}),
        "thunderstorm": WeatherCatalogEntry(
            "thunderstorm", (0.6, 1.0), 30,
            modifiers={"visibility": -3},
            environment_effects={"soil_moisture": 4.0},
        ),
        "snow": WeatherCatalogEntry(
            "snow", (0.3, 0.9), 120,
            modifiers={"temperature": -10},
            environment_effects={"snow_cover": 2.0},
        ),
        "magical_cold_snap": WeatherCatalogEntry(
            "magical_cold_snap", (0.4, 1.0), 120,
            modifiers={"temperature": -20, "mana": -1},
        ),
        "mana_anomaly": WeatherCatalogEntry(
            "mana_anomaly", (0.3, 1.0), 60,
            modifiers={"mana": 3},
            environment_effects={"anomaly_charge": 1.0},
            is_anomaly=True,
        ),
    }


class TransitionMatrix:
    """按 (region, season) 注册的转移权重表"""

    def __init__(self, catalog: Dict[str, WeatherCatalogEntry]) -> None:
        self._catalog = catalog
        self._rows: Dict[Tuple[str, str], Dict[str, Dict[str, float]]] = {}
        self._magic_regions: set = set()

    def mark_magic_region(self, region_id: str) -> None:
        self._magic_regions.add(region_id)

    def register_rows(self, region_id: str, season: str,
                      rows: Dict[str, Dict[str, float]]) -> None:
        if season not in SEASONS:
            raise WeatherError("season_invalid", season)
        magic_region = region_id in self._magic_regions
        for from_id, targets in rows.items():
            if from_id not in self._catalog:
                raise WeatherError("weather_id_unknown", from_id)
            total = 0.0
            for to_id, weight in targets.items():
                if to_id not in self._catalog:
                    raise WeatherError("weather_id_unknown", to_id)
                if weight < 0:
                    raise WeatherError("transition_weight_invalid", f"{from_id}→{to_id}")
                # mana_anomaly 只能由魔法条件行进入
                if to_id == "mana_anomaly" and not magic_region:
                    raise WeatherError("anomaly_requires_magic_region", region_id)
                # magical_cold_snap 与 snow 互斥：不允许直接互转
                pair = {from_id, to_id}
                if pair == {"magical_cold_snap", "snow"}:
                    raise WeatherError("cold_snap_snow_exclusive", f"{from_id}→{to_id}")
                total += weight
            if abs(total - 1.0) > TRANSITION_ROW_TOLERANCE:
                raise WeatherError(
                    "transition_row_invalid", f"{region_id}/{season}/{from_id}: sum {total}"
                )
        self._rows[(region_id, season)] = copy.deepcopy(rows)

    def row(self, region_id: str, season: str, from_id: str) -> Dict[str, float]:
        rows = self._rows.get((region_id, season))
        if rows is None or from_id not in rows:
            raise WeatherError("transition_row_missing", f"{region_id}/{season}/{from_id}")
        return rows[from_id]

    def export_state(self) -> dict:
        return {
            "rows": {f"{r}|{s}": rows for (r, s), rows in self._rows.items()},
            "magic_regions": sorted(self._magic_regions),
        }

    def import_state(self, data: dict) -> None:
        self._rows = {}
        for key, rows in data["rows"].items():
            region_id, season = key.split("|", 1)
            self._rows[(region_id, season)] = rows
        self._magic_regions = set(data["magic_regions"])


@dataclass
class RegionWeatherState:
    region_id: str
    weather_id: str = "clear"
    intensity: float = 0.0
    since_game_time: int = 0
    last_eval_game_time: int = 0
    environment_stats: Dict[str, float] = field(default_factory=dict)
    version: int = 0

    def to_dict(self) -> dict:
        return {
            "region_id": self.region_id,
            "weather_id": self.weather_id,
            "intensity": self.intensity,
            "since_game_time": self.since_game_time,
            "last_eval_game_time": self.last_eval_game_time,
            "environment_stats": dict(self.environment_stats),
            "version": self.version,
        }

    @staticmethod
    def from_dict(data: dict) -> "RegionWeatherState":
        return RegionWeatherState(
            region_id=data["region_id"],
            weather_id=data["weather_id"],
            intensity=data["intensity"],
            since_game_time=data["since_game_time"],
            last_eval_game_time=data["last_eval_game_time"],
            environment_stats=dict(data["environment_stats"]),
            version=data["version"],
        )


class WeatherService:
    def __init__(
        self,
        catalog: Dict[str, WeatherCatalogEntry],
        matrix: TransitionMatrix,
        rng_hub: EventRngHub,
        event_log: object,
    ) -> None:
        if set(catalog) != set(WEATHER_IDS):
            raise WeatherError("weather_catalog_drift", "catalog must be the fixed 9 entries")
        self._catalog = catalog
        self._matrix = matrix
        self._rng = rng_hub
        self._log = event_log
        self._regions: Dict[str, RegionWeatherState] = {}
        self._evaluations: Dict[str, dict] = {}

    # -- region 管理 ---------------------------------------------------------

    def register_region(self, region_id: str, game_time: int = 0) -> RegionWeatherState:
        """新 region 初始 clear 强度 0"""
        if region_id in self._regions:
            return self._regions[region_id]
        state = RegionWeatherState(region_id=region_id, since_game_time=game_time,
                                   last_eval_game_time=game_time)
        self._regions[region_id] = state
        return state

    def get(self, region_id: str) -> RegionWeatherState:
        try:
            return self._regions[region_id]
        except KeyError:
            raise WeatherError("region_unknown", region_id) from None

    def is_wet(self, region_id: str) -> bool:
        """降水类天气 → 火源点 wet"""
        return self.get(region_id).weather_id in PRECIPITATION_WEATHERS

    def projection(self, region_id: str, game_time: int) -> dict:
        """projection 只含 weather_id/intensity/revision/game_time"""
        state = self.get(region_id)
        return {
            "weather_id": state.weather_id,
            "intensity": state.intensity,
            "revision": state.version,
            "game_time": game_time,
        }

    # -- 周期评估 -------------------------------------------------------------

    def evaluate(self, occurrence: dict) -> dict:
        """
        occurrence: {occurrence_key, kind=weather_eval, game_time,
                     payload{region_id, season}}
        幂等：同 occurrence_key 重放返回首次结果
        """
        key = occurrence["occurrence_key"]
        if key in self._evaluations:
            return {"status": "replayed", "result": self._evaluations[key]}
        game_time = occurrence["game_time"]
        payload = occurrence["payload"]
        region_id = payload["region_id"]
        season = payload["season"]
        state = self.get(region_id)

        # 环境效果按经过的 game hour 累积（无论是否转移）
        elapsed_hours = (game_time - state.last_eval_game_time) / 60.0
        if elapsed_hours > 0:
            effects = self._catalog[state.weather_id].environment_effects
            for stat, delta in effects.items():
                state.environment_stats[stat] = round(
                    state.environment_stats.get(stat, 0.0) + delta * elapsed_hours, 6
                )
        state.last_eval_game_time = game_time

        entry = self._catalog[state.weather_id]
        result: dict
        if game_time - state.since_game_time < entry.min_duration_game_minutes:
            result = {"status": "held", "weather_id": state.weather_id}
        else:
            row = self._matrix.row(region_id, season, state.weather_id)
            stream = self._rng.weather_stream(region_id)
            pick = stream.draw_probability_millionths() / 1_000_000.0
            target = state.weather_id
            cumulative = 0.0
            for to_id in sorted(row):
                cumulative += row[to_id]
                if pick < cumulative:
                    target = to_id
                    break
            if target != state.weather_id:
                target_entry = self._catalog[target]
                low, high = target_entry.allowed_intensity
                intensity_draw = stream.draw_probability_millionths() / 1_000_000.0
                intensity = round(low + (high - low) * intensity_draw, 6)
                previous = state.weather_id
                state.weather_id = target
                state.intensity = intensity
                state.since_game_time = game_time
                state.version += 1
                self._log.append(
                    "weather.changed",
                    {"region_id": region_id, "from": previous, "to": target,
                     "intensity": intensity, "season": season},
                    game_time,
                )
                result = {"status": "changed", "from": previous, "to": target,
                          "intensity": intensity}
            else:
                result = {"status": "held", "weather_id": state.weather_id}
        self._evaluations[key] = result
        return {"status": "processed", "result": result}

    # -- 导出/导入 ------------------------------------------------------------

    def export_state(self) -> dict:
        return {
            "regions": {rid: s.to_dict() for rid, s in self._regions.items()},
            "evaluations": copy.deepcopy(self._evaluations),
        }

    def import_state(self, data: dict) -> None:
        self._regions = {
            rid: RegionWeatherState.from_dict(s) for rid, s in data["regions"].items()
        }
        self._evaluations = copy.deepcopy(data["evaluations"])
