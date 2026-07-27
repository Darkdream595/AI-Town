"""
对话上下文构建（DOC-DIALOGUE-003）

- RULE-DIALOGUE-013：只由服务器在最新已提交 Revision 组装
- RULE-DIALOGUE-014：进入 context 前必须已有 AccessDecision allow；
  收到未判定条目整份 rejected
- RULE-DIALOGUE-015：每位响应居民单独构建，互不共享
- RULE-DIALOGUE-016：窗口上限 12；更早内容只以 is_summary=true 摘要进入
- RULE-DIALOGUE-017：Speaker Projection 只含公开外观/身份与响应者自己的
  记忆/关系投影
- RULE-DIALOGUE-018：持久化 context_hash/prompt ID/observed Revision，
  不持久化完整 Prompt
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .constants import (
    CONTEXT_MEMORY_LIMIT,
    DIALOGUE_PROMPT_ID,
    UTTERANCE_HISTORY_WINDOW,
)
from .conversation import Utterance


class ContextBuildError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True)
class AccessDecision:
    """DOC-MEMORY-009 的访问判定快照（RULE-DIALOGUE-014 的输入）"""

    decision_id: str
    subject_id: str  # 记忆/关系/秘密条目 ID
    allowed: bool
    policy_version: int = 1


@dataclass(frozen=True)
class UtteranceView:
    utterance_index: int
    speaker_id: str
    text: str
    is_summary: bool = False


@dataclass(frozen=True)
class HistorySummary:
    """RULE-DIALOGUE-016：摘要必须显式标记，不得伪装成原话"""

    covered_utterances: Tuple[int, ...]
    text: str
    is_summary: bool = True

    def __post_init__(self) -> None:
        if not self.is_summary:
            raise ContextBuildError(
                "DIALOGUE_SUMMARY_FLAG_REQUIRED",
                "history summary must be marked is_summary=true",
            )


@dataclass(frozen=True)
class SpeakerProjection:
    """
    RULE-DIALOGUE-017：最小化投影。

    对方内心状态、Need、秘密、Inventory、余额不进入；只允许公开外观/
    公开身份与响应者自己的关系边/记忆引用。
    """

    entity_id: str
    display_name: str
    public_identity: Dict[str, str]
    relationship_edge: Optional[Dict[str, int]] = None
    impression_memory_ids: Tuple[str, ...] = ()


@dataclass(frozen=True)
class DialogueContextV1:
    """DES-DIALOGUE-003 组装结果（不可变快照）"""

    conversation_id: str
    responder_id: str
    observed_revision: int
    game_time: int
    utterance_history: Tuple[UtteranceView, ...]
    history_summary: Optional[HistorySummary]
    speaker_projections: Tuple[SpeakerProjection, ...]
    retrieved_memory_ids: Tuple[str, ...]
    access_decision_ids: Tuple[str, ...]
    commitments: Tuple[Dict, ...]
    context_hash: str
    context_degraded: bool = False
    prompt_id: str = DIALOGUE_PROMPT_ID
    schema_version: int = 1


def compute_context_hash(
    conversation_id: str,
    responder_id: str,
    observed_revision: int,
    utterance_views: Tuple[UtteranceView, ...],
    retrieved_memory_ids: Tuple[str, ...],
) -> str:
    """RULE-DIALOGUE-018：context_hash 覆盖全部语义输入"""
    canonical = json.dumps(
        {
            "conversation_id": conversation_id,
            "responder_id": responder_id,
            "observed_revision": observed_revision,
            "utterances": [
                (u.utterance_index, u.speaker_id, u.text, u.is_summary)
                for u in utterance_views
            ],
            "memories": list(retrieved_memory_ids),
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class DialogueContextBuilder:
    """
    服务器侧 Context Builder（RULE-DIALOGUE-013）。

    memory_retriever 注入：返回 (memory_ids, decisions, timed_out)。
    """

    def __init__(self, memory_retriever=None) -> None:
        self._memory_retriever = memory_retriever
        self._persisted: List[Dict] = []

    def build(
        self,
        conversation_id: str,
        responder_id: str,
        participant_ids: List[str],
        utterances: List[Utterance],
        observed_revision: int,
        game_time: int,
        joined_at_utterance_index: int = 0,
        relationship_edges: Optional[Dict[str, Dict[str, int]]] = None,
        display_names: Optional[Dict[str, str]] = None,
        commitments: Tuple[Dict, ...] = (),
    ) -> DialogueContextV1:
        """build_dialogue_context(conversation_id, responder_id) 的实现"""
        # RULE-DIALOGUE-012/§7：中途加入者窗口从加入事件起算
        visible = [u for u in utterances if u.utterance_index >= joined_at_utterance_index]

        window = visible[-UTTERANCE_HISTORY_WINDOW:]
        overflow = visible[: -UTTERANCE_HISTORY_WINDOW] if len(visible) > UTTERANCE_HISTORY_WINDOW else []

        views = tuple(
            UtteranceView(u.utterance_index, u.speaker_id, u.text) for u in window
        )
        summary = None
        if overflow:
            summary = HistorySummary(
                covered_utterances=tuple(u.utterance_index for u in overflow),
                text=f"（此前 {len(overflow)} 条发言的摘要）",
            )

        # MEMORY 检索（§8：超时降级为最小 context，秘密过滤不放宽）
        memory_ids: Tuple[str, ...] = ()
        decision_ids: Tuple[str, ...] = ()
        degraded = False
        if self._memory_retriever is not None:
            retrieved_ids, decisions, timed_out = self._memory_retriever(
                conversation_id, responder_id
            )
            if timed_out:
                degraded = True
            else:
                # RULE-DIALOGUE-014：未判定或被拒条目使整份 context rejected
                for decision in decisions:
                    if not decision.allowed:
                        raise ContextBuildError(
                            "DIALOGUE_CONTEXT_ACCESS_DENIED",
                            f"entry {decision.subject_id} lacks AccessDecision allow",
                        )
                allowed_ids = {d.subject_id for d in decisions}
                unknown = [m for m in retrieved_ids if m not in allowed_ids]
                if unknown:
                    raise ContextBuildError(
                        "DIALOGUE_CONTEXT_UNJUDGED_ENTRY",
                        f"memories without AccessDecision: {unknown}",
                    )
                memory_ids = tuple(retrieved_ids[:CONTEXT_MEMORY_LIMIT])
                decision_ids = tuple(d.decision_id for d in decisions)

        edges = relationship_edges or {}
        names = display_names or {}
        projections = tuple(
            SpeakerProjection(
                entity_id=pid,
                display_name=names.get(pid, pid),
                public_identity={"display_name": names.get(pid, pid)},
                relationship_edge=edges.get(pid),
            )
            for pid in participant_ids
            if pid != responder_id
        )

        context_hash = compute_context_hash(
            conversation_id, responder_id, observed_revision, views, memory_ids
        )
        context = DialogueContextV1(
            conversation_id=conversation_id,
            responder_id=responder_id,
            observed_revision=observed_revision,
            game_time=game_time,
            utterance_history=views,
            history_summary=summary,
            speaker_projections=projections,
            retrieved_memory_ids=memory_ids,
            access_decision_ids=decision_ids,
            commitments=commitments,
            context_hash=context_hash,
            context_degraded=degraded,
        )
        # RULE-DIALOGUE-018：持久化 hash/prompt ID/revision，不持久化完整 Prompt
        self._persisted.append(
            {
                "context_hash": context.context_hash,
                "prompt_id": context.prompt_id,
                "observed_revision": observed_revision,
            }
        )
        return context

    def persisted_records(self) -> List[Dict]:
        return list(self._persisted)

    @staticmethod
    def assert_no_prompt_persisted(record: Dict) -> None:
        """RULE-DIALOGUE-018：持久化记录不得包含完整 Prompt 或 reasoning"""
        for forbidden in ("prompt_text", "reasoning_content", "full_prompt"):
            if forbidden in record:
                raise ContextBuildError(
                    "DIALOGUE_PERSISTENCE_BOUNDARY_VIOLATION",
                    f"{forbidden} must not be persisted",
                )
