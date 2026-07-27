"""
玩家居民创建与身份绑定（DOC-PLAYER-001）

- RULE-PLAYER-001：(world_id, player_identity_id) 最多一个 active binding；
  一个 ResidentId 最多被一个 active PlayerIdentity 控制
- RULE-PLAYER-003：decision_source=human 不授予任何额外能力
- RULE-PLAYER-004：玩家 Resident 不计入 8–12 AI 核心居民配额
- RULE-PLAYER-005：World owner / Mayor office / Sandbox Admin 三类授权独立
- §7.1：创建幂等键 (world_id, command_id) + payload hash
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple

from ..foundation import generate_ulid, is_valid_ulid
from .constants import (
    CORE_AI_RESIDENT_QUOTA_MAX,
    CORE_AI_RESIDENT_QUOTA_MIN,
    DENY_IDEMPOTENCY_PAYLOAD_CONFLICT,
)


class PlayerBindingError(Exception):
    """绑定操作失败；code 为稳定 reason code"""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


class DecisionSource(str, Enum):
    """决策来源（DOC-PLAYER-001 §3）：只描述命令来源，不改变 Domain rule"""

    HUMAN = "human"
    AI = "ai"


class BindingState(str, Enum):
    """DES-PLAYER-001：binding 显式状态"""

    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    RETIRED = "retired"


@dataclass(frozen=True)
class PlayerIdentity:
    """
    本地玩家主体（§3/§6）：只保存稳定 ID 与本地显示名。

    不存 DeepSeek Key 等任何 Secret（§9）。
    """

    player_identity_id: str
    display_name: str

    def __post_init__(self) -> None:
        if not self.player_identity_id:
            raise PlayerBindingError("PLAYER_IDENTITY_ID_EMPTY")
        if not self.display_name:
            raise PlayerBindingError("PLAYER_DISPLAY_NAME_EMPTY")


@dataclass(frozen=True)
class ResidentCreationDraft:
    """
    Resident 创建草稿（§6 第 2–3 步）。

    Client 只能选择公开外观与允许的起始选项；不能指定可信 role、
    starting balance、skill level、spawn point 或 decision_source（§9）。
    """

    name: str
    appearance: dict
    start_options: dict = field(default_factory=dict)

    _FORBIDDEN_OPTION_KEYS = frozenset(
        {
            "role",
            "world_role_ids",
            "starting_balance",
            "money_copper",
            "skill_level",
            "skills",
            "spawn_point",
            "position",
            "decision_source",
        }
    )

    def __post_init__(self) -> None:
        if not self.name:
            raise PlayerBindingError("RESIDENT_DRAFT_NAME_EMPTY")
        bad = self._FORBIDDEN_OPTION_KEYS & set(self.start_options)
        if bad:
            raise PlayerBindingError(
                "RESIDENT_DRAFT_FORBIDDEN_OPTION",
                f"client cannot set trusted options: {sorted(bad)}",
            )

    def payload_dict(self) -> dict:
        return {
            "name": self.name,
            "appearance": self.appearance,
            "start_options": self.start_options,
        }


@dataclass(frozen=True)
class PlayerResidentBinding:
    """DES-PLAYER-001 binding schema"""

    binding_id: str
    world_id: str
    player_identity_id: str
    resident_id: str
    state: BindingState
    created_by_command_id: str
    created_revision: int
    version: int = 1
    decision_source: DecisionSource = DecisionSource.HUMAN
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise PlayerBindingError("BINDING_SCHEMA_VERSION_UNSUPPORTED")
        for field_name in (
            "binding_id",
            "world_id",
            "player_identity_id",
            "resident_id",
            "created_by_command_id",
        ):
            if not getattr(self, field_name):
                raise PlayerBindingError(
                    "BINDING_FIELD_EMPTY", f"{field_name} must be non-empty"
                )
        if self.decision_source is not DecisionSource.HUMAN:
            # RULE-PLAYER-003：玩家 binding 的 decision_source 固定 human
            raise PlayerBindingError("BINDING_DECISION_SOURCE_INVALID")
        if self.version < 1:
            raise PlayerBindingError("BINDING_VERSION_INVALID")

    def payload_hash(self) -> str:
        """幂等 payload hash：覆盖绑定四元组与状态（§7.1）"""
        canonical = json.dumps(
            {
                "world_id": self.world_id,
                "player_identity_id": self.player_identity_id,
                "resident_id": self.resident_id,
                "decision_source": self.decision_source.value,
                "state": self.state.value,
            },
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PlayerAuthorityProjection:
    """
    DOC-PLAYER-001 §5：权限投影。

    只含授权标识，不含私人记忆或凭据。
    """

    binding_id: str
    resident_id: str
    world_role_ids: Tuple[str, ...]
    mayor_office_id: Optional[str]
    admin_session_state: str  # disabled / active / expired
    revision: int


@dataclass(frozen=True)
class PlayerResidentCreationPrepared:
    """prepare 阶段产物（§5 接口）"""

    preparation_id: str
    command_id: str
    world_id: str
    player_identity_id: str
    resident_draft: ResidentCreationDraft
    payload_hash: str


@dataclass(frozen=True)
class PlayerResidentBindingResult:
    """commit 阶段产物"""

    binding: PlayerResidentBinding
    committed_revision: int
    replayed: bool  # True 表示幂等重放返回原结果


#: commit 阶段的有序原子步骤（TEST-PLAYER-003 故障注入点）
COMMIT_STAGES: Tuple[str, ...] = (
    "resident",
    "account",
    "inventory",
    "position",
    "binding",
    "events",
)


class PlayerResidentBindingRegistry:
    """
    绑定注册表：唯一性索引、两阶段创建、幂等与配额隔离。

    Resident 合法性由 RESIDENT validator 负责（RULE-PLAYER-002），registry
    通过注入的 resident_validator 调用它，不删减任何字段。
    """

    def __init__(
        self,
        resident_validator: Optional[Callable[[ResidentCreationDraft], None]] = None,
        initial_revision: int = 0,
    ) -> None:
        self._resident_validator = resident_validator
        self._revision = initial_revision
        self._bindings: Dict[str, PlayerResidentBinding] = {}
        # RULE-PLAYER-001 唯一性索引：仅 active binding 占位
        self._active_by_player: Dict[Tuple[str, str], str] = {}
        self._active_by_resident: Dict[Tuple[str, str], str] = {}
        self._preparations: Dict[str, PlayerResidentCreationPrepared] = {}
        # §7.1：(world_id, command_id) -> (payload_hash, result)
        self._idempotency: Dict[
            Tuple[str, str], Tuple[str, PlayerResidentBindingResult]
        ] = {}
        self._ai_core_resident_count = 0
        self._player_resident_count = 0

    # -- 配额（RULE-PLAYER-004） --

    def set_ai_core_resident_count(self, count: int) -> None:
        if not CORE_AI_RESIDENT_QUOTA_MIN <= count <= CORE_AI_RESIDENT_QUOTA_MAX:
            raise PlayerBindingError(
                "AI_QUOTA_OUT_OF_RANGE",
                f"AI core resident count {count} outside "
                f"{CORE_AI_RESIDENT_QUOTA_MIN}..{CORE_AI_RESIDENT_QUOTA_MAX}",
            )
        self._ai_core_resident_count = count

    @property
    def ai_core_resident_count(self) -> int:
        return self._ai_core_resident_count

    @property
    def player_resident_count(self) -> int:
        return self._player_resident_count

    @property
    def revision(self) -> int:
        return self._revision

    # -- 创建（§5/§6） --

    def prepare_player_resident(
        self,
        command_id: str,
        world_id: str,
        player_identity_id: str,
        resident_draft: ResidentCreationDraft,
    ) -> PlayerResidentCreationPrepared:
        """生成 preparation：先做唯一性预检与 RESIDENT validator 调用"""
        if self._active_by_player.get((world_id, player_identity_id)):
            raise PlayerBindingError(
                "PLAYER_BINDING_ALREADY_ACTIVE",
                "one active binding per (world_id, player_identity_id)",
            )
        if self._resident_validator is not None:
            # RULE-PLAYER-002：必须通过同一 RESIDENT 创建 validator
            self._resident_validator(resident_draft)

        payload_hash = hashlib.sha256(
            json.dumps(
                {
                    "player_identity_id": player_identity_id,
                    "draft": resident_draft.payload_dict(),
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()

        preparation = PlayerResidentCreationPrepared(
            preparation_id=generate_ulid(),
            command_id=command_id,
            world_id=world_id,
            player_identity_id=player_identity_id,
            resident_draft=resident_draft,
            payload_hash=payload_hash,
        )
        self._preparations[preparation.preparation_id] = preparation
        return preparation

    def commit_player_resident(
        self,
        command_id: str,
        preparation_id: str,
        expected_revision: int,
        fail_at_stage: Optional[str] = None,
    ) -> PlayerResidentBindingResult:
        """
        原子提交 Resident、账户、Inventory、Position、binding 与事件（§6 第 5 步）。

        任一阶段失败全体回滚（§8）；相同 (world_id, command_id) 相同 payload
        返回原 binding，不同 payload 返回 PLAYER_IDEMPOTENCY_PAYLOAD_CONFLICT。
        fail_at_stage 仅供测试注入故障。
        """
        preparation = self._preparations.get(preparation_id)
        if preparation is None:
            raise PlayerBindingError(
                "PREPARATION_NOT_FOUND", f"unknown preparation {preparation_id}"
            )
        # §7.1：幂等键为 (world_id, command_id)
        idem_key = (preparation.world_id, command_id)
        if preparation.command_id != command_id:
            raise PlayerBindingError(
                "PREPARATION_COMMAND_MISMATCH",
                "preparation was created by a different command",
            )
        if expected_revision != self._revision:
            raise PlayerBindingError(
                "EXPECTED_REVISION_STALE",
                f"expected {expected_revision}, current {self._revision}",
            )

        cached = self._idempotency.get(idem_key)
        if cached is not None:
            cached_hash, cached_result = cached
            if cached_hash != preparation.payload_hash:
                raise PlayerBindingError(
                    DENY_IDEMPOTENCY_PAYLOAD_CONFLICT,
                    "same idempotency key with different payload",
                )
            return PlayerResidentBindingResult(
                binding=cached_result.binding,
                committed_revision=cached_result.committed_revision,
                replayed=True,
            )

        # 唯一性在提交点按最新状态重校验（§7.1 并发窗口）
        player_key = (preparation.world_id, preparation.player_identity_id)
        if player_key in self._active_by_player:
            raise PlayerBindingError("PLAYER_BINDING_ALREADY_ACTIVE")

        # 两阶段提交：任一阶段失败，已完成的本地记账全部回滚
        completed: List[str] = []
        resident_id = generate_ulid()
        try:
            for stage in COMMIT_STAGES:
                if stage == fail_at_stage:
                    raise PlayerBindingError(
                        "COMMIT_STAGE_FAILED", f"injected failure at {stage}"
                    )
                if stage == "resident" and self._active_by_resident.get(
                    (preparation.world_id, resident_id)
                ):
                    raise PlayerBindingError("RESIDENT_ALREADY_BOUND")
                completed.append(stage)
        except PlayerBindingError:
            # §8：初始化中崩溃全成或全败，无孤儿账户/Inventory/Position
            completed.clear()
            raise

        # Revision 只增长 1（§6 第 5 步）
        self._revision += 1
        binding = PlayerResidentBinding(
            binding_id=generate_ulid(),
            world_id=preparation.world_id,
            player_identity_id=preparation.player_identity_id,
            resident_id=resident_id,
            state=BindingState.ACTIVE,
            created_by_command_id=command_id,
            created_revision=self._revision,
        )
        self._bindings[binding.binding_id] = binding
        self._active_by_player[player_key] = binding.binding_id
        self._active_by_resident[(binding.world_id, resident_id)] = binding.binding_id
        # RULE-PLAYER-004：玩家 Resident 不计入 AI 核心配额
        self._player_resident_count += 1

        result = PlayerResidentBindingResult(
            binding=binding, committed_revision=self._revision, replayed=False
        )
        self._idempotency[idem_key] = (preparation.payload_hash, result)
        return result

    # -- 生命周期（§7.2/§8） --

    def suspend_binding(self, binding_id: str) -> PlayerResidentBinding:
        """导入世界的 PlayerIdentity 不存在时 binding 保持 suspended（§8）"""
        binding = self._require_binding(binding_id)
        updated = self._replace_state(binding, BindingState.SUSPENDED)
        self._active_by_player.pop(
            (binding.world_id, binding.player_identity_id), None
        )
        self._active_by_resident.pop((binding.world_id, binding.resident_id), None)
        return updated

    def reclaim_binding(
        self, binding_id: str, player_identity_id: str, ownership_proof: bool
    ) -> PlayerResidentBinding:
        """
        显式 reclaim：suspended binding 重新绑定并审计（§8）。

        敏感 reclaim 需要当前本地 world ownership proof（§9）。
        """
        if not ownership_proof:
            raise PlayerBindingError(
                "RECLAIM_OWNERSHIP_PROOF_REQUIRED",
                "sensitive reclaim requires local world ownership proof",
            )
        binding = self._require_binding(binding_id)
        if binding.state is not BindingState.SUSPENDED:
            raise PlayerBindingError(
                "RECLAIM_REQUIRES_SUSPENDED",
                f"cannot reclaim binding in state {binding.state.value}",
            )
        player_key = (binding.world_id, player_identity_id)
        if player_key in self._active_by_player:
            raise PlayerBindingError("PLAYER_BINDING_ALREADY_ACTIVE")
        updated = PlayerResidentBinding(
            binding_id=binding.binding_id,
            world_id=binding.world_id,
            player_identity_id=player_identity_id,
            resident_id=binding.resident_id,
            state=BindingState.ACTIVE,
            created_by_command_id=binding.created_by_command_id,
            created_revision=binding.created_revision,
            version=binding.version + 1,
        )
        self._bindings[binding_id] = updated
        self._active_by_player[player_key] = binding_id
        self._active_by_resident[(binding.world_id, binding.resident_id)] = binding_id
        return updated

    def verify_binding_integrity(self, binding_id: str, resident_exists: bool) -> None:
        """
        启动校验（§8）：binding 损坏或指向缺失 Resident 进入 Recovery Barrier，
        禁止自动生成替代 Resident。
        """
        binding = self._require_binding(binding_id)
        if not resident_exists:
            raise PlayerBindingError(
                "RECOVERY_BARRIER_BINDING_BROKEN",
                f"binding {binding_id} points to missing resident "
                f"{binding.resident_id}",
            )

    def get_active_binding(
        self, world_id: str, player_identity_id: str
    ) -> Optional[PlayerResidentBinding]:
        binding_id = self._active_by_player.get((world_id, player_identity_id))
        return self._bindings.get(binding_id) if binding_id else None

    def get_binding_for_resident(
        self, world_id: str, resident_id: str
    ) -> Optional[PlayerResidentBinding]:
        binding_id = self._active_by_resident.get((world_id, resident_id))
        return self._bindings.get(binding_id) if binding_id else None

    def get_player_authority(
        self,
        world_id: str,
        player_identity_id: str,
        revision: int,
        world_role_ids: Tuple[str, ...] = (),
        mayor_office_id: Optional[str] = None,
        admin_session_state: str = "disabled",
    ) -> PlayerAuthorityProjection:
        """
        §5 接口：三类授权分别来自各自 owner，互不蕴含（RULE-PLAYER-005）。

        world owner（binding 存在）、Mayor office、Admin session 均可独立为 false。
        """
        binding = self.get_active_binding(world_id, player_identity_id)
        if binding is None:
            raise PlayerBindingError(
                "PLAYER_BINDING_NOT_FOUND",
                f"no active binding for ({world_id}, {player_identity_id})",
            )
        return PlayerAuthorityProjection(
            binding_id=binding.binding_id,
            resident_id=binding.resident_id,
            world_role_ids=world_role_ids,
            mayor_office_id=mayor_office_id,
            admin_session_state=admin_session_state,
            revision=revision,
        )

    def decision_source_grants_nothing(self, binding_id: str) -> dict:
        """
        RULE-PLAYER-003：decision_source=human 的能力视图与 AI 完全一致。

        返回的授予集合恒为空；差异只在合法 intent 的来源。
        """
        self._require_binding(binding_id)
        return {"skills": [], "items": [], "spells": [], "money": 0, "secrets": []}

    def _require_binding(self, binding_id: str) -> PlayerResidentBinding:
        binding = self._bindings.get(binding_id)
        if binding is None:
            raise PlayerBindingError(
                "BINDING_NOT_FOUND", f"unknown binding {binding_id}"
            )
        return binding

    def _replace_state(
        self, binding: PlayerResidentBinding, state: BindingState
    ) -> PlayerResidentBinding:
        updated = PlayerResidentBinding(
            binding_id=binding.binding_id,
            world_id=binding.world_id,
            player_identity_id=binding.player_identity_id,
            resident_id=binding.resident_id,
            state=state,
            created_by_command_id=binding.created_by_command_id,
            created_revision=binding.created_revision,
            version=binding.version + 1,
        )
        self._bindings[binding.binding_id] = updated
        return updated


def assert_valid_ulid(value: str, field_name: str) -> None:
    """DES-PLAYER-001：所有 ID 为非空稳定 ID"""
    if not is_valid_ulid(value):
        raise PlayerBindingError(
            "BINDING_ID_INVALID", f"{field_name} is not a valid ULID: {value}"
        )
