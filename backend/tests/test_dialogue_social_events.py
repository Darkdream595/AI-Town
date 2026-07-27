"""
TEST-DIALOGUE-017/018/029：对话的记忆与关系影响（DOC-DIALOGUE-009）

- TEST-DIALOGUE-017：RULE-DIALOGUE-053 版本化类别映射 12 类穷举与 lie 表面映射
- TEST-DIALOGUE-018：RULE-DIALOGUE-054/055/058 无 delta 字段、Episode 聚合与幂等
- TEST-DIALOGUE-029：RULE-DIALOGUE-080 玩家分类器确定性、默认 inform、承诺不补发
"""

import dataclasses

import pytest

from src.dialogue import (
    CATEGORY_MAP_VERSION,
    ConversationPrivacy,
    EndedReason,
    PlayerUtteranceClassifier,
    SocialEventEmitter,
    SocialEventError,
    SpeechActType,
    map_speech_act_category,
)

from ai_helpers import ULID_A, ULID_B

CONV = "01K1CVRX000000000000000001"


class TestCategoryMap:
    """TEST-DIALOGUE-017"""

    @pytest.mark.parametrize(
        "act_type,expected_category",
        [
            (SpeechActType.COMFORT, "dialogue.comforted"),
            (SpeechActType.APOLOGIZE, "dialogue.apologized"),
            (SpeechActType.WARN, "dialogue.warned"),
            (SpeechActType.REFUSE, "dialogue.refused"),
            (SpeechActType.NEGOTIATE, "dialogue.negotiated"),
            (SpeechActType.GREET, "dialogue.smalltalk"),
            (SpeechActType.INFORM, "dialogue.smalltalk"),
            (SpeechActType.ASK, "dialogue.smalltalk"),
            (SpeechActType.REQUEST, "dialogue.smalltalk"),
            (SpeechActType.FAREWELL, "dialogue.smalltalk"),
        ],
    )
    def test_direct_mappings(self, act_type, expected_category):
        assert map_speech_act_category(act_type) == expected_category

    def test_promise_requires_confirmed_offer(self):
        assert map_speech_act_category(SpeechActType.PROMISE) == "dialogue.smalltalk"
        assert (
            map_speech_act_category(SpeechActType.PROMISE, has_commitment_offer=True)
            == "dialogue.smalltalk"
        )
        assert (
            map_speech_act_category(
                SpeechActType.PROMISE, has_commitment_offer=True, offer_confirmed=True
            )
            == "dialogue.promise_made"
        )

    def test_lie_maps_by_surface_type(self):
        assert (
            map_speech_act_category(SpeechActType.LIE, surface_type=SpeechActType.COMFORT)
            == "dialogue.comforted"
        )
        assert (
            map_speech_act_category(SpeechActType.LIE, surface_type=SpeechActType.WARN)
            == "dialogue.warned"
        )
        # 无表面类型时按 inform 处理
        assert map_speech_act_category(SpeechActType.LIE) == "dialogue.smalltalk"

    def test_all_12_types_have_exactly_one_category(self):
        assert len(list(SpeechActType)) == 12
        for act_type in SpeechActType:
            category = map_speech_act_category(act_type)
            assert category.startswith("dialogue.")


