"""
环境实体：火源点、魔力异常、灵体（magic 域 event_port 契约的 owner 实现）

- 端口方法与 magic EFFECT_PORT_CALLS 封闭枚举一一对应：
  flammable_state / ignite / extinguish / purify_anomaly / reinforce_structure / soothe_spirit
- wet 由 region 天气推导（降水类天气 → 湿）
- 封路必须 NavigationPatch（经 MapChangeCommitter）；重开走 Reverse Entry
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from .buildings import BuildingService
from .diff import DiffOperation, MapChangeCommitter


class EnvironmentError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


def point_key(aim_point: dict) -> str:
    return json.dumps(aim_point, sort_keys=True, separators=(",", ":"))


@dataclass
class FlammablePoint:
    scene_id: str
    region_id: str
    aim_point: dict
    building_id: Optional[str] = None
    active_fire_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "scene_id": self.scene_id,
            "region_id": self.region_id,
            "aim_point": copy.deepcopy(self.aim_point),
            "building_id": self.building_id,
            "active_fire_id": self.active_fire_id,
        }

    @staticmethod
    def from_dict(data: dict) -> "FlammablePoint":
        return FlammablePoint(
            scene_id=data["scene_id"],
            region_id=data["region_id"],
            aim_point=copy.deepcopy(data["aim_point"]),
            building_id=data["building_id"],
            active_fire_id=data["active_fire_id"],
        )


@dataclass
class FireSource:
    fire_id: str
    point_key: str
    ignited_game_time: int
    source_event_id: Optional[str]
    damage_per_tick: int = 5
    last_tick_game_time: int = 0

    def to_dict(self) -> dict:
        return dict(self.__dict__)

    @staticmethod
    def from_dict(data: dict) -> "FireSource":
        return FireSource(**data)


@dataclass
class ManaAnomaly:
    scene_id: str
    region_id: str
    aim_point: dict
    purify_threshold: int
    purify_progress: int = 0
    cleared: bool = False

    def to_dict(self) -> dict:
        return dict(self.__dict__)

    @staticmethod
    def from_dict(data: dict) -> "ManaAnomaly":
        return ManaAnomaly(**data)


@dataclass
class Spirit:
    spirit_id: str
    scene_id: str
    source: str
    soothed: bool = False

    def to_dict(self) -> dict:
        return dict(self.__dict__)

    @staticmethod
    def from_dict(data: dict) -> "Spirit":
        return Spirit(**data)


FIRE_TICK_INTERVAL = 60


class EnvironmentService:
    def __init__(
        self,
        buildings: BuildingService,
        committer: MapChangeCommitter,
        event_log: object,
        id_factory: Callable[[], str],
    ) -> None:
        self._buildings = buildings
        self._committer = committer
        self._log = event_log
        self._id_factory = id_factory
        self._flammable: Dict[str, FlammablePoint] = {}
        self._fires: Dict[str, FireSource] = {}
        self._anomalies: Dict[str, ManaAnomaly] = {}
        self._spirits: Dict[str, Spirit] = {}
        #: region → 降水湿标记（WeatherService.is_wet 绑定）
        self.weather_wetness: Callable[[str], bool] = lambda _region: False
        #: 当前游戏时间（world facade 注入；magic 端口契约不传 game_time）
        self.clock: Callable[[], int] = lambda: 0

    # -- 注册 --------------------------------------------------------------

    def register_flammable_point(self, scene_id: str, region_id: str,
                                 aim_point: dict,
                                 building_id: Optional[str] = None) -> str:
        key = point_key(aim_point)
        self._flammable[key] = FlammablePoint(
            scene_id=scene_id, region_id=region_id,
            aim_point=copy.deepcopy(aim_point), building_id=building_id,
        )
        return key

    def register_anomaly(self, scene_id: str, region_id: str, aim_point: dict,
                         purify_threshold: int) -> str:
        key = point_key(aim_point)
        self._anomalies[key] = ManaAnomaly(
            scene_id=scene_id, region_id=region_id,
            aim_point=copy.deepcopy(aim_point), purify_threshold=purify_threshold,
        )
        return key

    def register_spirit(self, spirit_id: str, scene_id: str, source: str) -> None:
        self._spirits[spirit_id] = Spirit(spirit_id=spirit_id, scene_id=scene_id,
                                          source=source)

    def spirit_state(self, spirit_id: str) -> dict:
        spirit = self._spirits.get(spirit_id)
        if spirit is None:
            raise EnvironmentError("spirit_unknown", spirit_id)
        return {"soothed": spirit.soothed}

    # -- magic event_port 契约（EFFECT_PORT_CALLS 封闭枚举） ---------------------

    def flammable_state(self, aim_point: dict) -> dict:
        point = self._flammable.get(point_key(aim_point))
        if point is None:
            return {"registered": False, "active": False, "wet": False}
        return {
            "registered": True,
            "active": point.active_fire_id is not None,
            "wet": self.weather_wetness(point.region_id),
        }

    def ignite(self, aim_point: dict, source_event_id: Optional[str] = None) -> str:
        key = point_key(aim_point)
        point = self._flammable.get(key)
        if point is None:
            raise EnvironmentError("environment_point_unknown", key)
        if point.active_fire_id is not None:
            raise EnvironmentError("fire_already_active", key)
        fire = FireSource(
            fire_id=self._id_factory(), point_key=key,
            ignited_game_time=self.clock(), source_event_id=source_event_id,
        )
        point.active_fire_id = fire.fire_id
        self._fires[fire.fire_id] = fire
        self._log.append(
            "environment.fire_ignited",
            {"fire_id": fire.fire_id, "aim_point": copy.deepcopy(aim_point),
             "source_event_id": source_event_id},
            fire.ignited_game_time,
        )
        return fire.fire_id

    def extinguish(self, aim_point: dict, source_event_id: Optional[str] = None) -> None:
        key = point_key(aim_point)
        point = self._flammable.get(key)
        if point is None or point.active_fire_id is None:
            raise EnvironmentError("fire_not_active", key)
        fire_id = point.active_fire_id
        point.active_fire_id = None
        self._fires.pop(fire_id, None)
        self._log.append(
            "environment.fire_extinguished",
            {"fire_id": fire_id, "source_event_id": source_event_id},
            self.clock(),
        )

    def purify_anomaly(self, aim_point: dict, purify_progress: int,
                       source_event_id: Optional[str] = None) -> None:
        key = point_key(aim_point)
        anomaly = self._anomalies.get(key)
        if anomaly is None or anomaly.cleared:
            raise EnvironmentError("anomaly_unknown", key)
        anomaly.purify_progress += purify_progress
        if anomaly.purify_progress >= anomaly.purify_threshold:
            anomaly.cleared = True
        self._log.append(
            "environment.anomaly_purified",
            {"aim_point": copy.deepcopy(aim_point),
             "progress": anomaly.purify_progress, "cleared": anomaly.cleared,
             "source_event_id": source_event_id},
            self.clock(),
        )

    def reinforce_structure(self, target_ref: str, decay_reduction_bps: int,
                            duration_game_minutes: int,
                            source_event_id: Optional[str] = None) -> None:
        self._buildings.reinforce(
            target_ref, decay_reduction_bps, duration_game_minutes,
            game_time=self.clock(), source_event_id=source_event_id,
        )

    def soothe_spirit(self, target_ref: str,
                      source_event_id: Optional[str] = None) -> None:
        spirit = self._spirits.get(target_ref)
        if spirit is None:
            raise EnvironmentError("spirit_unknown", target_ref)
        spirit.soothed = True
        self._log.append(
            "environment.spirit_soothed",
            {"spirit_id": target_ref, "source_event_id": source_event_id},
            self.clock(),
        )

    # -- 火焰 tick（绑定建筑持续受损） ---------------------------------------------

    def fire_tick(self, game_time: int, command_prefix: str = "fire_tick") -> List[str]:
        """活动火源每 FIRE_TICK_INTERVAL 分钟对绑定建筑造成火焰损毁"""
        damaged: List[str] = []
        for fire in list(self._fires.values()):
            if game_time - fire.last_tick_game_time < FIRE_TICK_INTERVAL:
                continue
            fire.last_tick_game_time = game_time
            point = self._flammable.get(fire.point_key)
            if point is None or point.building_id is None:
                continue
            building = self._buildings.get(point.building_id)
            if building.removed or building.physical_state not in (
                "intact", "lightly_damaged", "severely_damaged"
            ):
                continue
            self._buildings.apply_damage(
                command_id=f"{command_prefix}:{fire.fire_id}:{game_time}",
                building_id=point.building_id,
                source="fire",
                damage_points=fire.damage_per_tick,
                game_time=game_time,
                evidence_id=fire.source_event_id,
            )
            damaged.append(point.building_id)
        return damaged

    # -- 封路/重开（environment_blockade） -------------------------------------------

    def apply_blockade(self, scene_id: str, blockade_id: str, obstacle: dict,
                       game_time: int, source: dict) -> str:
        """环境封锁：必须 NavigationPatch + WorldDiff（diff_kind=environment_blockade）"""
        ops = (DiffOperation(
            op="add", layer="collision", object_id=blockade_id,
            object_template_id=obstacle["object_template_id"],
            value=copy.deepcopy(obstacle["value"]),
        ),)

        def apply() -> None:
            return None

        entry, _event, _ = self._committer.commit(
            scene_id=scene_id, game_time=game_time,
            diff_kind="environment_blockade", source=source, subject_id=blockade_id,
            operations=ops,
            business_apply=apply,
            business_snapshot=lambda: None,
            business_restore=lambda _s: None,
            domain_event_type="environment.blockade_applied",
            domain_event_payload={"scene_id": scene_id, "blockade_id": blockade_id},
        )
        return entry.diff_entry_id

    def lift_blockade(self, blockade_entry_id: str, base_layers: dict,
                      game_time: int, source: dict) -> str:
        """重开：Reverse Entry（携带被撤销 entry 引用）"""
        entry, _event = self._committer.commit_reverse(
            target_entry_id=blockade_entry_id,
            game_time=game_time,
            source=source,
            base_layers=base_layers,
            domain_event_type="environment.blockade_lifted",
            domain_event_payload={"reverses_entry_id": blockade_entry_id},
        )
        return entry.diff_entry_id

    # -- 导出/导入 ------------------------------------------------------------

    def export_state(self) -> dict:
        return {
            "flammable": {k: p.to_dict() for k, p in self._flammable.items()},
            "fires": {k: f.to_dict() for k, f in self._fires.items()},
            "anomalies": {k: a.to_dict() for k, a in self._anomalies.items()},
            "spirits": {k: s.to_dict() for k, s in self._spirits.items()},
        }

    def import_state(self, data: dict) -> None:
        self._flammable = {k: FlammablePoint.from_dict(v) for k, v in data["flammable"].items()}
        self._fires = {k: FireSource.from_dict(v) for k, v in data["fires"].items()}
        self._anomalies = {k: ManaAnomaly.from_dict(v) for k, v in data["anomalies"].items()}
        self._spirits = {k: Spirit.from_dict(v) for k, v in data["spirits"].items()}


class EventMagicPort:
    """
    magic 域 event_port 适配器：只暴露 EFFECT_PORT_CALLS 封闭枚举内的方法，
    签名与 magic/effects.py 调用点逐一对应。
    """

    def __init__(self, environment: EnvironmentService) -> None:
        self._env = environment

    def flammable_state(self, aim_point: dict) -> dict:
        return self._env.flammable_state(aim_point)

    def ignite(self, aim_point: dict, source_event_id: Optional[str] = None) -> str:
        return self._env.ignite(aim_point, source_event_id)

    def extinguish(self, aim_point: dict, source_event_id: Optional[str] = None) -> None:
        return self._env.extinguish(aim_point, source_event_id)

    def purify_anomaly(self, aim_point: dict, purify_progress: int,
                       source_event_id: Optional[str] = None) -> None:
        return self._env.purify_anomaly(aim_point, purify_progress, source_event_id)

    def reinforce_structure(self, target_ref: str, decay_reduction_bps: int,
                            duration_game_minutes: int,
                            source_event_id: Optional[str] = None) -> None:
        return self._env.reinforce_structure(
            target_ref, decay_reduction_bps, duration_game_minutes, source_event_id
        )

    def soothe_spirit(self, target_ref: str,
                      source_event_id: Optional[str] = None) -> None:
        return self._env.soothe_spirit(target_ref, source_event_id)


#: 端口方法封闭枚举（与 magic EFFECT_PORT_CALLS 的 EVENT 侧并集一致）
EVENT_MAGIC_PORT_METHODS = frozenset(
    {"flammable_state", "ignite", "extinguish",
     "purify_anomaly", "reinforce_structure", "soothe_spirit"}
)
