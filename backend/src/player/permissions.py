"""
玩家居民模式权限（DOC-PLAYER-007）

- RULE-PLAYER-031：Resident Mode 不允许治理与 Admin mutation
- RULE-PLAYER-032：只能使用绑定 Resident 已拥有/获准的能力
- RULE-PLAYER-033：读取最小披露
- RULE-PLAYER-034：授权在提交点以最新版本校验
- RULE-PLAYER-035：拒绝是稳定结果，给安全 reason code，无近似成功 fallback
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from .mode import PlayerMode


@dataclass(frozen=True)
class PermissionDenial:
    """
    §6 第 5 步：deny_code + safe_player_message + retryability。

    §9：区分 not_permitted 与可公开原因；不能通过枚举目标探测秘密。
    """

    deny_code: str
    safe_player_message: str
    retryable: bool


#: §5.2 居民模式默认能力（允许尝试 ≠ 提交成功）
RESIDENT_CAPABILITIES = frozenset(
    {
        "resident.move",
        "resident.observe",
        "resident.talk",
        "resident.work",
        "resident.trade",
        "resident.craft",
        "resident.gather",
        "resident.give",
        "resident.cast_spell",
        "resident.combat",
        "resident.enter_building",
        "resident.view_public_stats",
    }
)

#: RULE-PLAYER-031：居民模式明确禁止的治理/Admin 能力前缀
_GOVERNANCE_PREFIXES = ("mayor.", "admin.")
_GOVERNANCE_CAPABILITIES = frozenset(
    {
        "governance.public_budget",
        "governance.tax_rate",
        "governance.mandatory_notice",
        "governance.public_works",
    }
)

#: §5.2：需要附加条件的能力（条件允许 ≠ 默认允许）
_CONDITIONAL_CAPABILITIES = frozenset(
    {
        "resident.cast_spell",
        "resident.combat",
        "resident.enter_building",
    }
)

#: §9：secret 门等敏感目标失败的统一公开文案
UNIFORM_ENTRY_DENIAL_MESSAGE = "无法进入"


@dataclass(frozen=True)
class CapabilityProjection:
    """
    §5.1 权限投影：revision-stamped hint，不是授权本身（§3）。

    不含余额、Inventory 内容、secret、relationship raw values。
    """

    binding_id: str
    resident_id: str
    mode: PlayerMode
    revision: int
    capability_ids: Tuple[str, ...]
    role_versions: Dict[str, int] = field(default_factory=dict)
    restriction_codes: Tuple[str, ...] = ()
    expires_after_revision: int = 0
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported capability projection schema_version")
        if self.expires_after_revision < self.revision:
            raise ValueError("expires_after_revision must be >= revision")

    def is_stale(self, current_revision: int) -> bool:
        """§7：projection 最多有效到生成时 Revision"""
        return current_revision > self.expires_after_revision


class ResidentPermissionService:
    """居民模式能力校验（§3.1 交集模型的服务端组合点）"""

    def build_projection(
        self,
        binding_id: str,
        resident_id: str,
        mode: PlayerMode,
        revision: int,
        healthy: bool = True,
        role_versions: Optional[Dict[str, int]] = None,
        restriction_codes: Tuple[str, ...] = (),
    ) -> CapabilityProjection:
        """
        生成权限投影。RULE-PLAYER-031：居民模式下 mayor/sandbox_admin
        不包含在 capability 中。
        """
        capabilities = set(RESIDENT_CAPABILITIES)
        if not healthy:
            # §5.2：健康/状态限制收缩能力集
            capabilities -= {"resident.work", "resident.combat", "resident.cast_spell"}
            restriction_codes = tuple(sorted(set(restriction_codes) | {"health"}))
        if mode is not PlayerMode.RESIDENT_ACTIVE:
            # 非居民模式不发放居民能力集
            capabilities = set()

        return CapabilityProjection(
            binding_id=binding_id,
            resident_id=resident_id,
            mode=mode,
            revision=revision,
            capability_ids=tuple(sorted(capabilities)),
            role_versions=dict(role_versions or {}),
            restriction_codes=restriction_codes,
            expires_after_revision=revision,
        )

    def check_capability(
        self,
        projection: CapabilityProjection,
        capability_id: str,
        current_revision: int,
        target_is_secret: bool = False,
    ) -> Optional[PermissionDenial]:
        """
        校验单个能力；返回 None 表示允许尝试。

        RULE-PLAYER-034：提交点必须由 owner 用最新 aggregate 重校验，
        本检查只是 PLAYER 侧 category gate。
        """
        if projection.is_stale(current_revision):
            return PermissionDenial(
                deny_code="PLAYER_CAPABILITY_PROJECTION_STALE",
                safe_player_message="操作状态已变化，请重试",
                retryable=True,
            )

        if capability_id.startswith(_GOVERNANCE_PREFIXES):
            # RULE-PLAYER-031：居民模式禁止 Mayor/Admin union
            return PermissionDenial(
                deny_code="PLAYER_GOVERNANCE_REQUIRES_MAYOR_MODE",
                safe_player_message="该操作需要镇长模式与授权",
                retryable=False,
            )
        if capability_id in _GOVERNANCE_CAPABILITIES:
            return PermissionDenial(
                deny_code="PLAYER_GOVERNANCE_REQUIRES_MAYOR_MODE",
                safe_player_message="该操作需要镇长模式与授权",
                retryable=False,
            )

        if capability_id not in projection.capability_ids:
            if target_is_secret:
                # §9：secret 目标统一公开文案，不泄露 owner 或内部事件
                return PermissionDenial(
                    deny_code="not_permitted",
                    safe_player_message=UNIFORM_ENTRY_DENIAL_MESSAGE,
                    retryable=False,
                )
            return PermissionDenial(
                deny_code="not_permitted",
                safe_player_message="当前状态下无法执行该操作",
                retryable=False,
            )
        return None

    @staticmethod
    def assert_no_near_success_fallback(denial: PermissionDenial, committed: bool) -> None:
        """RULE-PLAYER-035：拒绝后不得通过 fallback 改成近似成功"""
        if committed:
            raise AssertionError(
                f"denied command {denial.deny_code} must not produce partial success"
            )

    @staticmethod
    def check_secret_access() -> PermissionDenial:
        """
        §5.2：查看私人记忆/秘密默认禁止，只有 owner 明确的合法披露事件例外
        （披露事件由 MEMORY owner 判定，此处一律 fail closed）。
        """
        return PermissionDenial(
            deny_code="not_permitted",
            safe_player_message="无法查看",
            retryable=False,
        )
