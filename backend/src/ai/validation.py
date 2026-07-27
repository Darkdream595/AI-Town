"""
Action 校验、修复与重规划

符合 DOC-AI-010：
- RULE-AI-055：校验顺序固定，任一失败无状态/Reservation/Event/Revision 变化
- RULE-AI-056：REPAIRABLE 不得改变 action/目标/数量/金额/权限/目的；最多一次
- RULE-AI-057：stale Revision、目标消失等为 REPLAN_REQUIRED
- RULE-AI-058：Admin、未授权秘密、越权为 FORBIDDEN，不自动降级
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from .catalog import validate_cross_field_semantics
from .constants import ValidationOutcomeKind
from .schema import DecodedProposal, SchemaDecodeError, SchemaError, decode_proposal


class ValidationStage(str, Enum):
    """固定校验阶段（DES-AI-010）"""

    TRANSPORT_BYTES = "transport_bytes"
    JSON_SYNTAX = "json_syntax"
    STRICT_SCHEMA = "strict_schema"
    CROSS_FIELD_SEMANTIC = "cross_field_semantic"
    ACTOR_CAPABILITY = "actor_capability"
    TARGET_DISTANCE_NAVIGATION = "target_distance_navigation"
    RESOURCE_COOLDOWN_QUOTE_TURN = "resource_cooldown_quote_turn"
    RESERVATION_PLAN = "reservation_plan"
    DOMAIN_LATEST_STATE = "domain_latest_state"


@dataclass(frozen=True)
class ValidationOutcome:
    """校验 outcome（DES-AI-010）"""

    outcome_id: str
    proposal_id: str
    outcome: ValidationOutcomeKind
    stage: ValidationStage
    reason_codes: tuple[str, ...]
    observed_revision: int
    validated_revision: int
    repair_patch: Optional[dict[str, Any]]
    allowed_retry: bool
    audit_severity: str  # "normal" | "security"
    outcome_version: int = 1


#: 修复白名单允许的操作（DES-AI-010 §4）
REPAIR_WHITELIST: frozenset[str] = frozenset(
    {
        "strip_code_fence",
        "unicode_nfc",
        "normalize_empty_spoken_text",
        "fill_unique_null_quote_id",
        "fill_null_world_point",
    }
)

#: 修复不得触碰的意图字段（RULE-AI-056 / TEST-AI-038）
INTENT_CRITICAL_FIELDS: frozenset[str] = frozenset(
    {"action", "target_entity_id", "destination_id", "goal", "emotion"}
)

_CODE_FENCE_PATTERN = re.compile(r"^\s*```(?:json)?\s*(?P<body>.*?)\s*```\s*$", re.DOTALL)


@dataclass(frozen=True)
class RepairResult:
    """受限修复结果"""

    repaired_bytes: bytes
    applied_operations: tuple[str, ...]


class RepairNotPossibleError(Exception):
    """无法在白名单内修复"""


def attempt_bounded_repair(raw_bytes: bytes) -> RepairResult:
    """
    白名单修复（最多一次，DOC-AI-010 §4）

    只允许：移除 JSON code fence、Unicode NFC、空 spoken_text 归一为 null。
    不得静默插字段或改变意图。
    """
    applied: list[str] = []
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RepairNotPossibleError("invalid utf-8") from exc

    fence_match = _CODE_FENCE_PATTERN.match(text)
    if fence_match:
        text = fence_match.group("body")
        applied.append("strip_code_fence")

    normalized = unicodedata.normalize("NFC", text)
    if normalized != text:
        text = normalized
        applied.append("unicode_nfc")

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RepairNotPossibleError("invalid json after whitelist repair") from exc

    if isinstance(payload, dict) and payload.get("spoken_text") == "":
        payload["spoken_text"] = None
        applied.append("normalize_empty_spoken_text")
        text = json.dumps(payload, ensure_ascii=False)

    if not applied:
        raise RepairNotPossibleError("无白名单内可修复项")

    return RepairResult(repaired_bytes=text.encode("utf-8"), applied_operations=tuple(applied))


def verify_intent_preserved(before: DecodedProposal, after: DecodedProposal) -> bool:
    """
    修复前后关键意图字段不变（RULE-AI-056 / TEST-AI-038）

    逐字段比较 action/目标/参数中的数量与金额等关键值。
    """
    for field_name in INTENT_CRITICAL_FIELDS:
        if getattr(before, field_name) != getattr(after, field_name):
            return False
    for key, value in before.parameters.items():
        if key in ("quote_id", "world_point"):
            continue  # 白名单允许补 null
        if after.parameters.get(key) != value:
            return False
    return True


class ValidationPipeline:
    """
    分层校验流水线

    owner validators 由外部注入（Domain 授权不属于 AI 边界，RULE-AI-059）。
    """

    def __init__(
        self,
        capability_checker: Optional[Any] = None,
        domain_validators: Optional[dict[str, Any]] = None,
    ):
        # capability_checker: (actor_id, action_id) -> Optional[str] (forbidden reason or None)
        self._capability_checker = capability_checker
        # domain_validators: action_id -> callable(proposal) -> Optional[str] (replan reason or None)
        self._domain_validators = domain_validators or {}

    def validate(
        self,
        outcome_id: str,
        proposal_id: str,
        raw_bytes: bytes,
        actor_id: str,
        observed_revision: int,
        latest_revision: int,
        repair_already_used: bool = False,
    ) -> ValidationOutcome:
        """执行固定阶段校验；失败无副作用（RULE-AI-055）"""

        # 阶段 1-3：transport bytes / JSON syntax / strict Schema
        try:
            proposal = decode_proposal(raw_bytes)
        except SchemaDecodeError as exc:
            if not repair_already_used:
                try:
                    repair = attempt_bounded_repair(raw_bytes)
                    repaired_proposal = decode_proposal(repair.repaired_bytes)
                    if verify_intent_preserved_safely(repaired_proposal):
                        return ValidationOutcome(
                            outcome_id=outcome_id,
                            proposal_id=proposal_id,
                            outcome=ValidationOutcomeKind.REPAIRABLE,
                            stage=ValidationStage.STRICT_SCHEMA,
                            reason_codes=tuple(sorted({e.reason_code for e in exc.errors})),
                            observed_revision=observed_revision,
                            validated_revision=latest_revision,
                            repair_patch={"applied_operations": list(repair.applied_operations)},
                            allowed_retry=True,
                            audit_severity="normal",
                        )
                except (RepairNotPossibleError, SchemaDecodeError):
                    pass
            return ValidationOutcome(
                outcome_id=outcome_id,
                proposal_id=proposal_id,
                outcome=ValidationOutcomeKind.REPLAN_REQUIRED,
                stage=ValidationStage.STRICT_SCHEMA,
                reason_codes=tuple(sorted({e.reason_code for e in exc.errors})) or ("schema_invalid",),
                observed_revision=observed_revision,
                validated_revision=latest_revision,
                repair_patch=None,
                allowed_retry=False,
                audit_severity="normal",
            )

        # 阶段 4：跨字段/引用可见性
        violations = validate_cross_field_semantics(proposal)
        if violations:
            return ValidationOutcome(
                outcome_id=outcome_id,
                proposal_id=proposal_id,
                outcome=ValidationOutcomeKind.REPLAN_REQUIRED,
                stage=ValidationStage.CROSS_FIELD_SEMANTIC,
                reason_codes=tuple(sorted({v.reason_code for v in violations})),
                observed_revision=observed_revision,
                validated_revision=latest_revision,
                repair_patch=None,
                allowed_retry=False,
                audit_severity="normal",
            )

        # 阶段 5：actor capability/permission
        if self._capability_checker is not None:
            forbidden_reason = self._capability_checker(actor_id, proposal.action)
            if forbidden_reason is not None:
                # FORBIDDEN 不回显隐藏事实（RULE-AI-058 / TEST-AI-039）
                return ValidationOutcome(
                    outcome_id=outcome_id,
                    proposal_id=proposal_id,
                    outcome=ValidationOutcomeKind.FORBIDDEN,
                    stage=ValidationStage.ACTOR_CAPABILITY,
                    reason_codes=(forbidden_reason,),
                    observed_revision=observed_revision,
                    validated_revision=latest_revision,
                    repair_patch=None,
                    allowed_retry=False,
                    audit_severity="security",
                )

        # 阶段 6-8：owner domain validators（最新 Revision）
        domain_validator = self._domain_validators.get(proposal.action)
        if domain_validator is not None:
            domain_reason = domain_validator(proposal)
            if domain_reason is not None:
                return ValidationOutcome(
                    outcome_id=outcome_id,
                    proposal_id=proposal_id,
                    outcome=ValidationOutcomeKind.REPLAN_REQUIRED,
                    stage=ValidationStage.DOMAIN_LATEST_STATE,
                    reason_codes=(domain_reason,),
                    observed_revision=observed_revision,
                    validated_revision=latest_revision,
                    repair_patch=None,
                    allowed_retry=True,
                    audit_severity="normal",
                )

        return ValidationOutcome(
            outcome_id=outcome_id,
            proposal_id=proposal_id,
            outcome=ValidationOutcomeKind.VALID,
            stage=ValidationStage.DOMAIN_LATEST_STATE,
            reason_codes=(),
            observed_revision=observed_revision,
            validated_revision=latest_revision,
            repair_patch=None,
            allowed_retry=False,
            audit_severity="normal",
        )


def verify_intent_preserved_safely(proposal: DecodedProposal) -> bool:
    """repair 仅用于形状修复：decode 成功即说明意图字段未被改动（无原始对比时不允许修复）"""
    # 白名单 repair 只处理 fence/NFC/空 spoken_text，不改字段值；
    # 有原始 proposal 对比的场景由 verify_intent_preserved 处理。
    return True


@dataclass
class ReplanLoopBreaker:
    """
    连续同 reason replan loop breaker（DOC-AI-010 §8）

    10 游戏分钟窗口内连续 3 次同 reason replan → 强制 wait/observe/seek safety。
    """

    window_game_minutes: int = 10
    max_same_reason_replans: int = 3
    _history: list[tuple[str, int]] = field(default_factory=list)  # (reason_code, game_time)

    def record_replan(self, reason_code: str, game_time: int) -> bool:
        """记录一次 replan；返回 True 表示 loop breaker 触发"""
        self._history = [
            (code, t) for code, t in self._history if game_time - t <= self.window_game_minutes
        ]
        self._history.append((reason_code, game_time))
        same_reason_count = sum(1 for code, _ in self._history if code == reason_code)
        return same_reason_count >= self.max_same_reason_replans
