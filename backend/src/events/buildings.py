"""
建筑聚合：物理状态、损毁、修复、瓦砾（DOC-EVENT-007/010）

- 六态 Physical State × Construction Phase 正交受约
- 状态变化四件套同事务（状态+NavigationPatch+DomainEvent+WorldDiff）
- damage_points 阈值表唯一映射；跨阈值触发几何切换
- severely_damaged 默认禁入；ruins 无 interior 且原子生成 Rubble（排他领取）
- 修复分级：light 直接修、severe 需有效 Damage Assessment、ruins 不可修
- 重建成本 > 搜刮价值（注册期强制）；decay 周期 1440 分钟
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from .constants import (
    CONSTRUCTION_PHASES,
    DAMAGE_SOURCES,
    DEFAULT_DAMAGE_THRESHOLDS,
    GEOMETRIC_PHASES,
    PHASE_REQUIRED_STATES,
    PHYSICAL_STATES,
    SCENE_BUILDING_CAP,
)
from .diff import DiffOperation, MapChangeCommitter


class BuildingError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


class RelocationFailed(Exception):
    """resident_port 无法完成安全转移 → 整笔回滚"""


# ---------------------------------------------------------------------------
# 模板
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BuildingTemplate:
    building_template_id: str
    name: str
    footprint_wu: Tuple[int, int]
    zoning_tags: frozenset
    #: state_geometry: 键 "state:<physical_state>" 或 "phase:<construction_phase>"；
    #: 值 {layer: {name: (object_template_id, value)}}
    state_geometry: dict
    upgrade_to_template_ids: Tuple[str, ...] = ()
    interior_template_id: Optional[str] = None
    max_occupants: int = 4
    phase_requirements: dict = field(default_factory=dict)
    damage_thresholds: tuple = DEFAULT_DAMAGE_THRESHOLDS
    salvage_value: int = 0
    rebuild_cost: int = 0

    def __post_init__(self) -> None:
        for state in PHYSICAL_STATES:
            if f"state:{state}" not in self.state_geometry:
                raise BuildingError(
                    "template_geometry_incomplete", f"{self.building_template_id}: {state}"
                )
        if self.rebuild_cost <= self.salvage_value:
            # 重建成本必须大于搜刮价值，防套利
            raise BuildingError(
                "template_arbitrage", f"{self.building_template_id}: rebuild<=salvage"
            )
        for phase in self.phase_requirements:
            if phase not in CONSTRUCTION_PHASES:
                raise BuildingError("phase_invalid", phase)

    def geometry_for(self, key: str) -> Dict[str, Dict[str, Tuple[str, dict]]]:
        return self.state_geometry.get(key, {})

    def threshold_state(self, damage_points: int) -> str:
        for low, high, state in self.damage_thresholds:
            if damage_points >= low and (high is None or damage_points <= high):
                return state
        raise BuildingError("threshold_table_invalid", str(damage_points))


class BuildingTemplateRegistry:
    def __init__(self) -> None:
        self._templates: Dict[str, BuildingTemplate] = {}

    def register(self, template: BuildingTemplate) -> None:
        if template.building_template_id in self._templates:
            raise BuildingError("template_duplicate", template.building_template_id)
        self._templates[template.building_template_id] = template

    def get(self, building_template_id: str) -> BuildingTemplate:
        try:
            return self._templates[building_template_id]
        except KeyError:
            raise BuildingError("building_template_unknown", building_template_id) from None

    def all(self) -> Tuple[BuildingTemplate, ...]:
        return tuple(self._templates.values())


# ---------------------------------------------------------------------------
# 聚合
# ---------------------------------------------------------------------------


@dataclass
class Building:
    building_id: str
    building_template_id: str
    scene_id: str
    parcel_id: str
    footprint: dict  # {x, y, w, h}
    orientation: int
    physical_state: str
    construction_phase: Optional[str]
    geometry_key: str
    created_game_time: int
    damage_points: int = 0
    occupants: List[str] = field(default_factory=list)
    interior_active: bool = False
    reinforcement: Optional[dict] = None  # {bps, until}
    upgrade_target: Optional[str] = None
    removed: bool = False
    decay_accumulator_milli: int = 0
    version: int = 0

    def to_dict(self) -> dict:
        return {
            "building_id": self.building_id,
            "building_template_id": self.building_template_id,
            "scene_id": self.scene_id,
            "parcel_id": self.parcel_id,
            "footprint": dict(self.footprint),
            "orientation": self.orientation,
            "physical_state": self.physical_state,
            "construction_phase": self.construction_phase,
            "geometry_key": self.geometry_key,
            "created_game_time": self.created_game_time,
            "damage_points": self.damage_points,
            "occupants": list(self.occupants),
            "interior_active": self.interior_active,
            "reinforcement": copy.deepcopy(self.reinforcement),
            "upgrade_target": self.upgrade_target,
            "removed": self.removed,
            "decay_accumulator_milli": self.decay_accumulator_milli,
            "version": self.version,
        }

    @staticmethod
    def from_dict(data: dict) -> "Building":
        return Building(
            building_id=data["building_id"],
            building_template_id=data["building_template_id"],
            scene_id=data["scene_id"],
            parcel_id=data["parcel_id"],
            footprint=dict(data["footprint"]),
            orientation=data["orientation"],
            physical_state=data["physical_state"],
            construction_phase=data["construction_phase"],
            geometry_key=data["geometry_key"],
            created_game_time=data["created_game_time"],
            damage_points=data["damage_points"],
            occupants=list(data["occupants"]),
            interior_active=data["interior_active"],
            reinforcement=copy.deepcopy(data["reinforcement"]),
            upgrade_target=data["upgrade_target"],
            removed=data["removed"],
            decay_accumulator_milli=data["decay_accumulator_milli"],
            version=data["version"],
        )

    def check_invariant(self) -> None:
        """Physical State × Construction Phase 正交受约（RULE-EVENT-037）"""
        if self.removed:
            return
        if self.physical_state in PHASE_REQUIRED_STATES:
            if self.construction_phase not in CONSTRUCTION_PHASES:
                raise BuildingError(
                    "building_state_invalid",
                    f"{self.building_id}: {self.physical_state} without phase",
                )
        elif self.construction_phase is not None:
            raise BuildingError(
                "building_state_invalid",
                f"{self.building_id}: {self.physical_state} with phase {self.construction_phase}",
            )


@dataclass
class Rubble:
    rubble_id: str
    building_id: str
    parcel_id: str
    scene_id: str
    salvage_pool_id: str
    claimed_by: Optional[str] = None
    cleaned: bool = False

    def to_dict(self) -> dict:
        return dict(self.__dict__)

    @staticmethod
    def from_dict(data: dict) -> "Rubble":
        return Rubble(**data)


@dataclass
class DamageAssessment:
    assessment_id: str
    building_id: str
    damage_points: int
    game_time: int
    valid_until: int

    def to_dict(self) -> dict:
        return dict(self.__dict__)

    @staticmethod
    def from_dict(data: dict) -> "DamageAssessment":
        return DamageAssessment(**data)


# ---------------------------------------------------------------------------
# 服务
# ---------------------------------------------------------------------------

DAMAGEABLE_STATES = ("intact", "lightly_damaged", "severely_damaged")
DAMAGE_POINT_CAP = 10_000
REPAIR_MINUTES_PER_POINT = 10
DECAY_MILLI_PER_PERIOD = 1000


class BuildingService:
    def __init__(
        self,
        templates: BuildingTemplateRegistry,
        committer: MapChangeCommitter,
        map_port: object,
        resident_port: object,
        econ_port: object,
        event_log: object,
        id_factory: Callable[[], str],
    ) -> None:
        self._templates = templates
        self._committer = committer
        self._map = map_port
        self._resident = resident_port
        self._econ = econ_port
        self._log = event_log
        self._id_factory = id_factory
        self._buildings: Dict[str, Building] = {}
        self._rubble: Dict[str, Rubble] = {}
        self._assessments: Dict[str, DamageAssessment] = {}
        self._parcel_occupancy: Dict[str, str] = {}
        self._command_results: Dict[str, dict] = {}

    # -- 查询 ------------------------------------------------------------

    def get(self, building_id: str) -> Building:
        try:
            return self._buildings[building_id]
        except KeyError:
            raise BuildingError("building_unknown", building_id) from None

    def all(self) -> List[Building]:
        return list(self._buildings.values())

    def count_in_scene(self, scene_id: str) -> int:
        return sum(
            1 for b in self._buildings.values() if b.scene_id == scene_id and not b.removed
        )

    def parcel_owner_building(self, parcel_id: str) -> Optional[str]:
        return self._parcel_occupancy.get(parcel_id)

    def parcel_has_rubble(self, parcel_id: str) -> bool:
        return any(
            r.parcel_id == parcel_id and not r.cleaned for r in self._rubble.values()
        )

    def rubble_of(self, building_id: str) -> Optional[Rubble]:
        for rubble in self._rubble.values():
            if rubble.building_id == building_id and not rubble.cleaned:
                return rubble
        return None

    # -- 几何操作集 ----------------------------------------------------------

    def _object_id(self, building: Building, layer: str, name: str) -> str:
        return f"{building.building_id}.{layer}.{name}"

    def _geometry_ops(
        self, building: Building, from_key: str, to_key: str,
        to_template_id: Optional[str] = None,
    ) -> Tuple[DiffOperation, ...]:
        """从当前几何 key 到目标 key 的 add/replace/remove 操作集（前值取自地图现状）"""
        template = self._templates.get(building.building_template_id)
        to_template = (
            self._templates.get(to_template_id) if to_template_id else template
        )
        from_geom = template.geometry_for(from_key)
        to_geom = to_template.geometry_for(to_key)
        ops: List[DiffOperation] = []
        for layer in sorted(set(from_geom) | set(to_geom)):
            old = from_geom.get(layer, {})
            new = to_geom.get(layer, {})
            for name in sorted(set(old) | set(new)):
                object_id = self._object_id(building, layer, name)
                if name in old and name not in new:
                    prior = self._map.current_object(building.scene_id, layer, object_id)
                    if prior is None:
                        raise BuildingError("geometry_binding_broken", object_id)
                    ops.append(DiffOperation(
                        op="remove", layer=layer, object_id=object_id,
                        object_template_id=old[name][0], prior=copy.deepcopy(prior["value"]),
                    ))
                elif name not in old and name in new:
                    ops.append(DiffOperation(
                        op="add", layer=layer, object_id=object_id,
                        object_template_id=new[name][0], value=copy.deepcopy(new[name][1]),
                    ))
                elif old[name] != new[name]:
                    prior = self._map.current_object(building.scene_id, layer, object_id)
                    if prior is None:
                        raise BuildingError("geometry_binding_broken", object_id)
                    ops.append(DiffOperation(
                        op="replace", layer=layer, object_id=object_id,
                        object_template_id=new[name][0],
                        value=copy.deepcopy(new[name][1]),
                        prior=copy.deepcopy(prior["value"]),
                    ))
        return tuple(ops)

    def _commit_building_change(
        self,
        building: Building,
        to_geometry_key: str,
        game_time: int,
        source: dict,
        domain_event_type: str,
        domain_event_payload: dict,
        business_apply: Callable[[], None],
        extra_ops: Tuple[DiffOperation, ...] = (),
        expected_revision: Optional[int] = None,
        to_template_id: Optional[str] = None,
    ) -> None:
        """四件套提交：状态变更 + patch + event + diff，任一失败全部回滚"""
        ops = self._geometry_ops(
            building, building.geometry_key, to_geometry_key, to_template_id
        ) + extra_ops
        # 预校验（操作合法性 + revision），保证 relocate/escrow 之后提交不会失败
        for op in ops:
            op.validate()
        if expected_revision is not None:
            current_revision = self._map.current_revision(building.scene_id)
            if current_revision != expected_revision:
                raise BuildingError("stale_revision",
                                    f"{current_revision} != {expected_revision}")

        def apply_and_bind() -> None:
            business_apply()
            # 几何绑定与状态同事务落账：后续变更的前值锚定在新 key 上
            building.geometry_key = to_geometry_key

        def snapshot() -> dict:
            return building.to_dict()

        def restore(data: dict) -> None:
            self._buildings[building.building_id] = Building.from_dict(data)

        self._committer.commit(
            scene_id=building.scene_id,
            game_time=game_time,
            diff_kind="building",
            source=source,
            subject_id=building.building_id,
            operations=ops,
            business_apply=apply_and_bind,
            business_snapshot=snapshot,
            business_restore=restore,
            domain_event_type=domain_event_type,
            domain_event_payload=domain_event_payload,
            expected_revision=expected_revision,
        )

    # -- 创建（placement 调用） ------------------------------------------------

    def create_at_placement(
        self,
        command_id: str,
        building_template_id: str,
        scene_id: str,
        parcel_id: str,
        footprint: dict,
        orientation: int,
        game_time: int,
        expected_revision: int,
    ) -> Building:
        if command_id in self._command_results:
            return self.get(self._command_results[command_id]["building_id"])
        if self.count_in_scene(scene_id) >= SCENE_BUILDING_CAP:
            raise BuildingError("scene_building_cap_exceeded", scene_id)
        building = Building(
            building_id=self._id_factory(),
            building_template_id=building_template_id,
            scene_id=scene_id,
            parcel_id=parcel_id,
            footprint=dict(footprint),
            orientation=orientation,
            physical_state="foundation",
            construction_phase="planning",
            geometry_key="state:foundation",
            created_game_time=game_time,
        )

        def apply() -> None:
            building.check_invariant()
            self._buildings[building.building_id] = building
            self._parcel_occupancy[parcel_id] = building.building_id

        def snapshot() -> dict:
            return {"exists": building.building_id in self._buildings}

        def restore(_data: dict) -> None:
            self._buildings.pop(building.building_id, None)
            self._parcel_occupancy.pop(parcel_id, None)

        ops = self._geometry_ops(building, "__empty__", "state:foundation")
        for op in ops:
            op.validate()
        if self._map.current_revision(scene_id) != expected_revision:
            raise BuildingError("stale_revision", scene_id)
        self._committer.commit(
            scene_id=scene_id, game_time=game_time, diff_kind="building",
            source={"command_id": command_id, "world_event_id": None},
            subject_id=building.building_id,
            operations=ops,
            business_apply=apply, business_snapshot=snapshot, business_restore=restore,
            domain_event_type="building.placed",
            domain_event_payload={
                "building_id": building.building_id,
                "building_template_id": building_template_id,
                "parcel_id": parcel_id,
                "footprint": dict(footprint),
                "orientation": orientation,
            },
            expected_revision=expected_revision,
        )
        building.check_invariant()
        self._command_results[command_id] = {"building_id": building.building_id}
        return building

    # -- 施工几何同步（construction 调用） ---------------------------------------

    def commit_phase_geometry(
        self, building: Building, completed_phase: str, game_time: int,
        source: dict, business_apply: Callable[[], None],
    ) -> None:
        if completed_phase not in GEOMETRIC_PHASES:
            raise BuildingError("phase_not_geometric", completed_phase)
        to_key = f"phase:{completed_phase}"
        template = self._templates.get(building.building_template_id)
        if to_key not in template.state_geometry:
            # 阶段无独立几何时落到物理状态映射
            to_key = f"state:{building.physical_state}"
        self._commit_building_change(
            building, to_key, game_time, source,
            domain_event_type=f"building.phase_{completed_phase}",
            domain_event_payload={
                "building_id": building.building_id, "phase": completed_phase,
            },
            business_apply=business_apply,
        )

    def commit_acceptance(
        self, building: Building, game_time: int, source: dict,
        business_apply: Callable[[], None],
        to_template_id: Optional[str] = None,
    ) -> None:
        self._commit_building_change(
            building, "state:intact", game_time, source,
            domain_event_type="building.completed",
            domain_event_payload={"building_id": building.building_id,
                                  "to_template_id": to_template_id},
            business_apply=business_apply,
            to_template_id=to_template_id,
        )

    def commit_upgrade_start(self, building: Building, game_time: int,
                             source: dict, business_apply: Callable[[], None]) -> None:
        self._commit_building_change(
            building, "state:construction", game_time, source,
            domain_event_type="building.upgrade_started",
            domain_event_payload={"building_id": building.building_id,
                                  "upgrade_target": building.upgrade_target},
            business_apply=business_apply,
        )

    # -- 损毁 ---------------------------------------------------------------

    def apply_damage(
        self,
        command_id: str,
        building_id: str,
        source: str,
        damage_points: int,
        game_time: int,
        evidence_id: Optional[str] = None,
    ) -> Building:
        if command_id in self._command_results:
            return self.get(self._command_results[command_id]["building_id"])
        if source not in DAMAGE_SOURCES:
            raise BuildingError("damage_source_invalid", source)
        if damage_points < 0 or damage_points > DAMAGE_POINT_CAP:
            raise BuildingError("damage_points_invalid", str(damage_points))
        building = self.get(building_id)
        if building.removed:
            raise BuildingError("building_state_invalid", "removed")
        if building.physical_state not in DAMAGEABLE_STATES:
            raise BuildingError(
                "building_state_invalid", f"{building.physical_state} not damageable"
            )
        template = self._templates.get(building.building_template_id)
        new_points = min(DAMAGE_POINT_CAP, building.damage_points + damage_points)
        new_state = template.threshold_state(new_points)
        if new_state == building.physical_state:
            building.damage_points = new_points
            building.version += 1
            self._log.append(
                "building.damaged",
                {"building_id": building_id, "source": source,
                 "damage_points": new_points, "state": new_state,
                 "threshold_crossed": False, "evidence_id": evidence_id},
                game_time, caused_by_command_id=command_id,
            )
            self._command_results[command_id] = {"building_id": building_id}
            return building

        # 跨阈值：预校验在前，安全转移在提交前，失败整笔不生效
        losing_interior = new_state in ("severely_damaged", "ruins")
        relocating = losing_interior and building.occupants
        rubble_ops: Tuple[DiffOperation, ...] = ()
        rubble: Optional[Rubble] = None
        if new_state == "ruins":
            rubble = Rubble(
                rubble_id=self._id_factory(),
                building_id=building_id,
                parcel_id=building.parcel_id,
                scene_id=building.scene_id,
                salvage_pool_id=f"salvage.{building_id}",
            )
            rubble_ops = (DiffOperation(
                op="add", layer="collision", object_id=rubble.rubble_id,
                object_template_id="collision.rubble",
                value={"shape_type": "polygon", "outer_ring_wu": _footprint_ring(building.footprint),
                       "obstacle_tag": "rubble"},
            ),)
        if relocating:
            try:
                self._resident.relocate_occupants(
                    building_id, list(building.occupants), game_time
                )
            except RelocationFailed:
                raise BuildingError(
                    "occupant_relocation_failed", building_id
                ) from None
        if rubble is not None:
            self._econ.escrow_salvage(
                rubble.salvage_pool_id,
                {"value": template.salvage_value},
                evidence_id=building_id,
            )

        previous_state = building.physical_state

        def apply() -> None:
            building.damage_points = new_points
            building.physical_state = new_state
            building.geometry_key = f"state:{new_state}"
            building.interior_active = new_state in ("intact", "lightly_damaged")
            if relocating:
                building.occupants = []
            if rubble is not None:
                self._rubble[rubble.rubble_id] = rubble
            building.version += 1

        self._commit_building_change(
            building, f"state:{new_state}", game_time,
            source={"command_id": command_id, "world_event_id": evidence_id},
            domain_event_type="building.damaged",
            domain_event_payload={
                "building_id": building_id, "source": source,
                "damage_points": new_points, "from_state": previous_state,
                "to_state": new_state, "threshold_crossed": True,
                "evidence_id": evidence_id,
                "rubble_id": rubble.rubble_id if rubble else None,
            },
            business_apply=apply,
            extra_ops=rubble_ops,
        )
        self._command_results[command_id] = {"building_id": building_id}
        return building

    # -- 瓦砾 ---------------------------------------------------------------

    def claim_rubble(self, command_id: str, rubble_id: str, claimer_id: str,
                     game_time: int) -> Rubble:
        if command_id in self._command_results:
            return self._rubble[self._command_results[command_id]["rubble_id"]]
        rubble = self._rubble.get(rubble_id)
        if rubble is None or rubble.cleaned:
            raise BuildingError("rubble_unknown", rubble_id)
        if rubble.claimed_by is not None:
            # 排他领取：第二个领取者拒绝，防资源复制
            raise BuildingError("rubble_already_claimed", rubble_id)
        self._econ.claim_salvage(rubble.salvage_pool_id, claimer_id)
        rubble.claimed_by = claimer_id
        self._log.append(
            "rubble.claimed",
            {"rubble_id": rubble_id, "claimer_id": claimer_id},
            game_time, caused_by_command_id=command_id,
        )
        self._command_results[command_id] = {"rubble_id": rubble_id}
        return rubble

    def cleanup_rubble(self, command_id: str, rubble_id: str, game_time: int) -> Rubble:
        if command_id in self._command_results:
            return self._rubble[self._command_results[command_id]["rubble_id"]]
        rubble = self._rubble.get(rubble_id)
        if rubble is None or rubble.cleaned:
            raise BuildingError("rubble_unknown", rubble_id)
        building = self.get(rubble.building_id)
        remove_op = DiffOperation(
            op="remove", layer="collision", object_id=rubble.rubble_id,
            object_template_id="collision.rubble",
            prior={"shape_type": "polygon", "outer_ring_wu": _footprint_ring(building.footprint),
                   "obstacle_tag": "rubble"},
        )

        def apply() -> None:
            rubble.cleaned = True

        def snapshot() -> dict:
            return {"cleaned": rubble.cleaned}

        def restore(data: dict) -> None:
            rubble.cleaned = data["cleaned"]

        self._committer.commit(
            scene_id=building.scene_id, game_time=game_time, diff_kind="building",
            source={"command_id": command_id, "world_event_id": None},
            subject_id=rubble.rubble_id,
            operations=(remove_op,),
            business_apply=apply, business_snapshot=snapshot, business_restore=restore,
            domain_event_type="rubble.cleaned",
            domain_event_payload={"rubble_id": rubble_id, "parcel_id": rubble.parcel_id},
        )
        self._command_results[command_id] = {"rubble_id": rubble_id}
        return rubble

    # -- 修复 ---------------------------------------------------------------

    def assess_damage(self, command_id: str, building_id: str, game_time: int,
                      valid_duration: int = 1440) -> DamageAssessment:
        if command_id in self._command_results:
            return self._assessments[self._command_results[command_id]["assessment_id"]]
        building = self.get(building_id)
        assessment = DamageAssessment(
            assessment_id=self._id_factory(),
            building_id=building_id,
            damage_points=building.damage_points,
            game_time=game_time,
            valid_until=game_time + valid_duration,
        )
        self._assessments[assessment.assessment_id] = assessment
        self._log.append(
            "building.damage_assessed",
            {"assessment_id": assessment.assessment_id, "building_id": building_id,
             "damage_points": building.damage_points},
            game_time, caused_by_command_id=command_id,
        )
        self._command_results[command_id] = {"assessment_id": assessment.assessment_id}
        return assessment

    def repair(
        self,
        command_id: str,
        building_id: str,
        labor_game_minutes: int,
        materials: dict,
        game_time: int,
        assessment_id: Optional[str] = None,
    ) -> Building:
        if command_id in self._command_results:
            return self.get(self._command_results[command_id]["building_id"])
        building = self.get(building_id)
        if building.removed or building.physical_state not in DAMAGEABLE_STATES:
            raise BuildingError("building_state_invalid", building.physical_state)
        if building.physical_state == "intact":
            raise BuildingError("building_state_invalid", "nothing to repair")
        if building.physical_state == "severely_damaged":
            if assessment_id is None:
                raise BuildingError("assessment_required", building_id)
            assessment = self._assessments.get(assessment_id)
            if assessment is None or assessment.building_id != building_id:
                raise BuildingError("assessment_required", "unknown assessment")
            if game_time > assessment.valid_until:
                raise BuildingError("assessment_expired", assessment_id)
        if labor_game_minutes <= 0:
            raise BuildingError("repair_labor_invalid", str(labor_game_minutes))
        # 修复与施工对称：材料经 ECON 结算
        self._econ.consume_materials(
            f"repair.{building_id}", dict(materials), evidence_id=command_id
        )
        template = self._templates.get(building.building_template_id)
        repair_points = min(building.damage_points, labor_game_minutes // REPAIR_MINUTES_PER_POINT)
        new_points = building.damage_points - repair_points
        new_state = template.threshold_state(new_points)
        # 修复完成不越过 intact（threshold(0)=intact，天然满足）
        previous_state = building.physical_state
        if new_state == previous_state:
            building.damage_points = new_points
            building.version += 1
            self._log.append(
                "building.repaired",
                {"building_id": building_id, "damage_points": new_points,
                 "state": new_state, "threshold_crossed": False},
                game_time, caused_by_command_id=command_id,
            )
            self._command_results[command_id] = {"building_id": building_id}
            return building

        def apply() -> None:
            building.damage_points = new_points
            building.physical_state = new_state
            building.geometry_key = f"state:{new_state}"
            building.interior_active = new_state in ("intact", "lightly_damaged")
            building.version += 1

        self._commit_building_change(
            building, f"state:{new_state}", game_time,
            source={"command_id": command_id, "world_event_id": None},
            domain_event_type="building.repaired",
            domain_event_payload={
                "building_id": building_id, "from_state": previous_state,
                "to_state": new_state, "damage_points": new_points,
                "threshold_crossed": True,
            },
            business_apply=apply,
        )
        self._command_results[command_id] = {"building_id": building_id}
        return building

    # -- decay / 加固 -----------------------------------------------------------

    def reinforce(self, building_id: str, decay_reduction_bps: int,
                  duration_game_minutes: int, game_time: int,
                  source_event_id: Optional[str] = None) -> Building:
        building = self.get(building_id)
        if building.removed or building.physical_state == "ruins":
            raise BuildingError("building_state_invalid", "cannot reinforce ruins")
        if not 0 < decay_reduction_bps <= 10_000:
            raise BuildingError("reinforcement_invalid", str(decay_reduction_bps))
        building.reinforcement = {
            "bps": decay_reduction_bps,
            "until": game_time + duration_game_minutes,
        }
        building.version += 1
        self._log.append(
            "building.reinforced",
            {"building_id": building_id, "bps": decay_reduction_bps,
             "until": building.reinforcement["until"],
             "source_event_id": source_event_id},
            game_time,
        )
        return building

    def decay_eval(self, occurrence: dict) -> dict:
        """周期 1440 分钟：未被加固的建筑累积衰变；跨阈值走同一四件套"""
        key = occurrence["occurrence_key"]
        game_time = occurrence["game_time"]
        decayed: List[str] = []
        for building in list(self._buildings.values()):
            if building.removed or building.physical_state not in DAMAGEABLE_STATES:
                continue
            milli = DECAY_MILLI_PER_PERIOD
            reinforcement = building.reinforcement
            if reinforcement and game_time < reinforcement["until"]:
                milli = milli * (10_000 - reinforcement["bps"]) // 10_000
            building.decay_accumulator_milli += milli
            points = building.decay_accumulator_milli // 1000
            if points <= 0:
                continue
            building.decay_accumulator_milli %= 1000
            self.apply_damage(
                command_id=f"{key}:{building.building_id}",
                building_id=building.building_id,
                source="decay",
                damage_points=points,
                game_time=game_time,
                evidence_id=key,
            )
            decayed.append(building.building_id)
        self._log.append(
            "building.decay_eval",
            {"occurrence_key": key, "decayed": decayed},
            game_time,
        )
        return {"status": "processed", "decayed": decayed}

    # -- 拆除 ---------------------------------------------------------------

    def demolish(self, command_id: str, building_id: str, game_time: int) -> Building:
        if command_id in self._command_results:
            return self.get(self._command_results[command_id]["building_id"])
        building = self.get(building_id)
        if building.removed:
            raise BuildingError("building_state_invalid", "already removed")
        if building.occupants:
            try:
                self._resident.relocate_occupants(
                    building_id, list(building.occupants), game_time
                )
            except RelocationFailed:
                raise BuildingError("occupant_relocation_failed", building_id) from None
        rubble = self.rubble_of(building_id)
        extra_ops: List[DiffOperation] = []
        if rubble is not None:
            extra_ops.append(DiffOperation(
                op="remove", layer="collision", object_id=rubble.rubble_id,
                object_template_id="collision.rubble",
                prior={"shape_type": "polygon",
                       "outer_ring_wu": _footprint_ring(building.footprint),
                       "obstacle_tag": "rubble"},
            ))
            self._econ.release_escrow(rubble.salvage_pool_id)

        def apply() -> None:
            building.removed = True
            building.occupants = []
            building.interior_active = False
            building.version += 1
            if rubble is not None:
                rubble.cleaned = True
            self._parcel_occupancy.pop(building.parcel_id, None)

        self._commit_building_change(
            building, "__empty__", game_time,
            source={"command_id": command_id, "world_event_id": None},
            domain_event_type="building.demolished",
            domain_event_payload={"building_id": building_id},
            business_apply=apply,
            extra_ops=tuple(extra_ops),
        )
        self._command_results[command_id] = {"building_id": building_id}
        return building

    # -- occupants ------------------------------------------------------------

    def admit_occupant(self, building_id: str, resident_id: str) -> None:
        """severely_damaged 默认禁入；ruins 无 interior"""
        building = self.get(building_id)
        if building.removed or not building.interior_active:
            raise BuildingError("building_entry_forbidden", building_id)
        template = self._templates.get(building.building_template_id)
        if len(building.occupants) >= template.max_occupants:
            raise BuildingError("building_occupants_full", building_id)
        building.occupants.append(resident_id)
        building.version += 1

    def leave(self, building_id: str, resident_id: str) -> None:
        building = self.get(building_id)
        if resident_id in building.occupants:
            building.occupants.remove(resident_id)
            building.version += 1

    # -- 导出/导入 -----------------------------------------------------------

    def export_state(self) -> dict:
        return {
            "buildings": {bid: b.to_dict() for bid, b in self._buildings.items()},
            "rubble": {rid: r.to_dict() for rid, r in self._rubble.items()},
            "assessments": {aid: a.to_dict() for aid, a in self._assessments.items()},
            "parcel_occupancy": dict(self._parcel_occupancy),
            "command_results": copy.deepcopy(self._command_results),
        }

    def import_state(self, data: dict) -> None:
        self._buildings = {bid: Building.from_dict(b) for bid, b in data["buildings"].items()}
        self._rubble = {rid: Rubble.from_dict(r) for rid, r in data["rubble"].items()}
        self._assessments = {
            aid: DamageAssessment.from_dict(a) for aid, a in data["assessments"].items()
        }
        self._parcel_occupancy = dict(data["parcel_occupancy"])
        self._command_results = copy.deepcopy(data["command_results"])


def _footprint_ring(footprint: dict) -> list:
    x, y, w, h = footprint["x"], footprint["y"], footprint["w"], footprint["h"]
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
