"""
TEST-DIALOGUE-005/006：对话上下文构建（DOC-DIALOGUE-003）

- TEST-DIALOGUE-005：RULE-DIALOGUE-016 窗口 12 + 摘要标记；RULE-DIALOGUE-012 中途加入截断
- TEST-DIALOGUE-006：RULE-DIALOGUE-014 未判定整份 rejected；超时降级；
  RULE-DIALOGUE-018 hash 持久化不含 Prompt
"""

import pytest

from src.dialogue.context import (
    AccessDecision,
    ContextBuildError,
    DialogueContextBuilder,
    HistorySummary,
    compute_context_hash,
)
from src.dialogue.conversation import Utterance
from src.dialogue.constants import (
    CONTEXT_MEMORY_LIMIT,
    DIALOGUE_PROMPT_ID,
    UTTERANCE_HISTORY_WINDOW,
)

from ai_helpers import ULID_A, ULID_B, ULID_C

CONV = "01K1CVRX000000000000000001"


def _utterances(count: int) -> list[Utterance]:
    return [
        Utterance(
            utterance_index=i,
            speaker_id=ULID_A if i % 2 == 0 else ULID_B,
            text=f"第 {i} 句",
            committed_revision=i + 1,
            game_time=100 + i,
            command_id=f"u-{i}",
        )
        for i in range(count)
    ]


def _build(builder: DialogueContextBuilder, utterances, **overrides):
    kwargs = {
        "conversation_id": CONV,
        "responder_id": ULID_A,
        "participant_ids": [ULID_A, ULID_B],
        "utterances": utterances,
        "observed_revision": 50,
        "game_time": 1000,
    }
    kwargs.update(overrides)
    return builder.build(**kwargs)


class TestHistoryWindow:
    """TEST-DIALOGUE-005"""

    def test_window_caps_at_12_with_marked_summary(self):
        context = _build(DialogueContextBuilder(), _utterances(15))
        assert len(context.utterance_history) == UTTERANCE_HISTORY_WINDOW == 12
        assert [u.utterance_index for u in context.utterance_history] == list(range(3, 15))
        assert context.history_summary is not None
        assert context.history_summary.is_summary is True
        assert context.history_summary.covered_utterances == (0, 1, 2)

    def test_exactly_12_has_no_summary(self):
        context = _build(DialogueContextBuilder(), _utterances(12))
        assert len(context.utterance_history) == 12
        assert context.history_summary is None

    def test_13_has_single_entry_summary(self):
        context = _build(DialogueContextBuilder(), _utterances(13))
        assert context.history_summary.covered_utterances == (0,)

    def test_mid_conversation_join_truncates_history(self):
        # RULE-DIALOGUE-012：加入事件之前的 utterance 对新参与者不可见
        context = _build(DialogueContextBuilder(), _utterances(15), joined_at_utterance_index=10)
        assert [u.utterance_index for u in context.utterance_history] == [10, 11, 12, 13, 14]
        assert context.history_summary is None

    def test_summary_must_be_explicitly_marked(self):
        with pytest.raises(ContextBuildError) as excinfo:
            HistorySummary(covered_utterances=(0,), text="伪装成原话", is_summary=False)
        assert excinfo.value.code == "DIALOGUE_SUMMARY_FLAG_REQUIRED"

    def test_speaker_projection_minimized(self):
        context = _build(
            DialogueContextBuilder(),
            _utterances(3),
            participant_ids=[ULID_A, ULID_B, ULID_C],
            display_names={ULID_B: "贝拉", ULID_C: "卡尔"},
        )
        projections = {p.entity_id: p for p in context.speaker_projections}
        # 响应者自己不进入投影；只含公开身份与关系引用
        assert set(projections) == {ULID_B, ULID_C}
        assert projections[ULID_B].display_name == "贝拉"
        assert projections[ULID_B].public_identity == {"display_name": "贝拉"}


