"""
测试夹具与标准内容（DOC-EVENT-012）

- Fake 端口：MAP / ECON / RESIDENT / MEMORY / DirectorModel，全部 recording
- FakeMapPort 强制令牌：旁路写层（无 token）直接拒绝——架构违规探针
- Scenario Fixture 注册表：固定 Seed、固定命令脚本、预期时间线、Oracle
- TEST_COVERAGE_MATRIX：RULE-EVENT-001..072 → TEST-EVENT-001..040
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from .buildings import BuildingTemplate, RelocationFailed
from .consequences import OwnerUnavailable, PortRejected
from .diff import WorldDiffLog
from .placement import Parcel
from .templates import (
    AftermathTaskSpec,
    ConsequenceSpec,
    EventTemplate,
    ObjectiveSpec,
    QuestTemplate,
    RewardSpec,
    TriggerSpec,
)
from .world import EventWorld


# ---------------------------------------------------------------------------
# 确定性 ID
# ---------------------------------------------------------------------------


class DeterministicIdFactory:
    """确定性 ID：字典序与生成序一致；可快照/恢复"""

    def __init__(self) -> None:
        self.counter = 0

    def __call__(self) -> str:
        self.counter += 1
        return f"{self.counter:026d}"

    def snapshot(self) -> int:
        return self.counter

    def restore(self, value: int) -> None:
        self.counter = value


def make_id_factory() -> DeterministicIdFactory:
    return DeterministicIdFactory()


# ---------------------------------------------------------------------------
# Fake MAP 端口（NavigationPatch 接收方 + 规则层真相源）
# ---------------------------------------------------------------------------


class MapAccessError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


class FakeMapPort:
    """
    规则层真相源：apply_operations 必须出示 MapChangeCommitter 铸造的令牌；
    live layers 与 WorldDiff 重放同构（hash 必然一致，除非有人旁路写层）。
    """

    def __init__(self) -> None:
        self._scenes: Dict[str, dict] = {}
        self.patches: List[dict] = []
        self.entrance_walkable_hook: Callable[[str, dict], bool] = lambda _s, _f: True
        self.critical_routes_hook: Callable[[str, list], bool] = lambda _s, _ops: True

    def register_scene(self, scene_id: str, base_layers: Optional[dict] = None) -> None:
        layers = {layer: {} for layer in ("structure", "walkability", "collision", "semantic")}
        if base_layers:
            for layer, objects in base_layers.items():
                layers[layer] = copy.deepcopy(objects)
        self._scenes[scene_id] = {
            "base_layers": copy.deepcopy(layers),
            "layers": layers,
            "revision": 0,
            "base_package_version": "map.pkg.v1",
        }

    # -- 查询 ----------------------------------------------------------------

    def scene_exists(self, scene_id: str) -> bool:
        return scene_id in self._scenes

    def scene_ids(self) -> List[str]:
        return sorted(self._scenes)

    def base_layers(self, scene_id: str) -> dict:
        return copy.deepcopy(self._scenes[scene_id]["base_layers"])

    def current_revision(self, scene_id: str) -> int:
        return self._scenes[scene_id]["revision"]

    def current_object(self, scene_id: str, layer: str, object_id: str) -> Optional[dict]:
        obj = self._scenes[scene_id]["layers"].get(layer, {}).get(object_id)
        return copy.deepcopy(obj) if obj else None

    def current_layers_hash(self, scene_id: str) -> str:
        return WorldDiffLog.compute_diff_hash(self._scenes[scene_id]["layers"])

    def entrance_walkable(self, scene_id: str, footprint: dict) -> bool:
        return self.entrance_walkable_hook(scene_id, footprint)

    def critical_routes_intact(self, scene_id: str, candidate_ops: list) -> bool:
        return self.critical_routes_hook(scene_id, candidate_ops)

    # -- 写入（必须持令牌） ------------------------------------------------------

    def apply_operations(self, scene_id: str, operations: list,
                         expected_revision: Optional[int] = None,
                         token: object = None) -> int:
        from .diff import _TransactionToken  # 延迟导入避免循环

        if not isinstance(token, _TransactionToken) or token._sealed:
            # 旁路写层 = 架构违规（RULE-EVENT-062 探针）
            raise MapAccessError("bypass_write_rejected", scene_id)
        scene = self._scenes[scene_id]
        if expected_revision is not None and scene["revision"] != expected_revision:
            raise MapAccessError(
                "stale_revision", f"{scene['revision']} != {expected_revision}"
            )
        for op in operations:
            layer = scene["layers"].setdefault(op["layer"], {})
            if op["op"] in ("add", "replace"):
                layer[op["object_id"]] = {
                    "object_template_id": op["object_template_id"],
                    "value": copy.deepcopy(op["value"]),
                }
            else:
                layer.pop(op["object_id"], None)
        scene["revision"] += 1
        self.patches.append({
            "scene_id": scene_id,
            "revision": scene["revision"],
            "operations": copy.deepcopy(operations),
        })
        return scene["revision"]

    # -- 事务快照 ------------------------------------------------------------

    def snapshot_state(self) -> dict:
        return copy.deepcopy(self._scenes)

    def restore_state(self, snapshot: dict) -> None:
        self._scenes = copy.deepcopy(snapshot)

    def inject_bypass_write(self, scene_id: str, layer: str, object_id: str,
                            value: dict) -> None:
        """测试专用：绕过令牌直写规则层，制造 hash 分歧（Recovery Barrier 探针）"""
        self._scenes[scene_id]["layers"].setdefault(layer, {})[object_id] = {
            "object_template_id": "test.bypass", "value": copy.deepcopy(value),
        }


# ---------------------------------------------------------------------------
# Fake ECON 端口
# ---------------------------------------------------------------------------


class FakeEconPort:
    def __init__(self) -> None:
        self.build_rights: set = set()
        self.rewards: List[dict] = []
        self.region_modifiers: Dict[str, dict] = {}
        self.salvage_escrows: Dict[str, dict] = {}
        self.material_deliveries: List[dict] = []
        self.material_consumptions: List[dict] = []
        self.build_budgets: List[dict] = []
        self.fail_reward: bool = False

    def grant_build_right(self, resident_id: str, parcel_id: str) -> None:
        self.build_rights.add((resident_id, parcel_id))

    def has_build_right(self, resident_id: str, parcel_id: str) -> bool:
        return (resident_id, parcel_id) in self.build_rights

    def grant_reward(self, resident_id: str, reward_kind: str,
                     parameters: dict, evidence_id: Optional[str] = None) -> None:
        if self.fail_reward:
            raise PortRejected("econ_reward_rejected", resident_id)
        self.rewards.append({
            "resident_id": resident_id, "reward_kind": reward_kind,
            "parameters": copy.deepcopy(parameters), "evidence_id": evidence_id,
        })

    def register_region_modifier(self, modifier_id: str, region_id: str,
                                 modifier: dict, evidence_id: Optional[str] = None) -> None:
        # 稳定 ID：重复注册同 ID 只保留首个（幂等）
        self.region_modifiers.setdefault(modifier_id, {
            "region_id": region_id, "modifier": copy.deepcopy(modifier),
            "evidence_id": evidence_id,
        })

    def escrow_salvage(self, pool_id: str, resources: dict,
                       evidence_id: Optional[str] = None) -> None:
        self.salvage_escrows[pool_id] = {
            "resources": copy.deepcopy(resources),
            "claimed_by": None, "evidence_id": evidence_id,
        }

    def claim_salvage(self, pool_id: str, claimer_id: str) -> None:
        pool = self.salvage_escrows.get(pool_id)
        if pool is None:
            raise PortRejected("salvage_pool_unknown", pool_id)
        if pool["claimed_by"] is not None:
            raise PortRejected("salvage_already_claimed", pool_id)
        pool["claimed_by"] = claimer_id

    def release_escrow(self, pool_id: str) -> None:
        self.salvage_escrows.pop(pool_id, None)

    def settle_material_delivery(self, site_id: str, materials: dict,
                                 evidence_id: Optional[str] = None) -> None:
        self.material_deliveries.append({
            "site_id": site_id, "materials": copy.deepcopy(materials),
            "evidence_id": evidence_id,
        })

    def consume_materials(self, consumer_id: str, materials: dict,
                          evidence_id: Optional[str] = None) -> None:
        self.material_consumptions.append({
            "consumer_id": consumer_id, "materials": copy.deepcopy(materials),
            "evidence_id": evidence_id,
        })

    def settle_build_budget(self, budget_source: str, building_id: str,
                            cost: int, evidence_id: Optional[str] = None) -> None:
        self.build_budgets.append({
            "budget_source": budget_source, "building_id": building_id,
            "cost": cost, "evidence_id": evidence_id,
        })


# ---------------------------------------------------------------------------
# Fake RESIDENT 端口
# ---------------------------------------------------------------------------


class FakeResidentPort:
    def __init__(self) -> None:
        self.notifications: List[dict] = []
        self.relocations: List[dict] = []
        self.fail_relocation: bool = False
        self.unavailable: bool = False

    def notify(self, resident_id: str, kind: str, content: dict,
               evidence_id: Optional[str] = None) -> None:
        if self.unavailable:
            raise OwnerUnavailable("resident port unavailable")
        self.notifications.append({
            "resident_id": resident_id, "kind": kind,
            "content": copy.deepcopy(content), "evidence_id": evidence_id,
        })

    def relocate_occupants(self, building_id: str, occupant_ids: List[str],
                           game_time: int) -> None:
        if self.fail_relocation:
            raise RelocationFailed(building_id)
        self.relocations.append({
            "building_id": building_id, "occupant_ids": list(occupant_ids),
            "game_time": game_time,
        })


# ---------------------------------------------------------------------------
# Fake MEMORY 端口（认知分发；绝不注入 Secret）
# ---------------------------------------------------------------------------


class FakeMemoryPort:
    def __init__(self) -> None:
        self.distributions: List[dict] = []

    def distribute(self, publicity: str, audience: dict, content: dict,
                   evidence_id: Optional[str] = None) -> None:
        blob = json.dumps(content, ensure_ascii=False).lower()
        if "secret" in blob:
            raise PortRejected("memory_secret_forbidden", "content contains secret")
        self.distributions.append({
            "publicity": publicity, "audience": copy.deepcopy(audience),
            "content": copy.deepcopy(content), "evidence_id": evidence_id,
        })


# ---------------------------------------------------------------------------
# Fake Director 模型（FakeProvider 固定工件）
# ---------------------------------------------------------------------------


class FakeDirectorModel:
    def __init__(self) -> None:
        self.queue: List[object] = []
        self.calls: List[dict] = []
        self.unavailable: bool = False

    def push(self, response: object) -> None:
        self.queue.append(response)

    def complete(self, prompt_id: str, model: str, thinking: bool,
                 reasoning_effort: str, projection: dict) -> object:
        self.calls.append({
            "prompt_id": prompt_id, "model": model, "thinking": thinking,
            "reasoning_effort": reasoning_effort,
            "projection": copy.deepcopy(projection),
        })
        if self.unavailable:
            raise RuntimeError("model unavailable")
        if not self.queue:
            return None
        return self.queue.pop(0)


# ---------------------------------------------------------------------------
# 标准内容
# ---------------------------------------------------------------------------

SCENE_TOWN = "region.crown_creek_town"
SCENE_FOREST = "region.twilight_whisper_forest"


def standard_event_templates() -> List[EventTemplate]:
    return [
        EventTemplate(
            event_template_id="event.festival.harvest",
            name="丰收节",
            default_severity="minor",
            allowed_sources=frozenset({"time", "state", "director", "admin"}),
            max_concurrent_instances=2,
            dedup_window_game_minutes=1440,
            parameter_fields=frozenset({"theme"}),
            consequence_plan=(
                ConsequenceSpec(
                    consequence_id="festival_mood",
                    phase="on_active",
                    target_domain="econ",
                    port="register_region_modifier",
                    parameters={"region_id": SCENE_TOWN,
                                "modifier": {"happiness": 1}},
                ),
                ConsequenceSpec(
                    consequence_id="festival_news",
                    phase="on_active",
                    target_domain="memory",
                    port="distribute",
                    parameters={"content": {"fact": "harvest festival started"}},
                    publicity="public",
                ),
            ),
        ),
        EventTemplate(
            event_template_id="event.disaster.forest_fire",
            name="森林火灾",
            default_severity="major",
            allowed_sources=frozenset({"state", "environment", "director", "admin"}),
            max_concurrent_instances=1,
            dedup_window_game_minutes=4320,
            is_disaster=True,
            parameter_fields=frozenset({"origin"}),
            required_parameters=frozenset({"origin"}),
            consequence_plan=(
                ConsequenceSpec(
                    consequence_id="fire_alert",
                    phase="on_active",
                    target_domain="resident",
                    port="notify",
                    parameters={"resident_id": "resident.mayor",
                                "content": {"alert": "forest fire"}},
                ),
            ),
            aftermath_plan=(
                AftermathTaskSpec("compensation", {"fund": "disaster_relief"}),
                AftermathTaskSpec("reconstruction", {"area": "forest_edge"}),
            ),
        ),
        EventTemplate(
            event_template_id="event.crisis.dragon",
            name="巨龙来袭",
            default_severity="crisis",
            allowed_sources=frozenset({"director", "admin"}),
            max_concurrent_instances=1,
            dedup_window_game_minutes=10080,
            is_disaster=True,
            parameter_fields=frozenset(),
        ),
        EventTemplate(
            event_template_id="event.minor.rumor",
            name="流言",
            default_severity="minor",
            allowed_sources=frozenset({"state", "resident", "director"}),
            max_concurrent_instances=8,
            dedup_window_game_minutes=60,
        ),
        EventTemplate(
            event_template_id="event.weird.lights",
            name="异光",
            default_severity="moderate",
            allowed_sources=frozenset({"environment", "director", "admin"}),
            max_concurrent_instances=2,
            dedup_window_game_minutes=720,
        ),
    ]


def standard_triggers() -> List[TriggerSpec]:
    return [
        TriggerSpec(
            trigger_id="trigger.harvest_season",
            event_template_id="event.festival.harvest",
            allowed_sources=frozenset({"time"}),
            severity="minor",
            trigger_priority=1,
            condition={"all_of": [["projection_at_least", "public.harvest_stock", 100]]},
            activation_chance_0_to_1=1.0,
            cooldown_game_minutes=1440,
        ),
        TriggerSpec(
            trigger_id="trigger.drought_fire",
            event_template_id="event.disaster.forest_fire",
            allowed_sources=frozenset({"time", "state"}),
            severity="major",
            trigger_priority=5,
            condition={"all_of": [["projection_at_least", "public.drought_days", 3]]},
            activation_chance_0_to_1=1.0,
            cooldown_game_minutes=4320,
            exclusion_tags=frozenset({"disaster"}),
            parameters={"origin": "drought"},
        ),
        TriggerSpec(
            trigger_id="trigger.rumor_spread",
            event_template_id="event.minor.rumor",
            allowed_sources=frozenset({"time", "state"}),
            severity="minor",
            trigger_priority=0,
            condition={"all_of": [["projection_at_least", "public.tavern_visits", 10]]},
            activation_chance_0_to_1=0.5,
            cooldown_game_minutes=120,
        ),
    ]


def standard_quest_templates() -> List[QuestTemplate]:
    return [
        QuestTemplate(
            quest_template_id="quest.rescue.villager",
            name="营救村民",
            objectives=(
                ObjectiveSpec("reach", "reach_location",
                              {"location_id": "loc.forest_edge"}),
                ObjectiveSpec("defeat", "win_encounter",
                              {"winning_side": "residents"}),
            ),
            objective_ordering="sequential",
            deadline_game_minutes=1440,
            failure_policy="failed",
            rewards=(RewardSpec("currency", {"amount": 50}),),
            participant_roles={"rescuer": 1},
        ),
        QuestTemplate(
            quest_template_id="quest.deliver.supplies",
            name="运送补给",
            objectives=(
                ObjectiveSpec("deliver", "deliver_item",
                              {"item_template_id": "item.supplies",
                               "to": "resident.mayor"}, count_required=2),
            ),
            rewards=(RewardSpec("currency", {"amount": 20}),),
            participant_roles={"courier": 1},
        ),
        QuestTemplate(
            quest_template_id="quest.repair.smithy",
            name="修缮铁匠铺",
            objectives=(
                ObjectiveSpec("repair", "repair_structure", {"building_id": ""}),
            ),
            participant_roles={"worker": 1},
        ),
    ]


def _ring(x: int, y: int, w: int, h: int) -> list:
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def _cottage_geometry() -> dict:
    wall = ("collision.building.wall",
            {"shape_type": "polygon", "outer_ring_wu": _ring(0, 0, 4, 3),
             "obstacle_tag": "building.wall"})
    foundation = ("collision.building.foundation",
                  {"shape_type": "polygon", "outer_ring_wu": _ring(0, 0, 4, 3),
                   "obstacle_tag": "building.foundation"})
    debris = ("collision.debris",
              {"shape_type": "polygon", "outer_ring_wu": _ring(0, 0, 4, 3),
               "obstacle_tag": "debris"})
    ruins = ("collision.ruins",
             {"shape_type": "polygon", "outer_ring_wu": _ring(0, 0, 2, 2),
              "obstacle_tag": "ruins"})
    site_marker = ("semantic.site",
                   {"node_type": "construction_site", "label": "site"})
    entrance = ("semantic.entrance",
                {"node_type": "entrance", "label": "door"})
    interior_node = ("semantic.interior",
                     {"node_type": "interior", "interior_template_id": "interior.cottage"})
    blocked = ("semantic.entrance_blocked",
               {"node_type": "entrance", "blocked": True})
    path = ("walkability.path", {"kind": "path", "speed_modifier": 1.0})
    return {
        "state:foundation": {
            "semantic": {"site": site_marker},
        },
        "phase:clearing": {
            "semantic": {"site": site_marker},
            "walkability": {"site_path": path},
        },
        "phase:foundation_work": {
            "semantic": {"site": site_marker},
            "walkability": {"site_path": path},
            "collision": {"foundation": foundation},
        },
        "phase:structure_work": {
            "semantic": {"site": site_marker, "door": entrance},
            "walkability": {"site_path": path},
            "collision": {"foundation": foundation, "walls": wall},
        },
        "state:construction": {
            "semantic": {"site": site_marker, "door": entrance},
            "walkability": {"site_path": path},
            "collision": {"foundation": foundation, "walls": wall},
        },
        "state:intact": {
            "semantic": {"door": entrance, "room": interior_node},
            "walkability": {"site_path": path},
            "collision": {"walls": wall},
        },
        "state:lightly_damaged": {
            "semantic": {"door": entrance, "room": interior_node},
            "walkability": {"site_path": path},
            "collision": {"walls": wall, "cracks": debris},
        },
        "state:severely_damaged": {
            "semantic": {"door": blocked},
            "collision": {"walls": wall, "cracks": debris},
        },
        "state:ruins": {
            "collision": {"mound": ruins},
        },
    }


def _manor_geometry() -> dict:
    base = _cottage_geometry()
    geometry = {}
    for key, layers in base.items():
        geometry[key] = {}
        for layer, objects in layers.items():
            geometry[key][layer] = {}
            for name, (template_id, value) in objects.items():
                scaled = copy.deepcopy(value)
                ring = scaled.get("outer_ring_wu")
                if ring:
                    scaled["outer_ring_wu"] = _ring(0, 0, 6, 5)
                geometry[key][layer][name] = (template_id.replace("cottage", "manor")
                                              if "cottage" in template_id else template_id,
                                              scaled)
    return geometry


def _phase_requirements(scale: int = 1) -> dict:
    return {
        "planning": {"labor_game_minutes": 60 * scale,
                     "professions": {"architect": 60 * scale}, "materials": {}},
        "clearing": {"labor_game_minutes": 120 * scale,
                     "professions": {"laborer": 120 * scale}, "materials": {}},
        "foundation_work": {"labor_game_minutes": 240 * scale,
                            "professions": {"mason": 240 * scale},
                            "materials": {"item.stone": 10 * scale}},
        "structure_work": {"labor_game_minutes": 480 * scale,
                           "professions": {"carpenter": 480 * scale},
                           "materials": {"item.timber": 20 * scale}},
        "fitting": {"labor_game_minutes": 120 * scale,
                    "professions": {"carpenter": 120 * scale},
                    "materials": {"item.nail": 5 * scale}},
        "acceptance": {"labor_game_minutes": 30 * scale,
                       "professions": {"architect": 30 * scale}, "materials": {}},
    }


def standard_building_templates() -> List[BuildingTemplate]:
    return [
        BuildingTemplate(
            building_template_id="building.cottage",
            name="小屋",
            footprint_wu=(4, 3),
            zoning_tags=frozenset({"residential"}),
            state_geometry=_cottage_geometry(),
            upgrade_to_template_ids=("building.manor",),
            interior_template_id="interior.cottage",
            max_occupants=3,
            phase_requirements=_phase_requirements(),
            salvage_value=15,
            rebuild_cost=50,
        ),
        BuildingTemplate(
            building_template_id="building.manor",
            name="宅邸",
            footprint_wu=(6, 5),
            zoning_tags=frozenset({"residential"}),
            state_geometry=_manor_geometry(),
            interior_template_id="interior.manor",
            max_occupants=8,
            phase_requirements=_phase_requirements(scale=2),
            salvage_value=40,
            rebuild_cost=120,
        ),
    ]


def standard_parcels() -> List[Parcel]:
    return [
        Parcel(parcel_id="parcel.town.1", scene_id=SCENE_TOWN,
               region_id=SCENE_TOWN, zoning=frozenset({"residential"}),
               bounds={"x": 0, "y": 0, "w": 64, "h": 64}),
        Parcel(parcel_id="parcel.town.2", scene_id=SCENE_TOWN,
               region_id=SCENE_TOWN, zoning=frozenset({"commercial"}),
               bounds={"x": 64, "y": 0, "w": 64, "h": 64}),
        Parcel(parcel_id="parcel.town.reserved", scene_id=SCENE_TOWN,
               region_id=SCENE_TOWN, zoning=frozenset({"residential"}),
               bounds={"x": 0, "y": 64, "w": 64, "h": 64}, reserved=True),
        Parcel(parcel_id="parcel.forest.1", scene_id=SCENE_FOREST,
               region_id=SCENE_FOREST, zoning=frozenset({"residential"}),
               bounds={"x": 0, "y": 0, "w": 64, "h": 64}),
    ]


def register_standard_weather_matrix(world: EventWorld) -> None:
    town_rows = {
        "clear": {"clear": 0.5, "cloudy": 0.5},
        "cloudy": {"clear": 0.3, "cloudy": 0.3, "rain.light": 0.4},
        "rain.light": {"clear": 0.4, "cloudy": 0.3, "rain.heavy": 0.3},
        "rain.heavy": {"rain.light": 0.5, "cloudy": 0.5},
        "fog": {"clear": 1.0},
    }
    forest_rows = {
        "clear": {"clear": 0.4, "cloudy": 0.4, "magical_cold_snap": 0.2},
        "cloudy": {"clear": 0.3, "fog": 0.4, "mana_anomaly": 0.3},
        "fog": {"cloudy": 1.0},
        "magical_cold_snap": {"clear": 1.0},
        "mana_anomaly": {"cloudy": 1.0},
        "snow": {"clear": 1.0},
    }
    for season in ("spring", "summer", "autumn", "winter"):
        world.weather_matrix.register_rows(SCENE_TOWN, season, town_rows)
        world.weather_matrix.register_rows(SCENE_FOREST, season, forest_rows)


# ---------------------------------------------------------------------------
# 世界工厂
# ---------------------------------------------------------------------------


@dataclass
class Fakes:
    map_port: FakeMapPort
    econ: FakeEconPort
    resident: FakeResidentPort
    memory: FakeMemoryPort
    director_model: FakeDirectorModel
    id_factory: DeterministicIdFactory


def make_event_world(seed_hex: str = "8f3a1c2b9d4e5f60718293a4b5c6d7e8",
                     register_content: bool = True) -> Tuple[EventWorld, Fakes]:
    id_factory = make_id_factory()
    map_port = FakeMapPort()
    map_port.register_scene(SCENE_TOWN)
    map_port.register_scene(SCENE_FOREST)
    econ = FakeEconPort()
    resident = FakeResidentPort()
    memory = FakeMemoryPort()
    director_model = FakeDirectorModel()
    clock = {"now": 0}
    world = EventWorld(
        world_id="world.test",
        world_seed_hex=seed_hex,
        map_port=map_port,
        econ_port=econ,
        resident_port=resident,
        memory_port=memory,
        director_model_port=director_model,
        id_factory=id_factory,
        id_snapshot=id_factory.snapshot,
        id_restore=id_factory.restore,
        game_time_provider=lambda: clock["now"],
    )
    world.test_clock = clock  # 测试驱动用
    if register_content:
        for template in standard_event_templates():
            world.event_templates.register(template)
        for trigger in standard_triggers():
            world.trigger_registry.register(trigger)
        for quest_template in standard_quest_templates():
            world.quest_templates.register(quest_template)
        for building_template in standard_building_templates():
            world.building_templates.register(building_template)
        for parcel in standard_parcels():
            world.parcels.register(parcel)
        world.director_whitelist.allow("event.festival.harvest")
        world.director_whitelist.allow("event.weird.lights")
        world.weather.register_region(SCENE_TOWN, game_time=0)
        world.weather.register_region(SCENE_FOREST, game_time=0)
        world.weather_matrix.mark_magic_region(SCENE_FOREST)
        register_standard_weather_matrix(world)
    fakes = Fakes(map_port=map_port, econ=econ, resident=resident,
                  memory=memory, director_model=director_model,
                  id_factory=id_factory)
    return world, fakes


# ---------------------------------------------------------------------------
# 覆盖矩阵（DOC-EVENT-012 §11）
# ---------------------------------------------------------------------------

TEST_COVERAGE_MATRIX: Dict[str, Tuple[str, ...]] = {
    # DOC-EVENT-001 引擎生命周期
    "RULE-EVENT-001": ("TEST-EVENT-001",),
    "RULE-EVENT-002": ("TEST-EVENT-001", "TEST-EVENT-039"),
    "RULE-EVENT-003": ("TEST-EVENT-002", "TEST-EVENT-039"),
    "RULE-EVENT-004": ("TEST-EVENT-002", "TEST-EVENT-038"),
    "RULE-EVENT-005": ("TEST-EVENT-003", "TEST-EVENT-035"),
    "RULE-EVENT-006": ("TEST-EVENT-003", "TEST-EVENT-037"),
    # DOC-EVENT-002 触发
    "RULE-EVENT-007": ("TEST-EVENT-004",),
    "RULE-EVENT-008": ("TEST-EVENT-004", "TEST-EVENT-006"),
    "RULE-EVENT-009": ("TEST-EVENT-005", "TEST-EVENT-037"),
    "RULE-EVENT-010": ("TEST-EVENT-005", "TEST-EVENT-037"),
    "RULE-EVENT-011": ("TEST-EVENT-005", "TEST-EVENT-037"),
    "RULE-EVENT-012": ("TEST-EVENT-006", "TEST-EVENT-035"),
    # DOC-EVENT-003 Director
    "RULE-EVENT-013": ("TEST-EVENT-007",),
    "RULE-EVENT-014": ("TEST-EVENT-007", "TEST-EVENT-036"),
    "RULE-EVENT-015": ("TEST-EVENT-008",),
    "RULE-EVENT-016": ("TEST-EVENT-008", "TEST-EVENT-009"),
    "RULE-EVENT-017": ("TEST-EVENT-009", "TEST-EVENT-035"),
    "RULE-EVENT-018": ("TEST-EVENT-009",),
    # DOC-EVENT-004 Quest
    "RULE-EVENT-019": ("TEST-EVENT-010", "TEST-EVENT-039"),
    "RULE-EVENT-020": ("TEST-EVENT-011",),
    "RULE-EVENT-021": ("TEST-EVENT-011", "TEST-EVENT-039"),
    "RULE-EVENT-022": ("TEST-EVENT-010",),
    "RULE-EVENT-023": ("TEST-EVENT-012",),
    "RULE-EVENT-024": ("TEST-EVENT-012", "TEST-EVENT-039"),
    # DOC-EVENT-005 后果
    "RULE-EVENT-025": ("TEST-EVENT-013",),
    "RULE-EVENT-026": ("TEST-EVENT-013",),
    "RULE-EVENT-027": ("TEST-EVENT-014", "TEST-EVENT-039"),
    "RULE-EVENT-028": ("TEST-EVENT-014",),
    "RULE-EVENT-029": ("TEST-EVENT-015",),
    "RULE-EVENT-030": ("TEST-EVENT-015", "TEST-EVENT-039"),
    # DOC-EVENT-006 天气
    "RULE-EVENT-031": ("TEST-EVENT-016",),
    "RULE-EVENT-032": ("TEST-EVENT-016", "TEST-EVENT-037"),
    "RULE-EVENT-033": ("TEST-EVENT-017",),
    "RULE-EVENT-034": ("TEST-EVENT-017", "TEST-EVENT-018"),
    "RULE-EVENT-035": ("TEST-EVENT-018",),
    "RULE-EVENT-036": ("TEST-EVENT-018",),
    # DOC-EVENT-007 建筑本体
    "RULE-EVENT-037": ("TEST-EVENT-019",),
    "RULE-EVENT-038": ("TEST-EVENT-019", "TEST-EVENT-040"),
    "RULE-EVENT-039": ("TEST-EVENT-020", "TEST-EVENT-034"),
    "RULE-EVENT-040": ("TEST-EVENT-020",),
    "RULE-EVENT-041": ("TEST-EVENT-021", "TEST-EVENT-040"),
    "RULE-EVENT-042": ("TEST-EVENT-021",),
    # DOC-EVENT-008 放置
    "RULE-EVENT-043": ("TEST-EVENT-022",),
    "RULE-EVENT-044": ("TEST-EVENT-022", "TEST-EVENT-023"),
    "RULE-EVENT-045": ("TEST-EVENT-023",),
    "RULE-EVENT-046": ("TEST-EVENT-023", "TEST-EVENT-040"),
    "RULE-EVENT-047": ("TEST-EVENT-024",),
    "RULE-EVENT-048": ("TEST-EVENT-024", "TEST-EVENT-040"),
    # DOC-EVENT-009 施工
    "RULE-EVENT-049": ("TEST-EVENT-025", "TEST-EVENT-040"),
    "RULE-EVENT-050": ("TEST-EVENT-025", "TEST-EVENT-026"),
    "RULE-EVENT-051": ("TEST-EVENT-026", "TEST-EVENT-040"),
    "RULE-EVENT-052": ("TEST-EVENT-027",),
    "RULE-EVENT-053": ("TEST-EVENT-027", "TEST-EVENT-040"),
    "RULE-EVENT-054": ("TEST-EVENT-027", "TEST-EVENT-034"),
    # DOC-EVENT-010 损毁修复
    "RULE-EVENT-055": ("TEST-EVENT-028",),
    "RULE-EVENT-056": ("TEST-EVENT-028", "TEST-EVENT-040"),
    "RULE-EVENT-057": ("TEST-EVENT-029", "TEST-EVENT-040"),
    "RULE-EVENT-058": ("TEST-EVENT-029",),
    "RULE-EVENT-059": ("TEST-EVENT-030", "TEST-EVENT-040"),
    "RULE-EVENT-060": ("TEST-EVENT-030", "TEST-EVENT-037"),
    # DOC-EVENT-011 WorldDiff
    "RULE-EVENT-061": ("TEST-EVENT-031",),
    "RULE-EVENT-062": ("TEST-EVENT-031", "TEST-EVENT-040"),
    "RULE-EVENT-063": ("TEST-EVENT-032",),
    "RULE-EVENT-064": ("TEST-EVENT-033", "TEST-EVENT-034", "TEST-EVENT-040"),
    "RULE-EVENT-065": ("TEST-EVENT-031", "TEST-EVENT-032"),
    "RULE-EVENT-066": ("TEST-EVENT-033",),
    # DOC-EVENT-012 恢复与场景
    "RULE-EVENT-067": ("TEST-EVENT-034",),
    "RULE-EVENT-068": ("TEST-EVENT-035",),
    "RULE-EVENT-069": ("TEST-EVENT-036", "TEST-EVENT-039", "TEST-EVENT-040"),
    "RULE-EVENT-070": ("TEST-EVENT-036",),
    "RULE-EVENT-071": ("TEST-EVENT-037",),
    "RULE-EVENT-072": ("TEST-EVENT-038",),
}


def audit_coverage() -> List[str]:
    """返回覆盖缺口列表；空 = 零缺口"""
    gaps = []
    for index in range(1, 73):
        rule_id = f"RULE-EVENT-{index:03d}"
        if rule_id not in TEST_COVERAGE_MATRIX:
            gaps.append(rule_id)
    for rule_id, test_ids in TEST_COVERAGE_MATRIX.items():
        for test_id in test_ids:
            if not test_id.startswith("TEST-EVENT-"):
                gaps.append(f"{rule_id}: bad ref {test_id}")
    return gaps


# ---------------------------------------------------------------------------
# Scenario Fixture 注册表（DOC-EVENT-012：固定 Seed + 固定命令脚本 + 预期时间线 + Oracle）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScenarioFixture:
    fixture_id: str
    test_id: str
    seed_hex: str
    #: tests/event_helpers.py 中的固定命令脚本名
    script: str
    description: str
    #: 追加式事件日志 (revision, event_type) 全序列——钉死防漂移
    expected_timeline: Tuple[Tuple[int, str], ...]
    oracles: Tuple[str, ...]


SCENARIO_SEED = "8f3a1c2b9d4e5f60718293a4b5c6d7e8"

#: TEST-EVENT-039 森林火灾全链预期时间线（run_scenario_forest_fire 实测钉死）
_FOREST_FIRE_TIMELINE: Tuple[Tuple[int, str], ...] = (
    (0, "building.placed"),
    (1, "navigation.patch_committed"),
    (2, "construction.materials_delivered"),
    (3, "construction.work_session"),
    (4, "construction.phase_advanced"),
    (5, "construction.work_session"),
    (6, "building.phase_clearing"),
    (7, "navigation.patch_committed"),
    (8, "construction.work_session"),
    (9, "building.phase_foundation_work"),
    (10, "navigation.patch_committed"),
    (11, "construction.work_session"),
    (12, "building.phase_structure_work"),
    (13, "navigation.patch_committed"),
    (14, "construction.work_session"),
    (15, "construction.phase_advanced"),
    (16, "construction.work_session"),
    (17, "building.completed"),
    (18, "navigation.patch_committed"),
    (19, "world_event.instantiated"),
    (20, "world_event.active"),
    (21, "consequence.dispatched"),
    (22, "trigger.evaluated"),
    (23, "environment.blockade_applied"),
    (24, "navigation.patch_committed"),
    (25, "environment.fire_ignited"),
    (26, "building.damaged"),
    (27, "building.damaged"),
    (28, "navigation.patch_committed"),
    (29, "building.damaged"),
    (30, "building.damaged"),
    (31, "building.damaged"),
    (32, "building.damaged"),
    (33, "building.damaged"),
    (34, "building.damaged"),
    (35, "navigation.patch_committed"),
    (36, "building.damaged"),
    (37, "building.damaged"),
    (38, "building.damaged"),
    (39, "building.damaged"),
    (40, "building.damaged"),
    (41, "building.damaged"),
    (42, "building.damaged"),
    (43, "building.damaged"),
    (44, "navigation.patch_committed"),
    (45, "quest.offered"),
    (46, "quest.accepted"),
    (47, "quest.active"),
    (48, "quest.objective_progressed"),
    (49, "quest.objective_progressed"),
    (50, "quest.completed"),
    (51, "environment.fire_extinguished"),
    (52, "world_event.resolved"),
    (53, "world_event.aftermath"),
    (54, "aftermath_task.registered"),
    (55, "aftermath_task.registered"),
    (56, "rubble.claimed"),
    (57, "rubble.cleaned"),
    (58, "navigation.patch_committed"),
    (59, "environment.blockade_lifted"),
    (60, "aftermath_task.in_progress"),
    (61, "aftermath_task.completed"),
    (62, "aftermath_task.in_progress"),
    (63, "aftermath_task.completed"),
    (64, "world_event.archived"),
)

#: TEST-EVENT-040 建造全链预期时间线（run_scenario_construction 实测钉死）
_CONSTRUCTION_TIMELINE: Tuple[Tuple[int, str], ...] = (
    (0, "building.placed"),
    (1, "navigation.patch_committed"),
    (2, "construction.materials_delivered"),
    (3, "construction.work_session"),
    (4, "construction.phase_advanced"),
    (5, "construction.work_session"),
    (6, "building.phase_clearing"),
    (7, "navigation.patch_committed"),
    (8, "construction.work_session"),
    (9, "building.phase_foundation_work"),
    (10, "navigation.patch_committed"),
    (11, "construction.work_session"),
    (12, "building.phase_structure_work"),
    (13, "navigation.patch_committed"),
    (14, "construction.work_session"),
    (15, "construction.phase_advanced"),
    (16, "construction.work_session"),
    (17, "building.completed"),
    (18, "navigation.patch_committed"),
    (19, "building.upgrade_started"),
    (20, "navigation.patch_committed"),
    (21, "construction.materials_delivered"),
    (22, "construction.work_session"),
    (23, "construction.phase_advanced"),
    (24, "construction.work_session"),
    (25, "building.phase_clearing"),
    (26, "navigation.patch_committed"),
    (27, "construction.work_session"),
    (28, "building.phase_foundation_work"),
    (29, "navigation.patch_committed"),
    (30, "construction.work_session"),
    (31, "building.phase_structure_work"),
    (32, "navigation.patch_committed"),
    (33, "construction.work_session"),
    (34, "construction.phase_advanced"),
    (35, "construction.work_session"),
    (36, "building.completed"),
    (37, "navigation.patch_committed"),
    (38, "building.damaged"),
    (39, "navigation.patch_committed"),
    (40, "building.damage_assessed"),
    (41, "building.repaired"),
    (42, "navigation.patch_committed"),
)


SCENARIO_FIXTURES: Dict[str, ScenarioFixture] = {
    "scenario.event.forest_fire_full_chain": ScenarioFixture(
        fixture_id="scenario.event.forest_fire_full_chain",
        test_id="TEST-EVENT-039",
        seed_hex=SCENARIO_SEED,
        script="run_scenario_forest_fire",
        description="森林火灾全链：触发→封路→焚毁成瓦砾→营救→赔偿→清瓦砾→Reverse Entry 重开→归档",
        expected_timeline=_FOREST_FIRE_TIMELINE,
        oracles=(
            "audit_invariants_ok",
            "budget_never_exceeded",
            "no_duplicate_events",
            "diff_replay_consistent",
        ),
    ),
    "scenario.event.construction_full_chain": ScenarioFixture(
        fixture_id="scenario.event.construction_full_chain",
        test_id="TEST-EVENT-040",
        seed_hex=SCENARIO_SEED,
        script="run_scenario_construction",
        description="建造全链：放置→六阶段→升级 manor→风暴损毁→评估→修复→重放一致",
        expected_timeline=_CONSTRUCTION_TIMELINE,
        oracles=(
            "audit_invariants_ok",
            "diff_replay_consistent",
            "export_import_replay_consistent",
        ),
    ),
}
