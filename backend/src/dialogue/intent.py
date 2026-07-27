"""
自然语言意图边界（DOC-DIALOGUE-004）

- RULE-DIALOGUE-019：utterance 文本永不直接改变 Conversation 之外的 Domain 状态
- RULE-DIALOGUE-020：规则后果必须编译为 Derived Command 走 owner validator
- RULE-DIALOGUE-021：玩家文本/居民许诺都不能越权；越权部分按 FORBIDDEN 拒绝
- RULE-DIALOGUE-022：事实断言进入记忆一律为 Testimony，不自动为真
- RULE-DIALOGUE-023：承诺表达只生成 Commitment Candidate，确认后才生效
- RULE-DIALOGUE-024：OOC 输入只作为普通话语处理
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..foundation import generate_ulid
from .constants import IntentKind, IntentStatus


class IntentBoundaryError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


#: 意图识别关键词（规则解析器优先，RULE-PLAYER-023 同立场）
_INTENT_PATTERNS: List[Tuple[IntentKind, re.Pattern]] = [
    (IntentKind.TRADE_PURCHASE, re.compile(r"(?:买|购买|购入)")),
    (IntentKind.TRADE_SALE, re.compile(r"(?:卖|出售|卖出)")),
    (IntentKind.GIFT, re.compile(r"(?:送给|赠与|送你|给你)")),
    (IntentKind.HIRE, re.compile(r"(?:雇佣|雇用|聘请)")),
    (IntentKind.PROMISE, re.compile(r"(?:答应|承诺|保证|一定)")),
    (IntentKind.REQUEST_HELP, re.compile(r"(?:帮我|帮忙|求助|拜托)")),
    (IntentKind.REQUEST_INFORMATION, re.compile(r"(?:告诉我|问问|打听|知道吗)")),
]

#: RULE-DIALOGUE-024：OOC 特征（指向系统本身的文本）
_OOC_PATTERNS = re.compile(
    r"(忽略.{0,4}指令|系统提示|system prompt|API|接口|模型|管理员权限|游戏规则修改)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DerivedIntent:
    """DES-DIALOGUE-004 derived_intents 行"""

    intent_kind: IntentKind
    compilation_id: str
    target_domain: str
    status: IntentStatus
    derived_command_id: Optional[str] = None


@dataclass(frozen=True)
class CommitmentCandidate:
    """RULE-DIALOGUE-023：未确认承诺不产生 deadline 与履约义务"""

    candidate_id: str
    direction: str  # speaker_promises / addressee_promises
    status: IntentStatus = IntentStatus.AWAITING_CONFIRMATION


@dataclass(frozen=True)
class IntentBoundaryResult:
    """DES-DIALOGUE-004：附着在 utterance 提交管道上的判定结果"""

    conversation_id: str
    utterance_index: int
    speaker_id: str
    speech_fact_committed: bool
    derived_intents: Tuple[DerivedIntent, ...]
    commitment_candidates: Tuple[CommitmentCandidate, ...]
    out_of_character: bool


_INTENT_TO_DOMAIN = {
    IntentKind.TRADE_PURCHASE: "economy",
    IntentKind.TRADE_SALE: "economy",
    IntentKind.GIFT: "economy",
    IntentKind.HIRE: "economy",
    IntentKind.PROMISE: "memory",
    IntentKind.REQUEST_HELP: "social",
    IntentKind.REQUEST_INFORMATION: "social",
    IntentKind.SOCIAL_ONLY: "none",
}


class IntentBoundaryClassifier:
    """
    utterance 提交后的意图识别（§9：异步、幂等、不阻塞 Speech Fact）。

    幂等键 (conversation_id, utterance_index)。
    """

    def __init__(self) -> None:
        self._results: Dict[Tuple[str, int], IntentBoundaryResult] = {}

    def classify(
        self,
        conversation_id: str,
        utterance_index: int,
        speaker_id: str,
        text: str,
    ) -> IntentBoundaryResult:
        key = (conversation_id, utterance_index)
        if key in self._results:
            return self._results[key]

        ooc = bool(_OOC_PATTERNS.search(text))
        intents: List[DerivedIntent] = []
        candidates: List[CommitmentCandidate] = []

        if not ooc:
            seen: set[IntentKind] = set()
            for kind, pattern in _INTENT_PATTERNS:
                if pattern.search(text) and kind not in seen:
                    seen.add(kind)
                    if kind is IntentKind.PROMISE:
                        # RULE-DIALOGUE-023：承诺表达只生成 candidate
                        candidates.append(
                            CommitmentCandidate(
                                candidate_id=generate_ulid(),
                                direction="speaker_promises",
                            )
                        )
                    intents.append(
                        DerivedIntent(
                            intent_kind=kind,
                            compilation_id=generate_ulid(),
                            target_domain=_INTENT_TO_DOMAIN[kind],
                            status=IntentStatus.AWAITING_CONFIRMATION,
                        )
                    )
            if not intents:
                intents.append(
                    DerivedIntent(
                        intent_kind=IntentKind.SOCIAL_ONLY,
                        compilation_id=generate_ulid(),
                        target_domain="none",
                        status=IntentStatus.CONFIRMED,
                    )
                )
        else:
            # RULE-DIALOGUE-024：OOC 不进入意图编译
            intents.append(
                DerivedIntent(
                    intent_kind=IntentKind.SOCIAL_ONLY,
                    compilation_id=generate_ulid(),
                    target_domain="none",
                    status=IntentStatus.CONFIRMED,
                )
            )

        result = IntentBoundaryResult(
            conversation_id=conversation_id,
            utterance_index=utterance_index,
            speaker_id=speaker_id,
            speech_fact_committed=True,
            derived_intents=tuple(intents),
            commitment_candidates=tuple(candidates),
            out_of_character=ooc,
        )
        self._results[key] = result
        return result

    @staticmethod
    def assert_speech_fact_has_no_domain_effect(
        domain_state_before: object, domain_state_after: object
    ) -> None:
        """RULE-DIALOGUE-019：无 Derived Command 提交则世界状态零变化"""
        if domain_state_before != domain_state_after:
            raise IntentBoundaryError(
                "DIALOGUE_SPEECH_FACT_SIDE_EFFECT",
                "utterance text must never directly change domain state",
            )

    @staticmethod
    def expire_candidate(candidate: CommitmentCandidate) -> CommitmentCandidate:
        """§8：Confirmation 超时未答复 → expired，不留悬挂 Reservation"""
        return CommitmentCandidate(
            candidate_id=candidate.candidate_id,
            direction=candidate.direction,
            status=IntentStatus.EXPIRED,
        )

    @staticmethod
    def assert_testimony_not_fact(record_kind: str) -> None:
        """RULE-DIALOGUE-022：断言进入记忆一律为 testimony"""
        if record_kind != "testimony":
            raise IntentBoundaryError(
                "DIALOGUE_ASSERTION_MUST_BE_TESTIMONY",
                f"speech assertions enter memory as testimony, got {record_kind}",
            )
