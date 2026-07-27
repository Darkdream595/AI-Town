"""
职业与工作场所（DOC-ECON-002）

- RULE-ECON-005：11 个必需 ProfessionDefinition，Stable ID 唯一
- RULE-ECON-006：Workplace 只引用 Building/语义节点，不拥有坐标与生命周期
- RULE-ECON-007：同一 worker 同时最多一个 active_shift 排他 Reservation
- RULE-ECON-008：玩家与 AI 同一 Contract/资格/排班/工资规则
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional

from ..foundation import generate_ulid
from .constants import REQUIRED_PROFESSION_IDS, ContractState


class EmploymentError(Exception):
    """职业/合约操作失败；code 为稳定 reason code"""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True)
class ProfessionDefinition:
    """跨存档稳定的职业能力定义（构建期校验）"""

    profession_id: str
    display_name_key: str
    required_capability_ids: FrozenSet[str]
    produced_service_ids: FrozenSet[str]


def _build_catalog() -> Dict[str, ProfessionDefinition]:
    definitions = [
        ProfessionDefinition(pid, f"profession.name.{pid.split('.')[-1]}", frozenset({f"skill.{pid.split('.')[-1]}"}), frozenset())
        for pid in REQUIRED_PROFESSION_IDS
    ]
    catalog = {d.profession_id: d for d in definitions}
    if len(catalog) != len(REQUIRED_PROFESSION_IDS):
        raise EmploymentError("profession_catalog_duplicate", "Stable ID must be unique")
    return catalog


#: 构建期 Catalog；运行时不可变
PROFESSION_CATALOG: Dict[str, ProfessionDefinition] = _build_catalog()


@dataclass
class Workplace:
    """ECON aggregate：只保存引用，不拥有坐标/Building 生命周期"""

    workplace_id: str
    parent_building_id: str
    location_semantic_node_id: str
    position_capacity: int
    service_definition_ids: List[str] = field(default_factory=list)
    required_permission_ids: List[str] = field(default_factory=list)
    available: bool = True


@dataclass
class EmploymentContract:
    """DES-ECON-002 的运行时形态"""

    employment_contract_id: str
    profession_id: str
    worker_resident_id: str
    employer_entity_id: str
    workplace_id: str
    role_id: str
    wage_copper_feather_per_shift: int
    starts_at_game_time: int
    ends_at_game_time: Optional[int]
    state: ContractState
    version: int
    schema_version: int = 1


@dataclass(frozen=True)
class ShiftReservation:
    """RULE-ECON-007：排他 worker_shift + workplace capacity Reservation"""

    worker_reservation_id: str
    workplace_reservation_id: str
    contract_id: str


class EmploymentRegistry:
    """Offer/接受/排班/停职/转职；历史 Contract 永不改写"""

    def __init__(self, workplaces: Optional[Dict[str, Workplace]] = None) -> None:
        self._workplaces: Dict[str, Workplace] = workplaces or {}
        self._contracts: Dict[str, EmploymentContract] = {}
        # worker_id -> 当前 active shift 的 contract_id（排他）
        self._active_shift_by_worker: Dict[str, str] = {}
        # workplace_id -> 当前占用 capacity 的 contract_id 集
        self._shift_occupants: Dict[str, Dict[str, None]] = {}
        self._command_results: Dict[str, object] = {}

    def register_workplace(self, workplace: Workplace) -> None:
        self._workplaces[workplace.workplace_id] = workplace

    def get_workplace(self, workplace_id: str) -> Workplace:
        workplace = self._workplaces.get(workplace_id)
        if workplace is None:
            raise EmploymentError("workplace_unavailable", f"unknown {workplace_id}")
        return workplace

    def get(self, contract_id: str) -> EmploymentContract:
        contract = self._contracts.get(contract_id)
        if contract is None:
            raise EmploymentError("contract_unknown", f"unknown {contract_id}")
        return contract

    # -- Offer 与接受 --

    def offer_contract(
        self,
        command_id: str,
        profession_id: str,
        worker_resident_id: str,
        employer_entity_id: str,
        workplace_id: str,
        role_id: str,
        wage_copper_feather_per_shift: int,
        starts_at_game_time: int,
        ends_at_game_time: Optional[int] = None,
        worker_capability_ids: FrozenSet[str] = frozenset(),
        worker_permission_ids: FrozenSet[str] = frozenset(),
        actor_kind: str = "ai",
    ) -> EmploymentContract:
        """
        RULE-ECON-008：actor_kind（player/ai）不进入任何判定——
        同一资格、许可、工资与排班规则。
        """
        if command_id in self._command_results:
            return self._command_results[command_id]  # type: ignore[return-value]
        profession = PROFESSION_CATALOG.get(profession_id)
        if profession is None:
            raise EmploymentError("profession_unknown", profession_id)
        workplace = self._workplaces.get(workplace_id)
        if workplace is None or not workplace.available:
            raise EmploymentError("workplace_unavailable", workplace_id)
        missing_capabilities = profession.required_capability_ids - set(worker_capability_ids)
        if missing_capabilities:
            raise EmploymentError(
                "qualification_failed", f"missing {sorted(missing_capabilities)}"
            )
        missing_permissions = set(workplace.required_permission_ids) - set(worker_permission_ids)
        if missing_permissions:
            raise EmploymentError(
                "permission_missing", f"missing {sorted(missing_permissions)}"
            )
        contract = EmploymentContract(
            employment_contract_id=generate_ulid(),
            profession_id=profession_id,
            worker_resident_id=worker_resident_id,
            employer_entity_id=employer_entity_id,
            workplace_id=workplace_id,
            role_id=role_id,
            wage_copper_feather_per_shift=wage_copper_feather_per_shift,
            starts_at_game_time=starts_at_game_time,
            ends_at_game_time=ends_at_game_time,
            state=ContractState.OFFERED,
            version=0,
        )
        self._contracts[contract.employment_contract_id] = contract
        self._command_results[command_id] = contract
        return contract

    def accept_contract(
        self, command_id: str, contract_id: str, expected_version: int
    ) -> EmploymentContract:
        contract = self.get(contract_id)
        if contract.version != expected_version:
            raise EmploymentError(
                "stale_revision", f"expected {expected_version}, at {contract.version}"
            )
        if contract.state is not ContractState.OFFERED:
            raise EmploymentError("contract_state_invalid", contract.state.value)
        contract.state = ContractState.ACTIVE
        contract.version += 1
        return contract

    def reject_contract(self, command_id: str, contract_id: str) -> EmploymentContract:
        contract = self.get(contract_id)
        if contract.state is not ContractState.OFFERED:
            raise EmploymentError("contract_state_invalid", contract.state.value)
        contract.state = ContractState.REJECTED
        contract.version += 1
        return contract

    # -- 排他排班 --

    def start_shift(self, command_id: str, contract_id: str, game_time: int) -> ShiftReservation:
        """RULE-ECON-007：worker 排他与 workplace capacity 同时授予才成功"""
        if command_id in self._command_results:
            return self._command_results[command_id]  # type: ignore[return-value]
        contract = self.get(contract_id)
        if contract.state is not ContractState.ACTIVE:
            raise EmploymentError("contract_state_invalid", contract.state.value)
        if contract.worker_resident_id in self._active_shift_by_worker:
            raise EmploymentError(
                "shift_conflict", f"{contract.worker_resident_id} already on shift"
            )
        workplace = self.get_workplace(contract.workplace_id)
        occupants = self._shift_occupants.setdefault(workplace.workplace_id, {})
        if len(occupants) >= workplace.position_capacity:
            raise EmploymentError("capacity_full", workplace.workplace_id)
        self._active_shift_by_worker[contract.worker_resident_id] = contract_id
        occupants[contract_id] = None
        reservation = ShiftReservation(
            worker_reservation_id=generate_ulid(),
            workplace_reservation_id=generate_ulid(),
            contract_id=contract_id,
        )
        self._command_results[command_id] = reservation
        return reservation

    def end_shift(self, command_id: str, contract_id: str) -> None:
        contract = self.get(contract_id)
        self._active_shift_by_worker.pop(contract.worker_resident_id, None)
        occupants = self._shift_occupants.get(contract.workplace_id)
        if occupants is not None:
            occupants.pop(contract_id, None)

    def active_shift_count(self, worker_resident_id: str) -> int:
        return 1 if worker_resident_id in self._active_shift_by_worker else 0

    # -- 停职与转职 --

    def suspend_for_workplace_damage(self, command_id: str, contract_id: str) -> EmploymentContract:
        """§7：Building 损坏/不可达 → suspended；不假定 worker 已到岗"""
        contract = self.get(contract_id)
        if contract.state is not ContractState.ACTIVE:
            raise EmploymentError("contract_state_invalid", contract.state.value)
        self.end_shift(command_id, contract_id)
        contract.state = ContractState.SUSPENDED
        contract.version += 1
        return contract

    def resume_contract(self, command_id: str, contract_id: str) -> EmploymentContract:
        contract = self.get(contract_id)
        if contract.state is not ContractState.SUSPENDED:
            raise EmploymentError("contract_state_invalid", contract.state.value)
        contract.state = ContractState.ACTIVE
        contract.version += 1
        return contract

    def change_profession(
        self,
        command_id: str,
        old_contract_id: str,
        **new_offer_kwargs,
    ) -> EmploymentContract:
        """§6：转职 = 结束旧 Contract + 创建新 Contract，不改写历史"""
        old = self.get(old_contract_id)
        if old.state in (ContractState.ACTIVE, ContractState.SUSPENDED):
            self.end_shift(command_id, old_contract_id)
            old.state = ContractState.ENDED
            old.version += 1
        return self.offer_contract(command_id=f"{command_id}:new", **new_offer_kwargs)

    def history_of(self, worker_resident_id: str) -> List[EmploymentContract]:
        """转职/结束不丢失历史"""
        return [
            c
            for c in self._contracts.values()
            if c.worker_resident_id == worker_resident_id
        ]
