"""
镇长治理权限、预算与信息边界（DOC-PLAYER-008）

- RULE-PLAYER-036：MayorCommand 要求 mayor_active + active office +
  jurisdiction + policy capability + 最新 authority version
- RULE-PLAYER-037：公共支出受 Appropriation + Encumbrance + public balance
  三重约束；不能 mint、负余额或跳过 Transaction
- RULE-PLAYER-038：镇长不能读私人记忆/secret/私人 Inventory/隐藏关系
- RULE-PLAYER-039：不能强制感情/没收财产/指定胜负/set stage/改 Collision/
  伪造 WorldEvent
- RULE-PLAYER-040：紧急治理须注册 policy、上限、期限、reason 与事后审计
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Dict, Optional, Set, Tuple

from ..foundation import generate_ulid
from .mode import PlayerMode


class MayorCommandError(Exception):
    """MayorCommand 校验失败；code 为稳定 reason code"""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


#: §5.1：后端注册 union 全集
MAYOR_COMMAND_TYPES = frozenset(
    {
        "mayor.budget.propose",
        "mayor.tax.propose",
        "mayor.wage.propose",
        "mayor.public_work.propose",
        "mayor.notice.publish",
        "mayor.festival.schedule",
        "mayor.emergency.respond",
        "mayor.statistics.query",
    }
)

#: §5.1 每型 strict payload 必填字段（拒绝额外字段）
_PAYLOAD_SCHEMAS: Dict[str, frozenset] = {
    "mayor.budget.propose": frozenset(
        {"office_id", "expected_office_version", "jurisdiction_id", "purpose_id",
         "maximum_budget_copper_feather"}
    ),
    "mayor.tax.propose": frozenset(
        {"office_id", "expected_office_version", "jurisdiction_id", "tax_policy_id",
         "effective_game_time"}
    ),
    "mayor.wage.propose": frozenset(
        {"office_id", "expected_office_version", "jurisdiction_id", "wage_policy_id",
         "effective_game_time"}
    ),
    "mayor.public_work.propose": frozenset(
        {"office_id", "expected_office_version", "jurisdiction_id", "public_subject_id",
         "purpose_id", "maximum_budget_copper_feather", "requested_completion_game_time"}
    ),
    "mayor.notice.publish": frozenset(
        {"office_id", "expected_office_version", "jurisdiction_id", "content_id"}
    ),
    "mayor.festival.schedule": frozenset(
        {"office_id", "expected_office_version", "jurisdiction_id", "festival_template_id",
         "scheduled_game_time"}
    ),
    "mayor.emergency.respond": frozenset(
        {"office_id", "expected_office_version", "jurisdiction_id", "emergency_policy_id",
         "reason_code", "expires_game_time", "maximum_budget_copper_feather"}
    ),
    "mayor.statistics.query": frozenset(
        {"office_id", "expected_office_version", "jurisdiction_id", "query_kind"}
    ),
}

#: RULE-PLAYER-039：镇长禁止的 direct mutation 动作集合
_MAYOR_FORBIDDEN_ACTIONS = frozenset(
    {
        "set_affection",
        "confiscate_property",
        "force_combat_outcome",
        "set_building_stage",
        "edit_collision",
        "forge_world_event",
        "mint_currency",
        "set_balance",
    }
)

#: RULE-PLAYER-038：Public Projection / statistics 禁止出现的字段
_FORBIDDEN_PUBLIC_FIELDS = frozenset(
    {
        "private_memory",
        "personal_secret",
        "shared_secret",
        "private_inventory",
        "private_transaction",
        "relationship_raw",
        "undisclosed_health",
    }
)

#: RULE-PLAYER-040：注册的紧急响应 policy（首版白名单）
REGISTERED_EMERGENCY_POLICIES = frozenset(
    {"emergency.fire_response", "emergency.flood_response", "emergency.quarantine"}
)

EMERGENCY_BUDGET_CAP_COPPER = 20_000


@dataclass(frozen=True)
class MayorCommand:
    """§5.1 MayorCommand Schema；与 PlayerCommand/AdminCommand 不相容"""

    command_id: str
    world_id: str
    expected_revision: int
    type: str
    payload: dict
    protocol_version: int = 1

    def __post_init__(self) -> None:
        if self.protocol_version != 1:
            raise MayorCommandError("MAYOR_PROTOCOL_VERSION_UNSUPPORTED")
        if self.type not in MAYOR_COMMAND_TYPES:
            raise MayorCommandError(
                "MAYOR_COMMAND_TYPE_UNREGISTERED", f"unknown type {self.type!r}"
            )
        required = _PAYLOAD_SCHEMAS[self.type]
        keys = set(self.payload)
        if keys != required:
            # 每型 strict Schema：缺字段或多字段同样拒绝
            raise MayorCommandError(
                "MAYOR_PAYLOAD_SCHEMA_MISMATCH",
                f"{self.type} requires exactly {sorted(required)}, got {sorted(keys)}",
            )

    def payload_hash(self) -> str:
        canonical = json.dumps(
            {"type": self.type, "payload": self.payload, "world_id": self.world_id},
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class MayorOffice:
    """§3：WORLD 授予特定 Resident 的 versioned 治理职位"""

    office_id: str
    holder_resident_id: str
    jurisdiction_ids: Set[str]
    version: int
    active: bool = True


@dataclass
class PublicBudgetState:
    """
    RULE-PLAYER-037 三重约束的状态载体。

    额度竞争通过 try_encumber 的原子检查保证：两个拨款竞争时最多一个成功。
    """

    balance_copper_feather: int
    appropriation_limit_copper_feather: int
    appropriation_version: int = 1
    _encumbered: int = 0
    _active_encumbrances: Dict[str, int] = field(default_factory=dict)

    @property
    def encumbered_copper_feather(self) -> int:
        return self._encumbered

    @property
    def available_copper_feather(self) -> int:
        return min(
            self.balance_copper_feather,
            self.appropriation_limit_copper_feather - self._encumbered,
        )

    def try_encumber(self, encumbrance_id: str, amount: int) -> None:
        """
        原子三重检查：amount <= 余额、<= 剩余 appropriation、且不为负。

        满足即登记 Encumbrance；任一不满足整体失败，无部分支出。
        """
        if amount <= 0:
            raise MayorCommandError("MAYOR_BUDGET_AMOUNT_INVALID")
        if encumbrance_id in self._active_encumbrances:
            raise MayorCommandError("MAYOR_ENCUMBRANCE_DUPLICATE")
        if amount > self.balance_copper_feather:
            raise MayorCommandError(
                "MAYOR_BUDGET_INSUFFICIENT_BALANCE",
                "public account balance insufficient",
            )
        if self._encumbered + amount > self.appropriation_limit_copper_feather:
            raise MayorCommandError(
                "MAYOR_BUDGET_EXCEEDS_APPROPRIATION",
                "appropriation limit would be exceeded",
            )
        self._active_encumbrances[encumbrance_id] = amount
        self._encumbered += amount

    def release_encumbrance(self, encumbrance_id: str) -> int:
        """§8：Saga 失败时释放 active Encumbrance"""
        amount = self._active_encumbrances.pop(encumbrance_id, 0)
        self._encumbered -= amount
        return amount

    def settle_encumbrance(self, encumbrance_id: str) -> int:
        """成交：扣减余额并释放 Encumbrance（守恒：转入受款方由 ECON 负责）"""
        amount = self.release_encumbrance(encumbrance_id)
        self.balance_copper_feather -= amount
        return amount


@dataclass(frozen=True)
class GovernanceAuditRecord:
    """§9：每个 MayorCommand 的治理审计（不是 Sandbox Admin audit）"""

    record_id: str
    office_id: str
    authority_version: int
    jurisdiction_id: str
    policy_id: str
    result: str  # proposed / denied / committed
    reason: str
    correlation_id: str


class MayorCommandValidator:
    """MayorCommand 授权与预算校验（§6 第 4 步）"""

    def __init__(self) -> None:
        self._audit: list[GovernanceAuditRecord] = []
        # (world_id, command_id) -> (payload_hash, 原 decision 记录)
        self._idempotency: Dict[Tuple[str, str], Tuple[str, GovernanceAuditRecord]] = {}

    @property
    def audit_records(self) -> Tuple[GovernanceAuditRecord, ...]:
        return tuple(self._audit)

    def validate(
        self,
        command: MayorCommand,
        mode: PlayerMode,
        office: Optional[MayorOffice],
        authority_version: int,
        budget: Optional[PublicBudgetState] = None,
        correlation_id: Optional[str] = None,
    ) -> GovernanceAuditRecord:
        """
        RULE-PLAYER-036：五重授权检查全过才进入 owner 校验。

        返回治理审计记录；拒绝也记录（§9 decision 记录 result/reason）。
        """
        correlation = correlation_id or generate_ulid()

        cached = self._idempotency.get((command.world_id, command.command_id))
        if cached is not None:
            cached_hash, cached_record = cached
            if cached_hash != command.payload_hash():
                raise MayorCommandError(
                    "MAYOR_COMMAND_ID_CONFLICT",
                    "same command id with different payload",
                )
            # §7：相同幂等 key 相同 payload 返回原 decision，不重复 encumber
            return cached_record

        try:
            self._check_authority(command, mode, office, authority_version)
            encumbrance_id: Optional[str] = None
            if command.type in ("mayor.budget.propose", "mayor.public_work.propose"):
                encumbrance_id = self._check_budget(command, budget)
            if command.type == "mayor.emergency.respond":
                encumbrance_id = self._check_emergency(command, budget)
        except MayorCommandError as exc:
            self._record(
                command, office, authority_version, "denied", exc.code, correlation
            )
            raise

        record = self._record(
            command, office, authority_version, "proposed", "ok", correlation
        )
        self._idempotency[(command.world_id, command.command_id)] = (
            command.payload_hash(),
            record,
        )
        return record

    def _check_authority(
        self,
        command: MayorCommand,
        mode: PlayerMode,
        office: Optional[MayorOffice],
        authority_version: int,
    ) -> None:
        if mode is not PlayerMode.MAYOR_ACTIVE:
            raise MayorCommandError(
                "MAYOR_MODE_REQUIRED", "MayorCommand requires mayor_active"
            )
        if office is None or not office.active:
            raise MayorCommandError(
                "MAYOR_OFFICE_INACTIVE", "no active mayor office"
            )
        if command.payload["office_id"] != office.office_id:
            raise MayorCommandError("MAYOR_OFFICE_MISMATCH")
        if command.payload["expected_office_version"] != office.version:
            raise MayorCommandError(
                "MAYOR_OFFICE_VERSION_STALE",
                f"expected office version {command.payload['expected_office_version']}, "
                f"current {office.version}",
            )
        if authority_version != office.version:
            raise MayorCommandError(
                "MAYOR_AUTHORITY_VERSION_STALE",
                "authority version mismatch; proposals invalidated",
            )
        if command.payload["jurisdiction_id"] not in office.jurisdiction_ids:
            raise MayorCommandError(
                "MAYOR_JURISDICTION_MISMATCH",
                f"{command.payload['jurisdiction_id']} outside jurisdiction",
            )

    def _check_budget(
        self, command: MayorCommand, budget: Optional[PublicBudgetState]
    ) -> str:
        if budget is None:
            raise MayorCommandError("MAYOR_BUDGET_STATE_REQUIRED")
        amount = command.payload["maximum_budget_copper_feather"]
        encumbrance_id = generate_ulid()
        # RULE-PLAYER-037：余额 + Appropriation + Encumbrance 三重约束原子检查
        budget.try_encumber(encumbrance_id, amount)
        return encumbrance_id

    def _check_emergency(
        self, command: MayorCommand, budget: Optional[PublicBudgetState]
    ) -> str:
        """RULE-PLAYER-040：注册 policy + 上限 + 期限 + reason 缺一不可"""
        policy_id = command.payload["emergency_policy_id"]
        if policy_id not in REGISTERED_EMERGENCY_POLICIES:
            raise MayorCommandError(
                "MAYOR_EMERGENCY_POLICY_UNREGISTERED",
                f"{policy_id} not a registered emergency policy",
            )
        if not command.payload["reason_code"]:
            raise MayorCommandError("MAYOR_EMERGENCY_REASON_REQUIRED")
        amount = command.payload["maximum_budget_copper_feather"]
        if amount > EMERGENCY_BUDGET_CAP_COPPER:
            raise MayorCommandError(
                "MAYOR_EMERGENCY_CAP_EXCEEDED",
                f"emergency budget cap {EMERGENCY_BUDGET_CAP_COPPER}",
            )
        if command.payload["expires_game_time"] <= 0:
            raise MayorCommandError("MAYOR_EMERGENCY_DEADLINE_REQUIRED")
        return self._check_budget(command, budget)

    def _record(
        self,
        command: MayorCommand,
        office: Optional[MayorOffice],
        authority_version: int,
        result: str,
        reason: str,
        correlation_id: str,
    ) -> GovernanceAuditRecord:
        record = GovernanceAuditRecord(
            record_id=generate_ulid(),
            office_id=command.payload.get("office_id", ""),
            authority_version=authority_version,
            jurisdiction_id=command.payload.get("jurisdiction_id", ""),
            policy_id=command.type,
            result=result,
            reason=reason,
            correlation_id=correlation_id,
        )
        self._audit.append(record)
        return record

    @staticmethod
    def assert_mayor_cannot(action: str) -> None:
        """RULE-PLAYER-039：direct mutation 与越权动作一律拒绝"""
        if action in _MAYOR_FORBIDDEN_ACTIONS:
            raise MayorCommandError(
                "MAYOR_DIRECT_MUTATION_REJECTED",
                f"mayor cannot perform {action}; use consent/legal/owner workflow",
            )

    @staticmethod
    def filter_public_projection(fields: dict) -> dict:
        """
        RULE-PLAYER-038：Public Projection 只含聚合与公开字段。

        出现禁止字段即拒绝整个投影（fail closed），不做选择性遮蔽后放行。
        """
        bad = _FORBIDDEN_PUBLIC_FIELDS & set(fields)
        if bad:
            raise MayorCommandError(
                "MAYOR_PUBLIC_PROJECTION_DISCLOSURE_VIOLATION",
                f"public projection contains private fields: {sorted(bad)}",
            )
        return dict(fields)
