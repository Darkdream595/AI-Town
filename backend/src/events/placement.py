"""
建造放置校验链（DOC-EVENT-008）

- Deed build 权利或 Appropriation 证据 → Zoning → Footprint（Orientation 变换）→
  相交 → Entrance 邻接 Walkability → Critical Route Gate → parcel 已清理
- 全部校验在 Candidate Snapshot 上；任一失败无任何状态变化
- AI build 提案 strict schema：只有 parcel+模板+预算来源；注入字段一律拒绝
- 提交 = parcel 占用+Building+patch+event+diff 单一事务，带 expected_revision + 幂等
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Tuple

from .buildings import Building, BuildingError, BuildingService
from .constants import ORIENTATIONS


class PlacementError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass
class Parcel:
    parcel_id: str
    scene_id: str
    region_id: str
    zoning: frozenset
    bounds: dict  # {x, y, w, h}
    reserved: bool = False

    def to_dict(self) -> dict:
        return {
            "parcel_id": self.parcel_id,
            "scene_id": self.scene_id,
            "region_id": self.region_id,
            "zoning": sorted(self.zoning),
            "bounds": dict(self.bounds),
            "reserved": self.reserved,
        }

    @staticmethod
    def from_dict(data: dict) -> "Parcel":
        return Parcel(
            parcel_id=data["parcel_id"],
            scene_id=data["scene_id"],
            region_id=data["region_id"],
            zoning=frozenset(data["zoning"]),
            bounds=dict(data["bounds"]),
            reserved=data["reserved"],
        )


class ParcelRegistry:
    def __init__(self) -> None:
        self._parcels: Dict[str, Parcel] = {}

    def register(self, parcel: Parcel) -> None:
        if parcel.parcel_id in self._parcels:
            raise PlacementError("parcel_duplicate", parcel.parcel_id)
        self._parcels[parcel.parcel_id] = parcel

    def get(self, parcel_id: str) -> Parcel:
        try:
            return self._parcels[parcel_id]
        except KeyError:
            raise PlacementError("parcel_unknown", parcel_id) from None

    def all(self) -> Tuple[Parcel, ...]:
        return tuple(self._parcels.values())


def transformed_size(size: Tuple[int, int], orientation: int) -> Tuple[int, int]:
    """Orientation 0/90/180/270 下的 footprint 尺寸变换"""
    if orientation not in ORIENTATIONS:
        raise PlacementError("orientation_invalid", str(orientation))
    w, h = size
    return (w, h) if orientation in (0, 180) else (h, w)


def rects_intersect(a: dict, b: dict) -> bool:
    return not (
        a["x"] + a["w"] <= b["x"]
        or b["x"] + b["w"] <= a["x"]
        or a["y"] + a["h"] <= b["y"]
        or b["y"] + b["h"] <= a["y"]
    )


def rect_within(inner: dict, outer: dict) -> bool:
    return (
        inner["x"] >= outer["x"]
        and inner["y"] >= outer["y"]
        and inner["x"] + inner["w"] <= outer["x"] + outer["w"]
        and inner["y"] + inner["h"] <= outer["y"] + outer["h"]
    )


#: AI build 提案 strict schema（注入 footprint/permission/owner 一律拒绝）
AI_BUILD_PROPOSAL_FIELDS = frozenset({"parcel_id", "building_template_id", "budget_source"})


def validate_ai_build_proposal(data: object) -> dict:
    if not isinstance(data, dict):
        raise PlacementError("ai_build_proposal_invalid", "not an object")
    extra = set(data) - AI_BUILD_PROPOSAL_FIELDS
    if extra:
        raise PlacementError("ai_build_proposal_invalid", f"injected: {sorted(extra)}")
    missing = AI_BUILD_PROPOSAL_FIELDS - set(data)
    if missing:
        raise PlacementError("ai_build_proposal_invalid", f"missing: {sorted(missing)}")
    if not all(isinstance(data[k], str) for k in AI_BUILD_PROPOSAL_FIELDS):
        raise PlacementError("ai_build_proposal_invalid", "fields must be strings")
    return {"parcel_id": data["parcel_id"],
            "building_template_id": data["building_template_id"],
            "budget_source": data["budget_source"]}


class PlacementService:
    def __init__(
        self,
        parcels: ParcelRegistry,
        buildings: BuildingService,
        econ_port: object,
        map_port: object,
        event_log: object,
        id_factory: Callable[[], str],
    ) -> None:
        self._parcels = parcels
        self._buildings = buildings
        self._econ = econ_port
        self._map = map_port
        self._log = event_log
        self._id_factory = id_factory
        self._command_results: Dict[str, dict] = {}

    def submit_build(
        self,
        command_id: str,
        parcel_id: str,
        building_template_id: str,
        orientation: int,
        footprint_xy: Tuple[int, int],
        budget_source: str,
        expected_revision: int,
        requester_id: str,
        game_time: int,
        appropriation_evidence_id: Optional[str] = None,
    ) -> Building:
        if command_id in self._command_results:
            return self._buildings.get(self._command_results[command_id]["building_id"])
        parcel = self._parcels.get(parcel_id)
        template = self._buildings._templates.get(building_template_id)

        # 1) Deed build 权利或 Appropriation 证据
        if appropriation_evidence_id is None and not self._econ.has_build_right(
            requester_id, parcel_id
        ):
            raise PlacementError("deed_right_missing", f"{requester_id}@{parcel_id}")
        # 2) Zoning
        if not set(template.zoning_tags) <= set(parcel.zoning):
            raise PlacementError(
                "zoning_violation",
                f"{sorted(template.zoning_tags)} ⊄ {sorted(parcel.zoning)}",
            )
        # 3) Footprint 经 Orientation 变换须在 parcel 内
        w, h = transformed_size(template.footprint_wu, orientation)
        footprint = {"x": footprint_xy[0], "y": footprint_xy[1], "w": w, "h": h}
        if not rect_within(footprint, parcel.bounds):
            raise PlacementError("footprint_out_of_parcel", str(footprint))
        # 4) 不与既有建筑/保留区相交
        if parcel.reserved:
            raise PlacementError("overlap_detected", "parcel reserved")
        for other in self._buildings.all():
            if other.scene_id == parcel.scene_id and not other.removed:
                if rects_intersect(footprint, other.footprint):
                    raise PlacementError("overlap_detected", other.building_id)
        # 5) Entrance 邻接 Walkability（候选快照上校验）
        if not self._map.entrance_walkable(parcel.scene_id, footprint):
            raise PlacementError("entrance_unreachable", str(footprint))
        # 6) Critical Route Gate：候选操作集不得切断注册关键路径
        candidate_ops = self._candidate_ops(parcel.scene_id, footprint)
        if not self._map.critical_routes_intact(parcel.scene_id, candidate_ops):
            raise PlacementError("critical_route_cut", parcel_id)
        # 7) parcel 已清理（瓦砾清完）
        if self._buildings.parcel_has_rubble(parcel_id):
            raise PlacementError("parcel_not_cleared", parcel_id)
        # 8) expected_revision
        if self._map.current_revision(parcel.scene_id) != expected_revision:
            raise PlacementError("stale_revision", parcel.scene_id)

        try:
            building = self._buildings.create_at_placement(
                command_id=command_id,
                building_template_id=building_template_id,
                scene_id=parcel.scene_id,
                parcel_id=parcel_id,
                footprint=footprint,
                orientation=orientation,
                game_time=game_time,
                expected_revision=expected_revision,
            )
        except BuildingError as exc:
            if exc.code == "stale_revision":
                raise PlacementError("stale_revision", parcel.scene_id) from None
            raise
        self._econ.settle_build_budget(
            budget_source, building.building_id, template.rebuild_cost,
            evidence_id=command_id,
        )
        self._command_results[command_id] = {"building_id": building.building_id}
        return building

    def _candidate_ops(self, scene_id: str, footprint: dict) -> list:
        """供 Critical Route Gate 审计的候选 collision 操作"""
        return [{
            "op": "add", "layer": "collision",
            "object_id": f"candidate.{self._id_factory()}",
            "object_template_id": "collision.building.planned",
            "value": {
                "shape_type": "polygon",
                "outer_ring_wu": [
                    [footprint["x"], footprint["y"]],
                    [footprint["x"] + footprint["w"], footprint["y"]],
                    [footprint["x"] + footprint["w"], footprint["y"] + footprint["h"]],
                    [footprint["x"], footprint["y"] + footprint["h"]],
                ],
                "obstacle_tag": "building.planned",
            },
            "prior": None,
        }]

    def export_state(self) -> dict:
        return {"command_results": copy.deepcopy(self._command_results)}

    def import_state(self, data: dict) -> None:
        self._command_results = copy.deepcopy(data["command_results"])
