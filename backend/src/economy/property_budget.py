"""
财产、建筑引用与公共预算（DOC-ECON-011）

- RULE-ECON-041：每个 Property Subject 最多一份 active Deed
- RULE-ECON-042：Deed 转移必须验证同意/裁定；镇长不能直接没收
- RULE-ECON-043：spent + active_encumbrance <= authorized；三处金额一致
- RULE-ECON-044：Building 阶段归 EVENT；ECON 只结算经济资源
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..foundation import generate_ulid
from .constants import AppropriationState, EncumbranceState, PropertySubjectKind


class PropertyError(Exception):
    """财产/预算操作失败；code 为稳定 reason code"""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True)
class PropertySubject:
    subject_kind: PropertySubjectKind
    subject_id: str
    subject_version: int


@dataclass
class PropertyDeed:
    """DES-ECON-011 的运行时形态"""

    deed_item_id: str
    subject: PropertySubject
    rights: Tuple[str, ...]
    owner_entity_id: str
    issued_event_id: str
    state: str = "active"
    schema_version: int = 1


class DeedRegistry:
    """RULE-ECON-041/042：Deed 唯一性与转移授权"""

    def __init__(self) -> None:
        self._deeds: Dict[str, PropertyDeed] = {}
        self._command_results: Dict[str, PropertyDeed] = {}

    def issue_deed(
        self,
        command_id: str,
        subject: PropertySubject,
        rights: Tuple[str, ...],
        owner_entity_id: str,
        issued_event_id: str,
    ) -> PropertyDeed:
        if command_id in self._command_results:
            return self._command_results[command_id]
        if self.active_deed_count(subject.subject_id) >= 1:
            raise PropertyError(
                "deed_conflict", f"subject {subject.subject_id} already has active deed"
            )
        deed = PropertyDeed(
            deed_item_id=generate_ulid(),
            subject=subject,
            rights=rights,
            owner_entity_id=owner_entity_id,
            issued_event_id=issued_event_id,
        )
        self._deeds[deed.deed_item_id] = deed
        self._command_results[command_id] = deed
        return deed

    def active_deed_count(self, subject_id: str) -> int:
        return sum(
            1
            for d in self._deeds.values()
            if d.subject.subject_id == subject_id and d.state == "active"
        )

    def transfer_deed(
        self,
        command_id: str,
        deed_item_id: str,
        new_owner_entity_id: str,
        current_subject_version: int,
        consent_evidence_id: Optional[str] = None,
        legal_order_id: Optional[str] = None,
    ) -> PropertyDeed:
        """RULE-ECON-042：同意或合法裁定必须居一；越权没收拒绝"""
        deed = self._deeds.get(deed_item_id)
        if deed is None:
            raise PropertyError("property_subject_unknown", deed_item_id)
        if not consent_evidence_id and not legal_order_id:
            raise PropertyError(
                "transfer_consent_missing",
                "transfer requires owner consent or legal order",
            )
        if current_subject_version != deed.subject.subject_version:
            raise PropertyError(
                "property_version_stale",
                f"expected {deed.subject.subject_version}, got {current_subject_version}",
            )
        deed.owner_entity_id = new_owner_entity_id
        return deed


@dataclass
class Appropriation:
    """DES-ECON-011：预算授权（version 单调）"""

    appropriation_id: str
    public_account_id: str
    purpose_id: str
    authorized_copper_feather: int
    starts_at_game_time: int
    expires_at_game_time: int
    approval_evidence_id: str
    spent_copper_feather: int = 0
    active_encumbrance_copper_feather: int = 0
    state: AppropriationState = AppropriationState.DRAFT
    version: int = 0


@dataclass
class Encumbrance:
    """DES-ECON-011：字段集合固定，拒绝额外字段"""

    encumbrance_id: str
    appropriation_id: str
    public_account_id: str
    owner_command_id: str
    purpose_id: str
    amount_copper_feather: int
    created_game_time: int
    expires_at_game_time: int
    state: EncumbranceState = EncumbranceState.ACTIVE
    version: int = 1
    schema_version: int = 1


class BudgetLedger:
    """
    RULE-ECON-043：两层限制（账户余额 + 授权上限）同时强制。

    锁顺序固定 appropriation -> encumbrance -> public_account；
    encumber/consume/release/expire 与计数更新同一事务。
    """

    def __init__(self) -> None:
        self._appropriations: Dict[str, Appropriation] = {}
        self._encumbrances: Dict[str, Encumbrance] = {}
        self._command_results: Dict[str, object] = {}

    def create_appropriation(
        self,
        command_id: str,
        public_account_id: str,
        purpose_id: str,
        authorized_copper_feather: int,
        starts_at_game_time: int,
        expires_at_game_time: int,
        approval_evidence_id: str,
    ) -> Appropriation:
        appropriation = Appropriation(
            appropriation_id=generate_ulid(),
            public_account_id=public_account_id,
            purpose_id=purpose_id,
            authorized_copper_feather=authorized_copper_feather,
            starts_at_game_time=starts_at_game_time,
            expires_at_game_time=expires_at_game_time,
            approval_evidence_id=approval_evidence_id,
        )
        self._appropriations[appropriation.appropriation_id] = appropriation
        return appropriation

    def activate_appropriation(self, command_id: str, appropriation_id: str) -> Appropriation:
        appropriation = self._require_appropriation(appropriation_id)
        if appropriation.state is not AppropriationState.DRAFT:
            raise PropertyError(
                "appropriation_missing", f"cannot activate from {appropriation.state.value}"
            )
        appropriation.state = AppropriationState.ACTIVE
        appropriation.version += 1
        return appropriation

    def _require_appropriation(self, appropriation_id: str) -> Appropriation:
        appropriation = self._appropriations.get(appropriation_id)
        if appropriation is None:
            raise PropertyError("appropriation_missing", appropriation_id)
        return appropriation

    def _require_encumbrance(self, encumbrance_id: str) -> Encumbrance:
        encumbrance = self._encumbrances.get(encumbrance_id)
        if encumbrance is None:
            raise PropertyError("encumbrance_state_invalid", encumbrance_id)
        return encumbrance

    # -- Encumbrance 生命周期 --

    def encumber(
        self,
        command_id: str,
        appropriation_id: str,
        amount_copper_feather: int,
        expected_version: int,
        created_game_time: int,
        expires_at_game_time: int,
        purpose_id: str,
        public_account_id: str,
    ) -> Encumbrance:
        """§7：并发竞争同一剩余额度时只有一个能成功"""
        if command_id in self._command_results:
            return self._command_results[command_id]  # type: ignore[return-value]
        appropriation = self._require_appropriation(appropriation_id)
        if appropriation.state is not AppropriationState.ACTIVE:
            raise PropertyError(
                "appropriation_missing",
                f"appropriation not active ({appropriation.state.value})",
            )
        if expected_version != appropriation.version:
            raise PropertyError(
                "encumbrance_mismatch",
                f"expected version {expected_version}, at {appropriation.version}",
            )
        if amount_copper_feather <= 0:
            raise PropertyError("appropriation_exceeded", "amount must be > 0")
        if (
            appropriation.spent_copper_feather
            + appropriation.active_encumbrance_copper_feather
            + amount_copper_feather
            > appropriation.authorized_copper_feather
        ):
            raise PropertyError(
                "appropriation_exceeded",
                f"spent+active+{amount_copper_feather} > {appropriation.authorized_copper_feather}",
            )
        if purpose_id != appropriation.purpose_id or public_account_id != appropriation.public_account_id:
            raise PropertyError(
                "encumbrance_mismatch", "account/purpose must equal appropriation"
            )
        encumbrance = Encumbrance(
            encumbrance_id=generate_ulid(),
            appropriation_id=appropriation_id,
            public_account_id=public_account_id,
            owner_command_id=command_id,
            purpose_id=purpose_id,
            amount_copper_feather=amount_copper_feather,
            created_game_time=created_game_time,
            expires_at_game_time=expires_at_game_time,
        )
        # 创建与 active_encumbrance += amount 同一事务
        self._encumbrances[encumbrance.encumbrance_id] = encumbrance
        appropriation.active_encumbrance_copper_feather += amount_copper_feather
        appropriation.version += 1
        self._command_results[command_id] = encumbrance
        return encumbrance

    def consume_encumbrance(
        self,
        command_id: str,
        encumbrance_id: str,
        expected_version: int,
        appropriation_expected_version: int,
    ) -> Encumbrance:
        """consume 与 active-=amount、spent+=amount 同一事务"""
        if command_id in self._command_results:
            return self._command_results[command_id]  # type: ignore[return-value]
        encumbrance = self._require_encumbrance(encumbrance_id)
        if encumbrance.state is not EncumbranceState.ACTIVE:
            raise PropertyError(
                "encumbrance_state_invalid", encumbrance.state.value
            )
        appropriation = self._require_appropriation(encumbrance.appropriation_id)
        if (
            expected_version != encumbrance.version
            or appropriation_expected_version != appropriation.version
        ):
            raise PropertyError("encumbrance_mismatch", "version mismatch")
        encumbrance.state = EncumbranceState.CONSUMED
        appropriation.active_encumbrance_copper_feather -= encumbrance.amount_copper_feather
        appropriation.spent_copper_feather += encumbrance.amount_copper_feather
        appropriation.version += 1
        if (
            appropriation.spent_copper_feather
            >= appropriation.authorized_copper_feather
        ):
            appropriation.state = AppropriationState.EXHAUSTED
        self._command_results[command_id] = encumbrance
        return encumbrance

    def release_encumbrance(self, command_id: str, encumbrance_id: str) -> Encumbrance:
        """阶段失败原子释放：只执行 active_encumbrance -= amount"""
        if command_id in self._command_results:
            return self._command_results[command_id]  # type: ignore[return-value]
        encumbrance = self._require_encumbrance(encumbrance_id)
        if encumbrance.state is not EncumbranceState.ACTIVE:
            raise PropertyError(
                "encumbrance_state_invalid", encumbrance.state.value
            )
        appropriation = self._require_appropriation(encumbrance.appropriation_id)
        encumbrance.state = EncumbranceState.RELEASED
        appropriation.active_encumbrance_copper_feather -= encumbrance.amount_copper_feather
        appropriation.version += 1
        self._command_results[command_id] = encumbrance
        return encumbrance

    def expire_overdue(self, current_game_time: int) -> Tuple[List[str], List[str]]:
        """§7：Appropriation 到期时已 committed 保留，active Encumbrance 释放"""
        expired_encumbrances: List[str] = []
        expired_appropriations: List[str] = []
        for encumbrance in self._encumbrances.values():
            if (
                encumbrance.state is EncumbranceState.ACTIVE
                and current_game_time > encumbrance.expires_at_game_time
            ):
                appropriation = self._require_appropriation(encumbrance.appropriation_id)
                encumbrance.state = EncumbranceState.EXPIRED
                appropriation.active_encumbrance_copper_feather -= encumbrance.amount_copper_feather
                appropriation.version += 1
                expired_encumbrances.append(encumbrance.encumbrance_id)
        for appropriation in self._appropriations.values():
            if (
                appropriation.state is AppropriationState.ACTIVE
                and current_game_time > appropriation.expires_at_game_time
            ):
                appropriation.state = AppropriationState.EXPIRED
                appropriation.version += 1
                expired_appropriations.append(appropriation.appropriation_id)
        return expired_encumbrances, expired_appropriations

    # -- 不变量与恢复审计 --

    def assert_invariant(self, appropriation_id: str) -> None:
        appropriation = self._require_appropriation(appropriation_id)
        if (
            appropriation.spent_copper_feather
            + appropriation.active_encumbrance_copper_feather
            > appropriation.authorized_copper_feather
        ):
            raise PropertyError(
                "appropriation_exceeded", "spent + active > authorized"
            )

    def orphan_encumbrance_count(self, appropriation_id: str) -> int:
        """恢复审计：active Encumbrance 总额必须与计数一致"""
        appropriation = self._require_appropriation(appropriation_id)
        active_sum = sum(
            e.amount_copper_feather
            for e in self._encumbrances.values()
            if e.appropriation_id == appropriation_id
            and e.state is EncumbranceState.ACTIVE
        )
        return abs(active_sum - appropriation.active_encumbrance_copper_feather)
