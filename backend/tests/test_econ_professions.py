"""
TEST-ECON-005..008：职业与工作场所（DOC-ECON-002）

- TEST-ECON-005：Profession Catalog 必需集合与唯一性
- TEST-ECON-006：Workplace location/building 引用可解析且不夺取 ownership
- TEST-ECON-007：玩家/AI job parity 与资格/许可拒绝
- TEST-ECON-008：重叠 Contract、capacity、suspend/转职状态机
"""

import pytest

from src.economy import (
    PROFESSION_CATALOG,
    ContractState,
    EmploymentError,
    EmploymentRegistry,
    Workplace,
)
from src.economy.constants import REQUIRED_PROFESSION_IDS

WORKPLACE_ID = "01K1WKPC000000000000000001"


def _registry(capacity=1, permissions=()):
    workplace = Workplace(
        workplace_id=WORKPLACE_ID,
        parent_building_id="building.crown_creek.smithy",
        location_semantic_node_id="semantic_node.crown_creek.smithy",
        position_capacity=capacity,
        service_definition_ids=["service.smith.repair"],
        required_permission_ids=list(permissions),
    )
    return EmploymentRegistry({WORKPLACE_ID: workplace}), workplace


def _offer_kwargs(worker="resident.worker", **overrides):
    kwargs = {
        "profession_id": "profession.blacksmith",
        "worker_resident_id": worker,
        "employer_entity_id": "organization.smithy",
        "workplace_id": WORKPLACE_ID,
        "role_id": "role.blacksmith.journeyman",
        "wage_copper_feather_per_shift": 180,
        "starts_at_game_time": 2880,
        "worker_capability_ids": frozenset({"skill.blacksmith"}),
    }
    kwargs.update(overrides)
    return kwargs


class TestProfessionCatalog:
    """TEST-ECON-005"""

    def test_required_eleven_professions_unique(self):
        assert len(REQUIRED_PROFESSION_IDS) == 11
        assert len(set(REQUIRED_PROFESSION_IDS)) == 11
        assert set(PROFESSION_CATALOG) == set(REQUIRED_PROFESSION_IDS)
        for definition in PROFESSION_CATALOG.values():
            assert definition.display_name_key


class TestWorkplaceReferences:
    """TEST-ECON-006"""

    def test_workplace_holds_references_not_ownership(self):
        _registry_obj, workplace = _registry()
        # 引用可解析为稳定 ID 字符串
        assert workplace.parent_building_id == "building.crown_creek.smithy"
        assert workplace.location_semantic_node_id == "semantic_node.crown_creek.smithy"
        # ECON 不拥有坐标/Building 生命周期：Workplace 无任何坐标/状态写字段
        assert not hasattr(workplace, "x_wu")
        assert not hasattr(workplace, "building_state")


class TestPlayerAiParity:
    """TEST-ECON-007"""

    @pytest.mark.parametrize("actor_kind", ["ai", "player"])
    def test_same_job_same_result(self, actor_kind):
        registry, _workplace = _registry()
        contract = registry.offer_contract(command_id=f"cmd-offer-{actor_kind}", actor_kind=actor_kind, **_offer_kwargs())
        assert contract.state is ContractState.OFFERED
        accepted = registry.accept_contract("cmd-accept", contract.employment_contract_id, expected_version=0)
        assert accepted.state is ContractState.ACTIVE
        assert accepted.wage_copper_feather_per_shift == 180

    @pytest.mark.parametrize("actor_kind", ["ai", "player"])
    def test_unqualified_rejected_identically(self, actor_kind):
        registry, _workplace = _registry()
        with pytest.raises(EmploymentError) as excinfo:
            registry.offer_contract(
                command_id=f"cmd-unq-{actor_kind}",
                actor_kind=actor_kind,
                **_offer_kwargs(worker_capability_ids=frozenset()),
            )
        assert excinfo.value.code == "qualification_failed"

    def test_missing_permission_rejected(self):
        registry, _workplace = _registry(permissions=("permit.smithy",))
        with pytest.raises(EmploymentError) as excinfo:
            registry.offer_contract(command_id="cmd-perm", **_offer_kwargs())
        assert excinfo.value.code == "permission_missing"

    def test_unknown_profession_and_workplace(self):
        registry, _workplace = _registry()
        with pytest.raises(EmploymentError) as excinfo:
            registry.offer_contract(command_id="cmd-p", **_offer_kwargs(profession_id="profession.pirate"))
        assert excinfo.value.code == "profession_unknown"
        with pytest.raises(EmploymentError) as excinfo:
            registry.offer_contract(command_id="cmd-w", **_offer_kwargs(workplace_id="01K1WKPC000000000000000099"))
        assert excinfo.value.code == "workplace_unavailable"


class TestShiftOverlapAndStateMachine:
    """TEST-ECON-008"""

    def _active_contract(self, registry, worker, command_id):
        contract = registry.offer_contract(command_id=command_id, **_offer_kwargs(worker=worker))
        registry.accept_contract(f"{command_id}:acc", contract.employment_contract_id, expected_version=0)
        return contract

    def test_worker_shift_exclusive(self):
        registry, _workplace = _registry(capacity=2)
        first = self._active_contract(registry, "resident.w1", "cmd-c1")
        second = self._active_contract(registry, "resident.w1", "cmd-c2")
        registry.start_shift("cmd-s1", first.employment_contract_id, 2880)
        with pytest.raises(EmploymentError) as excinfo:
            registry.start_shift("cmd-s2", second.employment_contract_id, 2880)
        assert excinfo.value.code == "shift_conflict"
        assert registry.active_shift_count("resident.w1") == 1

    def test_workplace_capacity_full(self):
        registry, _workplace = _registry(capacity=1)
        first = self._active_contract(registry, "resident.w1", "cmd-c1")
        second = self._active_contract(registry, "resident.w2", "cmd-c2")
        registry.start_shift("cmd-s1", first.employment_contract_id, 2880)
        with pytest.raises(EmploymentError) as excinfo:
            registry.start_shift("cmd-s2", second.employment_contract_id, 2880)
        assert excinfo.value.code == "capacity_full"

    def test_suspend_on_workplace_damage_and_resume(self):
        registry, _workplace = _registry()
        contract = self._active_contract(registry, "resident.w1", "cmd-c1")
        registry.start_shift("cmd-s1", contract.employment_contract_id, 2880)
        suspended = registry.suspend_for_workplace_damage("cmd-dmg", contract.employment_contract_id)
        assert suspended.state is ContractState.SUSPENDED
        assert registry.active_shift_count("resident.w1") == 0
        resumed = registry.resume_contract("cmd-rsm", contract.employment_contract_id)
        assert resumed.state is ContractState.ACTIVE

    def test_change_profession_preserves_history(self):
        registry, _workplace = _registry(capacity=2)
        old = self._active_contract(registry, "resident.w1", "cmd-c1")
        new = registry.change_profession(
            "cmd-change",
            old.employment_contract_id,
            **_offer_kwargs(worker="resident.w1", profession_id="profession.carpenter", worker_capability_ids=frozenset({"skill.carpenter"})),
        )
        assert registry.get(old.employment_contract_id).state is ContractState.ENDED
        assert new.state is ContractState.OFFERED
        history = registry.history_of("resident.w1")
        assert len(history) == 2  # 历史不改写
