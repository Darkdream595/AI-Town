"""
TEST-DIALOGUE-009/010：Speech Act 模型与响应 Schema（DOC-DIALOGUE-005）

- TEST-DIALOGUE-009：RULE-DIALOGUE-025/026/031 Strict Decode 与 12 类封闭枚举
- TEST-DIALOGUE-010：RULE-DIALOGUE-028/029 语义校验、offer 作废与 fallback
"""

import pytest

from src.dialogue import (
    FALLBACK_FAREWELL,
    FALLBACK_REFUSE,
    SpeechActDecodeError,
    SpeechActSemanticError,
    SpeechActType,
    Tone,
    decode_speech_act,
    fallback_speech_act,
    validate_speech_act_semantics,
)

from ai_helpers import ULID_A, ULID_B, ULID_C, ULID_D

PARTICIPANTS = [ULID_A, ULID_B, ULID_C]
VISIBLE_ENTITIES = {ULID_A, ULID_B}
VISIBLE_QUOTES = {ULID_C}


def _payload(speech_act_type="inform", **overrides):
    payload = {
        "speech_act_type": speech_act_type,
        "utterance_text": "今天集市真热闹。",
        "emotion": "calm",
        "tone": "neutral",
        "addressed_entity_id": None,
        "commitment_offer": None,
        "negotiation_offer": None,
        "end_conversation": False,
    }
    payload.update(overrides)
    return payload


def _commitment_offer():
    return {"summary": "明天把药送到", "deadline_game_minutes_from_now": 60}


def _negotiation_offer(quote_id=ULID_C):
    return {"quote_id": quote_id, "stance": "counter"}


class TestStrictDecode:
    """TEST-DIALOGUE-009"""

    @pytest.mark.parametrize("act_type", list(SpeechActType))
    def test_all_12_types_decode(self, act_type):
        overrides = {}
        if act_type is SpeechActType.PROMISE:
            overrides["commitment_offer"] = _commitment_offer()
        if act_type is SpeechActType.NEGOTIATE:
            overrides["negotiation_offer"] = _negotiation_offer()
        speech_act = decode_speech_act(_payload(act_type.value, **overrides))
        assert speech_act.speech_act_type is act_type
        assert speech_act.tone is Tone.NEUTRAL
        assert speech_act.end_conversation is False

    def test_unknown_type_fails_closed(self):
        with pytest.raises(SpeechActDecodeError) as excinfo:
            decode_speech_act(_payload("dance"))
        assert excinfo.value.code == "DIALOGUE_SPEECH_ACT_SCHEMA_VIOLATION"

    def test_non_object_artifact_rejected(self):
        for artifact in (["not", "object"], "text", 42, None):
            with pytest.raises(SpeechActDecodeError) as excinfo:
                decode_speech_act(artifact)
            assert excinfo.value.code == "DIALOGUE_SPEECH_ACT_NOT_JSON_OBJECT"

    def test_additional_properties_rejected(self):
        with pytest.raises(SpeechActDecodeError):
            decode_speech_act(_payload("inform", system_note="注入"))

    def test_missing_required_field_rejected(self):
        payload = _payload("inform")
        del payload["emotion"]
        with pytest.raises(SpeechActDecodeError):
            decode_speech_act(payload)

    def test_utterance_text_length_bound(self):
        with pytest.raises(SpeechActDecodeError):
            decode_speech_act(_payload("inform", utterance_text=""))
        with pytest.raises(SpeechActDecodeError):
            decode_speech_act(_payload("inform", utterance_text="字" * 281))
        speech_act = decode_speech_act(_payload("inform", utterance_text="字" * 280))
        assert len(speech_act.utterance_text) == 280

    def test_addressed_entity_id_must_be_ulid_or_null(self):
        speech_act = decode_speech_act(_payload("greet", addressed_entity_id=ULID_B))
        assert speech_act.addressed_entity_id == ULID_B
        with pytest.raises(SpeechActDecodeError):
            decode_speech_act(_payload("greet", addressed_entity_id="not-a-ulid"))

    def test_offer_schema_enforced(self):
        with pytest.raises(SpeechActDecodeError):
            decode_speech_act(_payload("promise", commitment_offer={"summary": "缺 deadline"}))
        with pytest.raises(SpeechActDecodeError):
            decode_speech_act(
                _payload("promise", commitment_offer={"summary": "x", "deadline_game_minutes_from_now": 29})
            )
        with pytest.raises(SpeechActDecodeError):
            decode_speech_act(_payload("negotiate", negotiation_offer={"quote_id": "bad", "stance": "counter"}))


