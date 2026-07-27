"""
对话的记忆与关系影响（DOC-DIALOGUE-009）

- RULE-DIALOGUE-052：只有已提交 Speech Act 与终结事件进入记忆/关系管道
- RULE-DIALOGUE-053：版本化类别映射；lie 按表面类型映射
- RULE-DIALOGUE-054：DIALOGUE 事件不携带任何 delta 字段
- RULE-DIALOGUE-055：终结时提交 Episode 事件
- RULE-DIALOGUE-056：旁听社会影响只经 overheard 事件
- RULE-DIALOGUE-057：玩家与居民事件完全同构
- RULE-DIALOGUE-058：类别事件与 Episode 幂等
- RULE-DIALOGUE-080：玩家 utterance 分类器（确定性、fail closed 到
  inform/smalltalk、承诺确认不补发）
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..foundation import generate_ulid
from .constants import ConversationPrivacy, EndedReason, SpeechActType


class SocialEventError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


#: RULE-DIALOGUE-053 版本化类别映射表
CATEGORY_MAP_VERSION = 1

CATEGORY_MAP: Dict[str, str] = {
    "comfort": "dialogue.comforted",
    "apologize": "dialogue.apologized",
    "warn": "dialogue.warned",
    "refuse": "dialogue.refused",
    "negotiate": "dialogue.negotiated",
    "greet": "dialogue.smalltalk",
    "inform": "dialogue.smalltalk",
    "ask": "dialogue.smalltalk",
    "request": "dialogue.smalltalk",
    "farewell": "dialogue.smalltalk",
}

#: promise 的特殊性：带 offer 且确认才映射 promise_made，否则 smalltalk
PROMISE_MADE_CATEGORY = "dialogue.promise_made"
SMALLTALK_CATEGORY = "dialogue.smalltalk"


def map_speech_act_category(
    speech_act_type: SpeechActType,
    has_commitment_offer: bool = False,
    offer_confirmed: bool = False,
    surface_type: Optional[SpeechActType] = None,
) -> str:
    """
    RULE-DIALOGUE-053：每个已提交 Speech Act 恰好一个类别。

    lie 按表面类型映射（surface_type）；promise 带确认 offer 才记
    promise_made，口头空话记 smalltalk。
    """
    if speech_act_type is SpeechActType.LIE:
        effective = surface_type or SpeechActType.INFORM
        return CATEGORY_MAP.get(effective.value, SMALLTALK_CATEGORY)
    if speech_act_type is SpeechActType.PROMISE:
        if has_commitment_offer and offer_confirmed:
            return PROMISE_MADE_CATEGORY
        return SMALLTALK_CATEGORY
    category = CATEGORY_MAP.get(speech_act_type.value)
    if category is None:
        raise SocialEventError(
            "DIALOGUE_CATEGORY_MAP_MISS",
            f"no category for {speech_act_type.value}",
        )
    return category


@dataclass(frozen=True)
class SpeechActEvent:
    """DES-DIALOGUE-009 speech_act_event（无 delta 字段，RULE-DIALOGUE-054）"""

    event_id: str
    conversation_id: str
    utterance_index: int
    speaker_id: str
    addressed_entity_id: Optional[str]
    social_event_category: str
    privacy: ConversationPrivacy
    category_map_version: int = CATEGORY_MAP_VERSION
    event_type: str = "dialogue.speech_act_committed/v1"


@dataclass(frozen=True)
class EpisodeEvent:
    """DES-DIALOGUE-009 episode_event（RULE-DIALOGUE-055）"""

    event_id: str
    conversation_id: str
    participant_ids: Tuple[str, ...]
    duration_game_minutes: int
    utterance_count: int
    category_counts: Dict[str, int]
    ended_reason: EndedReason
    event_type: str = "dialogue.conversation_episode/v1"


class SocialEventEmitter:
    """类别事件与 Episode 的发射与幂等（RULE-DIALOGUE-058）"""

    def __init__(self) -> None:
        self._by_utterance: Dict[Tuple[str, int], SpeechActEvent] = {}
        self._episodes: Dict[str, EpisodeEvent] = {}

    def emit_speech_act_event(
        self,
        conversation_id: str,
        utterance_index: int,
        speaker_id: str,
        addressed_entity_id: Optional[str],
        speech_act_type: SpeechActType,
        privacy: ConversationPrivacy,
        has_commitment_offer: bool = False,
        offer_confirmed: bool = False,
        surface_type: Optional[SpeechActType] = None,
    ) -> SpeechActEvent:
        key = (conversation_id, utterance_index)
        existing = self._by_utterance.get(key)
        if existing is not None:
            return existing  # RULE-DIALOGUE-058：重放幂等返回原事件
        event = SpeechActEvent(
            event_id=generate_ulid(),
            conversation_id=conversation_id,
            utterance_index=utterance_index,
            speaker_id=speaker_id,
            addressed_entity_id=addressed_entity_id,
            social_event_category=map_speech_act_category(
                speech_act_type, has_commitment_offer, offer_confirmed, surface_type
            ),
            privacy=privacy,
        )
        self._by_utterance[key] = event
        return event

    def emit_episode(
        self,
        conversation_id: str,
        participant_ids: Tuple[str, ...],
        duration_game_minutes: int,
        ended_reason: EndedReason,
    ) -> EpisodeEvent:
        existing = self._episodes.get(conversation_id)
        if existing is not None:
            return existing  # 每会话至多一条 Episode
        category_counts: Dict[str, int] = {}
        utterance_count = 0
        for (cid, _index), event in self._by_utterance.items():
            if cid == conversation_id:
                utterance_count += 1
                category_counts[event.social_event_category] = (
                    category_counts.get(event.social_event_category, 0) + 1
                )
        episode = EpisodeEvent(
            event_id=generate_ulid(),
            conversation_id=conversation_id,
            participant_ids=participant_ids,
            duration_game_minutes=duration_game_minutes,
            utterance_count=utterance_count,
            category_counts=category_counts,
            ended_reason=ended_reason,
        )
        self._episodes[conversation_id] = episode
        return episode

    @staticmethod
    def assert_no_delta_fields(event_payload: Dict) -> None:
        """RULE-DIALOGUE-054：事件不携带目标向量/delta 建议/「好感 +5」"""
        forbidden = {"delta", "target_vector", "affection_delta", "trust_delta",
                     "suggested_delta"}
        bad = forbidden & set(event_payload)
        if bad:
            raise SocialEventError(
                "DIALOGUE_EVENT_CARRIES_DELTA",
                f"dialogue events must not carry delta fields: {sorted(bad)}",
            )


#: RULE-DIALOGUE-080：玩家 utterance 分类器关键词（确定性规则）
_PLAYER_CLASSIFY_PATTERNS: List[Tuple[SpeechActType, re.Pattern]] = [
    (SpeechActType.APOLOGIZE, re.compile(r"(对不起|抱歉|不好意思|认错)")),
    (SpeechActType.COMFORT, re.compile(r"(别难过|没事的|会好的|节哀|加油)")),
    (SpeechActType.WARN, re.compile(r"(小心|危险|注意|别去)")),
    (SpeechActType.REFUSE, re.compile(r"(不行|拒绝|不可能|免谈)")),
    (SpeechActType.PROMISE, re.compile(r"(答应|保证|一定|我承诺)")),
    (SpeechActType.NEGOTIATE, re.compile(r"(便宜点|讨价还价|再少|优惠)")),
    (SpeechActType.REQUEST, re.compile(r"(请|拜托|帮我|能否)")),
    (SpeechActType.ASK, re.compile(r"(吗？|呢？|\?|？|什么|哪里|谁)")),
    (SpeechActType.FAREWELL, re.compile(r"(再见|告辞|拜拜|先走了)")),
    (SpeechActType.GREET, re.compile(r"(你好|早上好|晚上好|嗨|哈喽)")),
]


class PlayerUtteranceClassifier:
    """
    RULE-DIALOGUE-080：玩家 utterance 在提交事务内定类。

    (b) 分类失败/不确定 → 默认 inform（fail closed 到最低社会影响类别）；
    (c) 承诺表达按未确认承诺处理（smalltalk）；
    (d) 幂等键 (conversation_id, utterance_index)，同文本同上下文同结果。
    """

    def __init__(self) -> None:
        self._classified: Dict[Tuple[str, int], SpeechActType] = {}

    def classify(
        self, conversation_id: str, utterance_index: int, text: str
    ) -> SpeechActType:
        key = (conversation_id, utterance_index)
        if key in self._classified:
            return self._classified[key]
        surface = SpeechActType.INFORM
        for act_type, pattern in _PLAYER_CLASSIFY_PATTERNS:
            if pattern.search(text):
                surface = act_type
                break
        self._classified[key] = surface
        return surface
