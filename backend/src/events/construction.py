"""
施工阶段机（DOC-EVENT-009）

- 六阶段固定顺序 planning→clearing→foundation_work→structure_work→fitting→acceptance
- 材料经 Material Delivery 进现场托管 Inventory（ECON 结算）
- 劳动只由已提交 Work Session 累计（game minutes × 工种效率，万分比定点）
- 几何阶段完成四件套同步；升级走注册 Upgrade Path，无降级路径
- 中断保留进度与材料；4320 分钟无 Work Session → stalled + 通知 owner
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .buildings import Building, BuildingError, BuildingService
from .constants import (
    CONSTRUCTION_PHASES,
    CONSTRUCTION_STALLED_GAME_MINUTES,
    GEOMETRIC_PHASES,
)


class ConstructionError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass
class ConstructionSite:
    building_id: str
    labor_progress: Dict[str, int] = field(default_factory=dict)  # phase → minutes
    materials_escrow: Dict[str, int] = field(default_factory=dict)  # item → count
    last_work_game_time: int = 0
    stalled: bool = False
    stall_notified: bool = False

    def to_dict(self) -> dict:
        return {
            "building_id": self.building_id,
            "labor_progress": dict(self.labor_progress),
            "materials_escrow": dict(self.materials_escrow),
            "last_work_game_time": self.last_work_game_time,
            "stalled": self.stalled,
            "stall_notified": self.stall_notified,
        }

    @staticmethod
    def from_dict(data: dict) -> "ConstructionSite":
        return ConstructionSite(
            building_id=data["building_id"],
            labor_progress=dict(data["labor_progress"]),
            materials_escrow=dict(data["materials_escrow"]),
            last_work_game_time=data["last_work_game_time"],
            stalled=data["stalled"],
            stall_notified=data["stall_notified"],
        )


class ConstructionService:
    def __init__(
        self,
        buildings: BuildingService,
        econ_port: object,
        resident_port: object,
        event_log: object,
        id_factory: Callable[[], str],
    ) -> None:
        self._buildings = buildings
        self._econ = econ_port
        self._resident = resident_port
        self._log = event_log
        self._id_factory = id_factory
        self._sites: Dict[str, ConstructionSite] = {}
        self._command_results: Dict[str, dict] = {}
        self._stall_checks: Dict[str, dict] = {}

    def site_of(self, building_id: str) -> ConstructionSite:
        return self._sites.setdefault(building_id, ConstructionSite(building_id=building_id))

    def _phase_requirements(self, building: Building, phase: str) -> dict:
        template = self._buildings._templates.get(building.building_template_id)
        return template.phase_requirements.get(
            phase, {"labor_game_minutes": 0, "professions": {}, "materials": {}}
        )

    # -- 材料 ----------------------------------------------------------------

    def deliver_materials(
        self, command_id: str, building_id: str, materials: Dict[str, int],
        game_time: int,
    ) -> ConstructionSite:
        if command_id in self._command_results:
            cached = self._command_results[command_id]
            if cached.get("materials") != dict(materials):
                # 同 command_id 不同载荷 = 现场库存冲突
                raise ConstructionError("site_inventory_conflict", command_id)
            return self.site_of(building_id)
        building = self._buildings.get(building_id)
        if building.removed or building.physical_state not in ("foundation", "construction"):
            raise ConstructionError("building_state_invalid", building.physical_state)
        if any(count <= 0 for count in materials.values()):
            raise ConstructionError("materials_insufficient", "non-positive count")
        site = self.site_of(building_id)
        # Material Delivery 经 ECON 结算后进现场托管 Inventory
        self._econ.settle_material_delivery(
            f"site.{building_id}", dict(materials), evidence_id=command_id
        )
        for item, count in materials.items():
            site.materials_escrow[item] = site.materials_escrow.get(item, 0) + count
        self._log.append(
            "construction.materials_delivered",
            {"building_id": building_id, "materials": dict(materials)},
            game_time, caused_by_command_id=command_id,
        )
        self._command_results[command_id] = {"building_id": building_id,
                                             "materials": dict(materials)}
        return site

    # -- 劳动 ----------------------------------------------------------------

    def submit_work_session(
        self,
        command_id: str,
        building_id: str,
        profession: str,
        labor_game_minutes: int,
        efficiency_bps: int,
        game_time: int,
        expected_phase: str,
        expected_version: int,
    ) -> ConstructionSite:
        if command_id in self._command_results:
            return self.site_of(building_id)
        building = self._buildings.get(building_id)
        if building.removed or building.physical_state not in ("foundation", "construction"):
            raise ConstructionError("building_state_invalid", building.physical_state)
        if building.version != expected_version:
            raise ConstructionError("version_stale",
                                    f"{building.version} != {expected_version}")
        if building.construction_phase != expected_phase:
            raise ConstructionError(
                "phase_order_violation",
                f"current {building.construction_phase} != {expected_phase}",
            )
        phase = building.construction_phase
        requirements = self._phase_requirements(building, phase)
        professions = requirements.get("professions", {})
        if professions and profession not in professions:
            raise ConstructionError("profession_missing", profession)
        if labor_game_minutes <= 0 or efficiency_bps <= 0:
            raise ConstructionError("requirement_unmet", "non-positive labor/efficiency")

        site = self.site_of(building_id)
        effective = labor_game_minutes * efficiency_bps // 10_000
        site.labor_progress[phase] = site.labor_progress.get(phase, 0) + effective
        site.last_work_game_time = game_time
        site.stalled = False
        site.stall_notified = False
        self._log.append(
            "construction.work_session",
            {"building_id": building_id, "phase": phase, "profession": profession,
             "effective_minutes": effective},
            game_time, caused_by_command_id=command_id,
        )
        self._maybe_complete_phase(building, site, game_time, command_id)
        self._command_results[command_id] = {"building_id": building_id}
        return site

    def _maybe_complete_phase(self, building: Building, site: ConstructionSite,
                              game_time: int, command_id: str) -> None:
        phase = building.construction_phase
        requirements = self._phase_requirements(building, phase)
        if site.labor_progress.get(phase, 0) < requirements.get("labor_game_minutes", 0):
            return
        materials_needed = requirements.get("materials", {})
        for item, count in materials_needed.items():
            if site.materials_escrow.get(item, 0) < count:
                # 材料不足：劳动进度保留，阶段不完成
                self._log.append(
                    "construction.materials_insufficient",
                    {"building_id": building.building_id, "phase": phase,
                     "missing": {i: c for i, c in materials_needed.items()
                                 if site.materials_escrow.get(i, 0) < c}},
                    game_time,
                )
                return
        for item, count in materials_needed.items():
            site.materials_escrow[item] -= count
        if phase == "acceptance":
            # 验收完成：物理状态 → intact，施工结束（几何四件套）
            self._complete_acceptance(building, site, game_time, command_id)
        else:
            self._advance_phase(building, site, game_time, command_id)

    def _advance_phase(self, building: Building, site: ConstructionSite,
                       game_time: int, command_id: str) -> None:
        order = list(CONSTRUCTION_PHASES)
        current = building.construction_phase
        index = order.index(current)
        if index + 1 >= len(order):
            raise ConstructionError("phase_order_violation", "acceptance already done")
        next_phase = order[index + 1]
        source = {"command_id": command_id, "world_event_id": None}

        def apply_phase() -> None:
            building.construction_phase = next_phase
            building.version += 1

        if current in ("clearing", "foundation_work", "structure_work"):
            # 几何阶段完成：四件套同步；structure_work 后物理状态进入 construction
            def apply() -> None:
                if current == "structure_work":
                    building.physical_state = "construction"
                apply_phase()
            self._buildings.commit_phase_geometry(
                building, current, game_time, source, business_apply=apply,
            )
        else:
            # planning → clearing、fitting → acceptance：无几何变化
            apply_phase()
            self._log.append(
                "construction.phase_advanced",
                {"building_id": building.building_id, "phase": next_phase},
                game_time,
            )

    def _complete_acceptance(self, building: Building, site: ConstructionSite,
                             game_time: int, command_id: str) -> None:
        source = {"command_id": command_id, "world_event_id": None}
        upgrade_target = building.upgrade_target

        def apply() -> None:
            if upgrade_target is not None:
                building.building_template_id = upgrade_target
                building.upgrade_target = None
            building.physical_state = "intact"
            building.construction_phase = None
            building.interior_active = True
            building.version += 1

        self._buildings.commit_acceptance(
            building, game_time, source, business_apply=apply,
            to_template_id=upgrade_target,
        )
        building.check_invariant()

    # -- 升级 ----------------------------------------------------------------

    def start_upgrade(
        self, command_id: str, building_id: str, target_template_id: str,
        game_time: int, expected_version: int,
    ) -> Building:
        if command_id in self._command_results:
            return self._buildings.get(building_id)
        building = self._buildings.get(building_id)
        if building.version != expected_version:
            raise ConstructionError("version_stale",
                                    f"{building.version} != {expected_version}")
        if building.removed or building.physical_state != "intact":
            raise ConstructionError("building_state_invalid", building.physical_state)
        template = self._buildings._templates.get(building.building_template_id)
        if target_template_id not in template.upgrade_to_template_ids:
            # 无降级路径：未注册的升级目标一律拒绝
            raise ConstructionError("upgrade_path_unknown",
                                    f"{building.building_template_id} → {target_template_id}")
        self._buildings._templates.get(target_template_id)  # 目标模板必须已注册
        source = {"command_id": command_id, "world_event_id": None}

        def apply() -> None:
            building.upgrade_target = target_template_id
            building.physical_state = "construction"
            building.construction_phase = "planning"
            building.interior_active = False
            building.version += 1

        self._buildings.commit_upgrade_start(building, game_time, source, business_apply=apply)
        building.check_invariant()
        self.site_of(building_id)  # 确保站点存在
        self._command_results[command_id] = {"building_id": building_id}
        return building

    # -- 停滞检测（TIME 周期） ---------------------------------------------------

    def check_stalled(self, occurrence: dict) -> dict:
        key = occurrence["occurrence_key"]
        if key in self._stall_checks:
            return {"status": "replayed", "result": self._stall_checks[key]}
        game_time = occurrence["game_time"]
        stalled_now: List[str] = []
        for site in self._sites.values():
            building = self._buildings.get(site.building_id)
            if building.removed or building.physical_state not in ("foundation", "construction"):
                continue
            if site.stalled:
                continue
            if game_time - site.last_work_game_time >= CONSTRUCTION_STALLED_GAME_MINUTES:
                site.stalled = True
                if not site.stall_notified:
                    self._resident.notify(
                        f"owner.{building.parcel_id}", "construction_stalled",
                        {"building_id": building.building_id},
                        evidence_id=key,
                    )
                    site.stall_notified = True
                stalled_now.append(building.building_id)
        self._log.append(
            "construction.stall_check",
            {"occurrence_key": key, "stalled": stalled_now},
            game_time,
        )
        result = {"stalled": stalled_now}
        self._stall_checks[key] = result
        return {"status": "processed", "result": result}

    # -- 导出/导入 ------------------------------------------------------------

    def export_state(self) -> dict:
        return {
            "sites": {bid: s.to_dict() for bid, s in self._sites.items()},
            "command_results": copy.deepcopy(self._command_results),
            "stall_checks": copy.deepcopy(self._stall_checks),
        }

    def import_state(self, data: dict) -> None:
        self._sites = {
            bid: ConstructionSite.from_dict(s) for bid, s in data["sites"].items()
        }
        self._command_results = copy.deepcopy(data["command_results"])
        self._stall_checks = copy.deepcopy(data["stall_checks"])