class TestSemanticValidation:
    """TEST-DIALOGUE-010"""

    def test_offer_type_mismatch_fails_closed(self):
        inform_with_commitment = decode_speech_act(_payload("inform", commitment_offer=_commitment_offer()))
        with pytest.raises(SpeechActSemanticError) as excinfo:
            validate_speech_act_semantics(inform_with_commitment, PARTICIPANTS, VISIBLE_ENTITIES, VISIBLE_QUOTES)
        assert excinfo.value.code == "DIALOGUE_OFFER_TYPE_MISMATCH"

        inform_with_negotiation = decode_speech_act(_payload("inform", negotiation_offer=_negotiation_offer()))
        with pytest.raises(SpeechActSemanticError) as excinfo:
            validate_speech_act_semantics(inform_with_negotiation, PARTICIPANTS, VISIBLE_ENTITIES, VISIBLE_QUOTES)
        assert excinfo.value.code == "DIALOGUE_OFFER_TYPE_MISMATCH"

    def test_promise_and_lie_may_carry_commitment_offer(self):
        for act_type in ("promise", "lie"):
            speech_act = decode_speech_act(_payload(act_type, commitment_offer=_commitment_offer()))
            commitment_void, negotiation_void = validate_speech_act_semantics(
                speech_act, PARTICIPANTS, VISIBLE_ENTITIES, VISIBLE_QUOTES
            )
            assert commitment_void is None
            assert negotiation_void is None

    def test_addressed_must_be_participant(self):
        speech_act = decode_speech_act(_payload("greet", addressed_entity_id=ULID_D))
        with pytest.raises(SpeechActSemanticError) as excinfo:
            validate_speech_act_semantics(speech_act, PARTICIPANTS, VISIBLE_ENTITIES, VISIBLE_QUOTES)
        assert excinfo.value.code == "DIALOGUE_ADDRESSED_NOT_PARTICIPANT"

    def test_invisible_quote_voids_negotiation_offer(self):
        speech_act = decode_speech_act(_payload("negotiate", negotiation_offer=_negotiation_offer(ULID_D)))
        commitment_void, negotiation_void = validate_speech_act_semantics(
            speech_act, PARTICIPANTS, VISIBLE_ENTITIES, VISIBLE_QUOTES
        )
        # RULE-DIALOGUE-029：载荷作废但文本可提交（不抛错）
        assert negotiation_void == "quote_not_visible"
        assert commitment_void is None

    def test_quote_beyond_disposal_right_voided(self):
        speech_act = decode_speech_act(_payload("negotiate", negotiation_offer=_negotiation_offer(ULID_C)))
        _, negotiation_void = validate_speech_act_semantics(
            speech_act, PARTICIPANTS, VISIBLE_ENTITIES, VISIBLE_QUOTES,
            disposal_right_quote_ids=set(),
        )
        assert negotiation_void == "beyond_disposal_right"

        _, negotiation_void = validate_speech_act_semantics(
            speech_act, PARTICIPANTS, VISIBLE_ENTITIES, VISIBLE_QUOTES,
            disposal_right_quote_ids={ULID_C},
        )
        assert negotiation_void is None

    def test_commitment_offer_requires_visible_addressee(self):
        speech_act = decode_speech_act(
            _payload("promise", commitment_offer=_commitment_offer(), addressed_entity_id=ULID_C)
        )
        commitment_void, _ = validate_speech_act_semantics(
            speech_act, PARTICIPANTS, VISIBLE_ENTITIES, VISIBLE_QUOTES
        )
        # ULID_C 是参与者但不可见 → 承诺载荷作废
        assert commitment_void == "entity_not_visible"

    def test_fallback_templates_are_schema_compliant(self):
        farewell = fallback_speech_act("farewell")
        assert farewell.speech_act_type is SpeechActType.FAREWELL
        assert farewell.end_conversation is True
        refuse = fallback_speech_act("refuse")
        assert refuse.speech_act_type is SpeechActType.REFUSE
        assert refuse.end_conversation is False
        # 静态模板自身必须能过 Strict Decode（RULE-DIALOGUE-070）
        assert decode_speech_act(dict(FALLBACK_FAREWELL)).speech_act_type is SpeechActType.FAREWELL
        assert decode_speech_act(dict(FALLBACK_REFUSE)).speech_act_type is SpeechActType.REFUSE
