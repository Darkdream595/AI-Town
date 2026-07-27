"""
EVENT 域门面：装配、occurrence 路由、状态导出/导入、不变量审计

- 所有周期工作只经 TIME Scheduled Event（occurrence）入口，禁止逐 Tick 扫描
- export_state/import_state 覆盖全部子系统 + rng + id_counter（崩溃恢复基）
- audit_invariants：预算上限/crisis 并发/生命周期合法性/Diff Hash/Building Binding
"""

from __future__ import annotations

from typing import Callable, Dict, Optional, Tuple

from .budget import NarrativePressureLedger
from .buildings import BuildingService, BuildingTemplateRegistry
from .consequences import AftermathBoard, ConsequenceDispatcher
from .constants import (
    ACTIVE_EVENT_CAP,
    ACTIVE_WEIGHT_CAP,
    CRISIS_CONCURRENCY_CAP,
    EVENT_STATES,
    SEVERITY_WEIGHT,
)
from .construction import ConstructionService
from .diff import MapChangeCommitter, WorldDiffLog
from .director import DirectorReview, WorldSummaryProjectionBuilder
from .engine import EventEngine
from .environment import EnvironmentService, EventMagicPort
from .log import AppendOnlyEventLog
from .placement import ParcelRegistry, PlacementService
from .quests import QuestEngine
from .rng import EventRngHub
from .templates import (
    DirectorWhitelist,
    EventTemplateRegistry,
    QuestTemplateRegistry,
    TriggerRegistry,
)
from .triggers import TriggerEngine
from .weather import TransitionMatrix, WeatherService, default_catalog


class WorldError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


