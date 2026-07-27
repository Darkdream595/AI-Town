"""
Speech Act 模型与响应 Schema（DOC-DIALOGUE-005）

- RULE-DIALOGUE-025：居民响应必须是单个 SpeechActV1 strict JSON
- RULE-DIALOGUE-026：12 类封闭枚举，未知类型 fail closed
- RULE-DIALOGUE-027：refuse 是一等合法结果
- RULE-DIALOGUE-028：lie 的 Deception Intent 只写入说话者记忆与服务器审计
- RULE-DIALOGUE-029：offer 引用校验失败则载荷作废、文本可提交
- RULE-DIALOGUE-030：提交是原子事务
- RULE-DIALOGUE-031：utterance_text 上限 280、纯文本
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

import jsonschema

from ..foundation.id_generator import ULID_PATTERN
from .constants import SpeechActType, Tone

#: DES-DIALOGUE-005：唯一机器提取真源（注册 $id）
SPEECH_ACT_V1_SCHEMA: Dict = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "schema://ai-town/dialogue/speech-act/v1",
    "type": "object",
    "required": [
        "speech_act_type",
        "utterance_text",
        "emotion",
        "tone",
        "addressed_entity_id",
        "commitment_offer",
        "negotiation_offer",
        "end_conversation",
    ],
    "properties": {
        "speech_act_type": {
            "enum": [t.value for t in SpeechActType],
        },
        "utterance_text": {"type": "string", "minLength": 1, "maxLength": 280},
        "emotion": {
            "enum": [
                "calm", "joy", "sadness", "anger",
                "fear", "anxiety", "disgust", "hope",
            ],
        },
        "tone": {"enum": [t.value for t in Tone]},
        "addressed_entity_id": {
            "oneOf": [
                {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
                {"type": "null"},
            ],
        },
        "commitment_offer": {
            "oneOf": [
                {
                    "type": "object",
                    "required": ["summary", "deadline_game_minutes_from_now"],
                    "properties": {
                        "summary": {"type": "string", "minLength": 1, "maxLength": 120},
                        "deadline_game_minutes_from_now": {
                            "type": "integer", "minimum": 30, "maximum": 43200,
                        },
                    },
                    "additionalProperties": False,
                },
                {"type": "null"},
            ],
        },
        "negotiation_offer": {
            "oneOf": [
                {
                    "type": "object",
                    "required": ["quote_id", "stance"],
                    "properties": {
                        "quote_id": {
                            "type": "string",
                            "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$",
                        },
                        "stance": {"enum": ["accept", "counter", "decline"]},
                    },
                    "additionalProperties": False,
                },
                {"type": "null"},
            ],
        },
        "end_conversation": {"type": "boolean"},
    },
    "additionalProperties": False,
}

_validator = jsonschema.Draft202012Validator(SPEECH_ACT_V1_SCHEMA)


class SpeechActDecodeError(Exception):
    """Strict Decode 失败（RULE-DIALOGUE-025）"""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


class SpeechActSemanticError(Exception):
    """语义校验失败（§8：不重试模型，直接 fallback）"""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True)
class CommitmentOffer:
    summary: str
    deadline_game_minutes_from_now: int


@dataclass(frozen=True)
class NegotiationOffer:
    quote_id: str
    stance: str  # accept / counter / decline


@dataclass(frozen=True)
class SpeechActV1:
    """Strict Decode 产物；conversation_id/responder_id 由 Server Envelope 追加"""

    speech_act_type: SpeechActType
    utterance_text: str
    emotion: str
    tone: Tone
    addressed_entity_id: Optional[str]
    commitment_offer: Optional[CommitmentOffer]
    negotiation_offer: Optional[NegotiationOffer]
    end_conversation: bool


def decode_speech_act(model_artifact: object) -> SpeechActV1:
    """
    RULE-DIALOGUE-025：Strict Decode；失败绝不把自由文本当作 utterance。
    """
    if not isinstance(model_artifact, dict):
        raise SpeechActDecodeError(
            "DIALOGUE_SPEECH_ACT_NOT_JSON_OBJECT",
            f"artifact must be a JSON object, got {type(model_artifact).__name__}",
        )
    errors = sorted(_validator.iter_errors(model_artifact), key=lambda e: e.path)
    if errors:
        first = errors[0]
        raise SpeechActDecodeError(
            "DIALOGUE_SPEECH_ACT_SCHEMA_VIOLATION",
            f"{list(first.path)}: {first.message}",
        )
    return SpeechActV1(
        speech_act_type=SpeechActType(model_artifact["speech_act_type"]),
        utterance_text=model_artifact["utterance_text"],
        emotion=model_artifact["emotion"],
        tone=Tone(model_artifact["tone"]),
        addressed_entity_id=model_artifact["addressed_entity_id"],
        commitment_offer=(
            CommitmentOffer(**model_artifact["commitment_offer"])
            if model_artifact["commitment_offer"] is not None
            else None
        ),
        negotiation_offer=(
            NegotiationOffer(**model_artifact["negotiation_offer"])
            if model_artifact["negotiation_offer"] is not None
            else None
        ),
        end_conversation=model_artifact["end_conversation"],
    )


def validate_speech_act_semantics(
    speech_act: SpeechActV1,
    participant_ids: List[str],
    visible_entity_ids: Set[str],
    visible_quote_ids: Set[str],
    disposal_right_quote_ids: Optional[Set[str]] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    §6 第 2 步语义校验 + RULE-DIALOGUE-029 引用校验。

    返回 (commitment_offer_void_reason, negotiation_offer_void_reason)；
    offer 作废不阻断文本提交（RULE-DIALOGUE-029）。类型与载荷不一致、
    addressed 非参与者属结构性失败，抛 SpeechActSemanticError。
    """
    # §7：promise 才可带 commitment_offer、negotiate 才可带 negotiation_offer
    if speech_act.commitment_offer is not None and speech_act.speech_act_type not in (
        SpeechActType.PROMISE,
        SpeechActType.LIE,  # §7：lie 可带虚假承诺
    ):
        raise SpeechActSemanticError(
            "DIALOGUE_OFFER_TYPE_MISMATCH",
            "commitment_offer only allowed with promise/lie",
        )
    if speech_act.negotiation_offer is not None and (
        speech_act.speech_act_type is not SpeechActType.NEGOTIATE
    ):
        raise SpeechActSemanticError(
            "DIALOGUE_OFFER_TYPE_MISMATCH",
            "negotiation_offer only allowed with negotiate",
        )
    if (
        speech_act.addressed_entity_id is not None
        and speech_act.addressed_entity_id not in participant_ids
    ):
        raise SpeechActSemanticError(
            "DIALOGUE_ADDRESSED_NOT_PARTICIPANT",
            f"addressed {speech_act.addressed_entity_id} not in participant set",
        )

    negotiation_void: Optional[str] = None
    if speech_act.negotiation_offer is not None:
        offer = speech_act.negotiation_offer
        if offer.quote_id not in visible_quote_ids:
            # RULE-DIALOGUE-029：引用不可见 → 载荷作废并记录 reason
            negotiation_void = "quote_not_visible"
        elif (
            disposal_right_quote_ids is not None
            and offer.quote_id not in disposal_right_quote_ids
        ):
            negotiation_void = "beyond_disposal_right"

    commitment_void: Optional[str] = None
    if speech_act.commitment_offer is not None:
        if (
            speech_act.addressed_entity_id is not None
            and speech_act.addressed_entity_id not in visible_entity_ids
        ):
            commitment_void = "entity_not_visible"

    return commitment_void, negotiation_void