class TestAccessGateAndPersistence:
    """TEST-DIALOGUE-006"""

    def test_allowed_entries_pass(self):
        decisions = [
            AccessDecision("d1", "m1", True),
            AccessDecision("d2", "m2", True),
        ]
        builder = DialogueContextBuilder(
            memory_retriever=lambda cid, rid: (["m1", "m2"], decisions, False)
        )
        context = _build(builder, _utterances(3))
        assert context.retrieved_memory_ids == ("m1", "m2")
        assert context.access_decision_ids == ("d1", "d2")
        assert context.context_degraded is False

    def test_denied_entry_rejects_whole_context(self):
        decisions = [AccessDecision("d1", "m1", False)]
        builder = DialogueContextBuilder(
            memory_retriever=lambda cid, rid: (["m1"], decisions, False)
        )
        with pytest.raises(ContextBuildError) as excinfo:
            _build(builder, _utterances(3))
        assert excinfo.value.code == "DIALOGUE_CONTEXT_ACCESS_DENIED"

    def test_unjudged_entry_rejects_whole_context(self):
        builder = DialogueContextBuilder(
            memory_retriever=lambda cid, rid: (["m1"], [], False)
        )
        with pytest.raises(ContextBuildError) as excinfo:
            _build(builder, _utterances(3))
        assert excinfo.value.code == "DIALOGUE_CONTEXT_UNJUDGED_ENTRY"

    def test_retrieval_timeout_degrades_without_relaxing_filter(self):
        builder = DialogueContextBuilder(
            memory_retriever=lambda cid, rid: (["m1"], [], True)
        )
        context = _build(builder, _utterances(3))
        assert context.context_degraded is True
        assert context.retrieved_memory_ids == ()

    def test_memory_entry_limit(self):
        ids = [f"m{i}" for i in range(20)]
        decisions = [AccessDecision(f"d{i}", f"m{i}", True) for i in range(20)]
        builder = DialogueContextBuilder(
            memory_retriever=lambda cid, rid: (ids, decisions, False)
        )
        context = _build(builder, _utterances(3))
        assert len(context.retrieved_memory_ids) == CONTEXT_MEMORY_LIMIT == 16

    def test_context_hash_deterministic_and_sensitive(self):
        builder = DialogueContextBuilder()
        first = _build(builder, _utterances(5))
        second = _build(builder, _utterances(5))
        assert first.context_hash == second.context_hash

        altered = _utterances(5)
        altered[2] = Utterance(2, ULID_A, "改动", 3, 102, "u-2")
        third = _build(builder, altered)
        assert third.context_hash != first.context_hash

    def test_persistence_holds_hash_not_prompt(self):
        builder = DialogueContextBuilder()
        context = _build(builder, _utterances(3))
        [record] = builder.persisted_records()
        assert record["context_hash"] == context.context_hash
        assert record["prompt_id"] == DIALOGUE_PROMPT_ID == "resident-dialogue/v1"
        assert record["observed_revision"] == 50
        assert set(record) == {"context_hash", "prompt_id", "observed_revision"}
        DialogueContextBuilder.assert_no_prompt_persisted(record)
        with pytest.raises(ContextBuildError) as excinfo:
            DialogueContextBuilder.assert_no_prompt_persisted({**record, "prompt_text": "..."})
        assert excinfo.value.code == "DIALOGUE_PERSISTENCE_BOUNDARY_VIOLATION"

    def test_compute_context_hash_covers_semantic_inputs(self):
        views = tuple(_build(DialogueContextBuilder(), _utterances(2)).utterance_history)
        hash_a = compute_context_hash(CONV, ULID_A, 50, views, ())
        hash_b = compute_context_hash(CONV, ULID_A, 51, views, ())
        hash_c = compute_context_hash(CONV, ULID_A, 50, views, ("m1",))
        assert hash_a != hash_b  # observed_revision 参与 hash
        assert hash_a != hash_c  # 记忆条目参与 hash
