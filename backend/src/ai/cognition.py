"""
居民认知与行动提案流水线

符合 DOC-AI-001：
- 状态机 scheduled → observing → retrieving → assembling → planning → parsing
  → validating → reserving → committing → observed_result
- RULE-AI-002：模型只产生 Plan/Intent/Proposal，不得调用 Repository/Domain writer
- RULE-AI-005：同一 cognition_run_id + artifact_kind + attempt 只接受一个 provider result
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CognitionStage(str, Enum):
    """流水线阶段（DOC-AI-001 §3）"""

    SCHEDULED = "scheduled"
    OBSERVING = "observing"
    RETRIEVING = "retrieving"
    ASSEMBLING = "assembling"
    PLANNING = "planning"
    PARSING = "parsing"
    VALIDATING = "validating"
    RESERVING = "reserving"
    COMMITTING = "committing"
    OBSERVED_RESULT = "observed_result"
    FALLBACK = "fallback"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


#: 合法状态边（TEST-AI-001）
COGNITION_EDGES: dict[CognitionStage, frozenset[CognitionStage]] = {
    CognitionStage.SCHEDULED: frozenset({CognitionStage.OBSERVING, CognitionStage.CANCELLED}),
    CognitionStage.OBSERVING: frozenset({CognitionStage.RETRIEVING}),
    CognitionStage.RETRIEVING: frozenset({CognitionStage.ASSEMBLING}),
    CognitionStage.ASSEMBLING: frozenset({CognitionStage.PLANNING}),
    CognitionStage.PLANNING: frozenset({CognitionStage.PARSING, CognitionStage.EXPIRED}),
    CognitionStage.PARSING: frozenset({CognitionStage.VALIDATING}),
    CognitionStage.VALIDATING: frozenset(
        {CognitionStage.RESERVING, CognitionStage.PLANNING, CognitionStage.FALLBACK}
    ),
    CognitionStage.RESERVING: frozenset({CognitionStage.COMMITTING}),
    CognitionStage.COMMITTING: frozenset({CognitionStage.OBSERVED_RESULT, CognitionStage.PLANNING}),
    CognitionStage.FALLBACK: frozenset({CognitionStage.VALIDATING}),
    CognitionStage.OBSERVED_RESULT: frozenset(),
    CognitionStage.CANCELLED: frozenset(),
    CognitionStage.EXPIRED: frozenset(),
}


class CognitionTransitionError(Exception):
    """非法流水线状态边"""


@dataclass(frozen=True)
class DecisionReference:
    """不可变 Decision Reference（DOC-AI-001 §3）"""

    job_id: str
    resident_id: str
    plan_kind: str
    observed_revision: int
    observed_game_time: int


@dataclass(frozen=True)
class CognitionEnvelope:
    """每次认知运行的 immutable envelope（DES-AI-001）"""

    cognition_run_id: str
    resident_id: str
    plan_kind: str
    observed_revision: int
    observed_game_time: int
    context_hash: str
    prompt_id: str
    request_policy_version: int
    attempt: int


@dataclass
class CognitionRun:
    """单次认知运行状态"""

    envelope: CognitionEnvelope
    stage: CognitionStage = CognitionStage.SCHEDULED
    accepted_result_key: Optional[str] = None  # (run_id, artifact_kind, attempt) 去重

    def transition_to(self, new_stage: CognitionStage) -> None:
        if new_stage == self.stage:
            return
        if new_stage not in COGNITION_EDGES[self.stage]:
            raise CognitionTransitionError(
                f"非法认知状态迁移: {self.stage.value} -> {new_stage.value}"
            )
        self.stage = new_stage

    def accept_provider_result(self, artifact_kind: str, attempt: int) -> bool:
        """
        同一 cognition_run_id + artifact_kind + attempt 只接受一个 provider result（RULE-AI-005）

        重复/迟到结果返回 False（可审计但不可重新入提交链）。
        """
        result_key = f"{self.envelope.cognition_run_id}:{artifact_kind}:{attempt}"
        if self.accepted_result_key is not None:
            return False
        if self.stage in (CognitionStage.CANCELLED, CognitionStage.EXPIRED, CognitionStage.OBSERVED_RESULT):
            return False
        if attempt != self.envelope.attempt:
            return False
        self.accepted_result_key = result_key
        return True