#: §8 fallback：解码失败耗尽后的模板化 Speech Act（固定文案，不调模型）
FALLBACK_FAREWELL: Dict = {
    "speech_act_type": "farewell",
    "utterance_text": "（居民似乎有心事，匆匆告辞了。）",
    "emotion": "calm",
    "tone": "neutral",
    "addressed_entity_id": None,
    "commitment_offer": None,
    "negotiation_offer": None,
    "end_conversation": True,
}

FALLBACK_REFUSE: Dict = {
    "speech_act_type": "refuse",
    "utterance_text": "（居民摇了摇头，没有回答。）",
    "emotion": "calm",
    "tone": "neutral",
    "addressed_entity_id": None,
    "commitment_offer": None,
    "negotiation_offer": None,
    "end_conversation": False,
}


def fallback_speech_act(kind: str = "farewell") -> SpeechActV1:
    """RULE-DIALOGUE-070：fallback 模板天然合规（静态审计）"""
    template = FALLBACK_FAREWELL if kind == "farewell" else FALLBACK_REFUSE
    return decode_speech_act(dict(template))


def validate_ulid_or_none(value: Optional[str], field_name: str) -> None:
    if value is not None and not ULID_PATTERN.match(value):
        raise SpeechActDecodeError(
            "DIALOGUE_ULID_INVALID", f"{field_name} is not a valid ULID"
        )