class EventWorld:
    def __init__(
        self,
        world_id: str,
        world_seed_hex: str,
        map_port: object,
        econ_port: object,
        resident_port: object,
        memory_port: object,
        director_model_port: object,
        id_factory: Callable[[], str],
        id_snapshot: Optional[Callable[[], int]] = None,
        id_restore: Optional[Callable[[int], None]] = None,
        game_time_provider: Optional[Callable[[], int]] = None,
    ) -> None:
        self.world_id = world_id
        self._id_factory = id_factory
        self._id_snapshot = id_snapshot
        self._id_restore = id_restore
        self._clock = game_time_provider or (lambda: 0)

        # 基础设施
        self.event_log = AppendOnlyEventLog(world_id, id_factory)
        self.diff_log = WorldDiffLog(id_factory)
        self.committer = MapChangeCommitter(map_port, self.diff_log, self.event_log)
        self.rng_hub = EventRngHub(world_seed_hex)
        self.budget = NarrativePressureLedger()

        # 注册表
        self.event_templates = EventTemplateRegistry()
        self.trigger_registry = TriggerRegistry()
        self.quest_templates = QuestTemplateRegistry()
        self.building_templates = BuildingTemplateRegistry()
        self.parcels = ParcelRegistry()
        self.director_whitelist = DirectorWhitelist()

        # 子系统
        self.engine = EventEngine(
            world_id, self.event_templates, self.budget, self.event_log,
            id_factory, scene_exists=map_port.scene_exists,
        )
        self.triggers = TriggerEngine(
            self.trigger_registry, self.engine, self.budget, self.rng_hub,
            id_factory, self.event_log,
        )
        self.projection_builder = WorldSummaryProjectionBuilder()
        self.director = DirectorReview(
            self.engine, self.event_templates, self.director_whitelist,
            self.budget, director_model_port, self.event_log, id_factory,
        )
        self.aftermath = AftermathBoard(self.event_log, id_factory, self.event_templates)
        self.quests = QuestEngine(
            self.quest_templates, self.event_log, id_factory, econ_port,
            aftermath_registrar=self.aftermath.register,
        )
        self.consequences = ConsequenceDispatcher(
            self.event_templates, self.event_log, econ_port, resident_port, memory_port,
        )
        self.weather_catalog = default_catalog()
        self.weather_matrix = TransitionMatrix(self.weather_catalog)
        self.weather = WeatherService(
            self.weather_catalog, self.weather_matrix, self.rng_hub, self.event_log,
        )
        self.buildings = BuildingService(
            self.building_templates, self.committer, map_port, resident_port,
            econ_port, self.event_log, id_factory,
        )
        self.placement = PlacementService(
            self.parcels, self.buildings, econ_port, map_port, self.event_log, id_factory,
        )
        self.construction = ConstructionService(
            self.buildings, econ_port, resident_port, self.event_log, id_factory,
        )
        self.environment = EnvironmentService(
            self.buildings, self.committer, self.event_log, id_factory,
        )
        self.environment.weather_wetness = self.weather.is_wet
        self.environment.clock = self._clock
        self.magic_port = EventMagicPort(self.environment)

        # 引擎钩子
        self.engine.register_phase_dispatcher(self.consequences.dispatch_phase)
        self.engine.bind_aftermath(self.aftermath.pending_count,
                                   self.aftermath.create_from_event)

        # 端口引用（审计用）
        self.map_port = map_port
        self.econ_port = econ_port
        self.resident_port = resident_port
        self.memory_port = memory_port

    # -- occurrence 路由 --------------------------------------------------

    def on_occurrence(self, occurrence: dict) -> dict:
        kind = occurrence["kind"]
        if kind in ("event_activate", "event_deadline"):
            return self.engine.on_occurrence(occurrence)
        if kind == "trigger_eval":
            projection = occurrence.get("projection")
            if projection is None:
                raise WorldError("occurrence_payload_invalid", "trigger_eval needs projection")
            return self.triggers.evaluate(occurrence, projection,
                                          source=occurrence.get("source", "time"))
        if kind == "director_review":
            projection = occurrence.get("projection")
            if projection is None:
                raise WorldError("occurrence_payload_invalid",
                                 "director_review needs projection")
            return self.director.run_review(occurrence, projection)
        if kind == "weather_eval":
            return self.weather.evaluate(occurrence)
        if kind == "quest_deadline":
            return self.quests.on_deadline(occurrence)
        if kind == "decay_eval":
            return self.buildings.decay_eval(occurrence)
        if kind == "construction_stall_check":
            return self.construction.check_stalled(occurrence)
        if kind == "consequence_retry":
            events_by_id = {e.world_event_id: e for e in self.engine.all()}
            return self.consequences.retry_pending(occurrence, events_by_id)
        raise WorldError("occurrence_kind_unknown", kind)

    # -- 导出/导入 ---------------------------------------------------------

    def export_state(self) -> dict:
        state = {
            "world_id": self.world_id,
            "event_log": self.event_log.export_state(),
            "diff_log": self.diff_log.export_state(),
            "rng": self.rng_hub.snapshot_all(),
            "budget": self.budget.export_state(),
            "engine": self.engine.export_state(),
            "triggers": self.triggers.export_state(),
            "director": self.director.export_state(),
            "director_whitelist": self.director_whitelist.export(),
            "aftermath": self.aftermath.export_state(),
            "quests": self.quests.export_state(),
            "consequences": self.consequences.export_state(),
            "weather": self.weather.export_state(),
            "weather_matrix": self.weather_matrix.export_state(),
            "buildings": self.buildings.export_state(),
            "placement": self.placement.export_state(),
            "construction": self.construction.export_state(),
            "environment": self.environment.export_state(),
        }
        if self._id_snapshot is not None:
            state["id_counter"] = self._id_snapshot()
        return state

    def import_state(self, data: dict) -> None:
        if data.get("world_id") != self.world_id:
            raise WorldError("world_mismatch", f"{data.get('world_id')} != {self.world_id}")
        self.event_log.import_state(data["event_log"])
        self.diff_log.import_state(data["diff_log"])
        self.rng_hub.restore_all(data["rng"])
        self.budget.import_state(data["budget"])
        self.engine.import_state(data["engine"])
        self.triggers.import_state(data["triggers"])
        self.director.import_state(data["director"])
        self.director_whitelist.import_(data["director_whitelist"])
        self.aftermath.import_state(data["aftermath"])
        self.quests.import_state(data["quests"])
        self.consequences.import_state(data["consequences"])
        self.weather.import_state(data["weather"])
        self.weather_matrix.import_state(data["weather_matrix"])
        self.buildings.import_state(data["buildings"])
        self.placement.import_state(data["placement"])
        self.construction.import_state(data["construction"])
        self.environment.import_state(data["environment"])
        if "id_counter" in data and self._id_restore is not None:
            self._id_restore(data["id_counter"])

    # -- 不变量审计 ---------------------------------------------------------

    def audit_invariants(self, game_time: int) -> Dict[str, object]:
        violations = []

        # 预算：active 权重和 ≤ 12、crisis 并发 ≤ 1、active 实例 ≤ 16
        active = self.engine.active_events()
        if len(active) > ACTIVE_EVENT_CAP:
            violations.append(f"active_cap: {len(active)}")
        active_weight = sum(SEVERITY_WEIGHT[e.severity] for e in active)
        if active_weight > ACTIVE_WEIGHT_CAP:
            violations.append(f"weight_cap: {active_weight}")
        if self.budget.active_crisis_count() > CRISIS_CONCURRENCY_CAP:
            violations.append("crisis_concurrency")

        # 生命周期合法性
        for event in self.engine.all():
            if event.state not in EVENT_STATES:
                violations.append(f"event_state: {event.world_event_id}:{event.state}")
            if event.state == "archived" and self.aftermath.pending_count(
                event.world_event_id
            ) > 0:
                violations.append(f"archived_with_pending: {event.world_event_id}")

        # Building Binding 一致性（Physical State × Phase 受约 + 几何 key 锚定）
        for building in self.buildings.all():
            try:
                building.check_invariant()
            except Exception as exc:
                violations.append(f"building_binding: {building.building_id}: {exc}")

        # 每 Scene Diff Hash：重放结果与地图现状一致
        diff_reports = {}
        for scene_id in self.map_port.scene_ids():
            base = self.map_port.base_layers(scene_id)
            replayed = self.diff_log.replay(scene_id, base, up_to_revision=None)
            replay_hash = self.diff_log.compute_diff_hash(replayed)
            live_hash = self.map_port.current_layers_hash(scene_id)
            diff_reports[scene_id] = {"replay": replay_hash, "live": live_hash,
                                      "ok": replay_hash == live_hash}
            if replay_hash != live_hash:
                violations.append(f"diff_hash: {scene_id}")

        return {"ok": not violations, "violations": violations,
                "diff_reports": diff_reports,
                "active_weight": active_weight,
                "active_events": len(active)}