class TestEventEmission:
    """TEST-DIALOGUE-018"""

    def _emitter_with_acts(self):
        emitter = SocialEventEmitter()
        emitter.emit_speech_act_event(
            CONV, 0, ULID_A, ULID_B, SpeechActType.COMFORT, ConversationPrivacy.PUBLIC
        )
        emitter.emit_speech_act_event(
            CONV, 1, ULID_B, ULID_A, SpeechActType.COMFORT, ConversationPrivacy.PUBLIC
        )
        emitter.emit_speech_act_event(
            CONV, 2, ULID_A, ULID_B, SpeechActType.INFORM, ConversationPrivacy.PUBLIC
        )
        return emitter

    def test_speech_act_event_payload(self):
        emitter = SocialEventEmitter()
        event = emitter.emit_speech_act_event(
            CONV, 0, ULID_A, ULID_B, SpeechActType.WARN, ConversationPrivacy.PUBLIC
        )
        assert event.event_type == "dialogue.speech_act_committed/v1"
        assert event.social_event_category == "dialogue.warned"
        assert event.privacy is ConversationPrivacy.PUBLIC
        assert event.category_map_version == CATEGORY_MAP_VERSION

    def test_speech_act_event_idempotent_replay(self):
        emitter = SocialEventEmitter()
        first = emitter.emit_speech_act_event(
            CONV, 0, ULID_A, ULID_B, SpeechActType.WARN, ConversationPrivacy.PUBLIC
        )
        second = emitter.emit_speech_act_event(
            CONV, 0, ULID_A, ULID_B, SpeechActType.WARN, ConversationPrivacy.PUBLIC
        )
        assert first is second

    def test_episode_aggregates_and_is_idempotent(self):
        emitter = self._emitter_with_acts()
        episode = emitter.emit_episode(
            CONV, (ULID_A, ULID_B), duration_game_minutes=12, ended_reason=EndedReason.COMPLETED
        )
        assert episode.event_type == "dialogue.conversation_episode/v1"
        assert episode.utterance_count == 3
        assert episode.category_counts == {"dialogue.comforted": 2, "dialogue.smalltalk": 1}
        assert episode.ended_reason is EndedReason.COMPLETED

        replay = emitter.emit_episode(
            CONV, (ULID_A, ULID_B), duration_game_minutes=99, ended_reason=EndedReason.TIMEOUT
        )
        assert replay is episode  # 每会话至多一条 Episode

    def test_episode_isolated_per_conversation(self):
        emitter = self._emitter_with_acts()
        other = emitter.emit_episode(
            "01K1CVRX000000000000000099", (ULID_A, ULID_B), 5, EndedReason.COMPLETED
        )
        assert other.utterance_count == 0
        assert other.category_counts == {}

    def test_events_carry_no_delta_fields(self):
        emitter = SocialEventEmitter()
        event = emitter.emit_speech_act_event(
            CONV, 0, ULID_A, ULID_B, SpeechActType.COMFORT, ConversationPrivacy.PUBLIC
        )
        field_names = {f.name for f in dataclasses.fields(event)}
        assert not ({"delta", "target_vector", "affection_delta", "trust_delta"} & field_names)

        SocialEventEmitter.assert_no_delta_fields({"social_event_category": "dialogue.comforted"})
        with pytest.raises(SocialEventError) as excinfo:
            SocialEventEmitter.assert_no_delta_fields({"affection_delta": 5})
        assert excinfo.value.code == "DIALOGUE_EVENT_CARRIES_DELTA"


class TestPlayerUtteranceClassifier:
    """TEST-DIALOGUE-029"""

    @pytest.mark.parametrize(
        "text,expected_type",
        [
            ("对不起，我错了。", SpeechActType.APOLOGIZE),
            ("别难过，会好的。", SpeechActType.COMFORT),
            ("小心，前面危险。", SpeechActType.WARN),
            ("不行，免谈。", SpeechActType.REFUSE),
            ("我保证一定来。", SpeechActType.PROMISE),
            ("便宜点吧。", SpeechActType.NEGOTIATE),
            ("请帮我一下。", SpeechActType.REQUEST),
            ("你叫什么名字？", SpeechActType.ASK),
            ("再见。", SpeechActType.FAREWELL),
            ("你好。", SpeechActType.GREET),
            ("今天集市人很多。", SpeechActType.INFORM),
        ],
    )
    def test_rule_based_classification(self, text, expected_type):
        classifier = PlayerUtteranceClassifier()
        assert classifier.classify(CONV, 0, text) is expected_type

    def test_unmatched_defaults_to_inform(self):
        classifier = PlayerUtteranceClassifier()
        # fail closed 到最低社会影响类别
        assert classifier.classify(CONV, 0, "嗯。") is SpeechActType.INFORM

    def test_deterministic_and_idempotent(self):
        classifier = PlayerUtteranceClassifier()
        first = classifier.classify(CONV, 0, "我保证一定来。")
        second = classifier.classify(CONV, 0, "我保证一定来。")
        assert first is second
        # 同文本在不同上下文同结果
        other = classifier.classify("01K1CVRX000000000000000088", 0, "我保证一定来。")
        assert other is first

    def test_promise_maps_to_smalltalk_without_confirmation(self):
        # RULE-DIALOGUE-080(c)：玩家承诺按未确认处理，不补发 promise_made
        classifier = PlayerUtteranceClassifier()
        surface = classifier.classify(CONV, 0, "我保证一定来。")
        assert map_speech_act_category(surface) == "dialogue.smalltalk"
