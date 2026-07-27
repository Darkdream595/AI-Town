"""
TEST-DIALOGUE-011/012：情绪与语气呈现（DOC-DIALOGUE-006）

- TEST-DIALOGUE-011：RULE-DIALOGUE-033/035 8 情绪 × 6 tone 全组合确定性 Portrait Cue
- TEST-DIALOGUE-012：RULE-DIALOGUE-034/036/037 critical leak cue、零写回与玩家 fail closed
"""

import pytest

from src.dialogue import (
    CommittedEmotionBand,
    EmotionPresentationError,
    PORTRAIT_CUE_CATALOG,
    Tone,
    band_of_intensity,
    compute_presentation,
)
from src.dialogue.emotion import DIALOGUE_EMOTION_VALUES, LEAK_CUES, assert_no_writeback

from ai_helpers import ULID_A

CONV = "01K1CVRX000000000000000001"


class TestPortraitCueCatalog:
    """TEST-DIALOGUE-011"""

    def test_catalog_covers_all_48_combinations(self):
        assert len(DIALOGUE_EMOTION_VALUES) == 8
        assert len(list(Tone)) == 6
        for emotion in DIALOGUE_EMOTION_VALUES:
            for tone in Tone:
                assert (emotion, tone.value) in PORTRAIT_CUE_CATALOG

    @pytest.mark.parametrize("emotion", sorted(DIALOGUE_EMOTION_VALUES))
    @pytest.mark.parametrize("tone", list(Tone), ids=lambda t: t.value)
    def test_mapping_deterministic_for_same_snapshot(self, emotion, tone):
        first = compute_presentation(CONV, 0, ULID_A, emotion, tone, "calm", 0)
        second = compute_presentation(CONV, 0, ULID_A, emotion, tone, "calm", 0)
        assert first == second
        assert first.portrait_cue == PORTRAIT_CUE_CATALOG[(emotion, tone.value)]
        # 非 critical：掩饰不产生 leak cue
        assert first.leak_cue is None

    def test_unknown_emotion_rejected(self):
        with pytest.raises(EmotionPresentationError) as excinfo:
            compute_presentation(CONV, 0, ULID_A, "meh", Tone.NEUTRAL, "calm", 0)
        assert excinfo.value.code == "DIALOGUE_EMOTION_ENUM_MISMATCH"


class TestCriticalLeakAndBoundary:
    """TEST-DIALOGUE-012"""

    def test_critical_masking_always_leaks(self):
        mapping = compute_presentation(CONV, 0, ULID_A, "calm", Tone.NEUTRAL, "anger", 800)
        assert mapping.committed_emotion_band == CommittedEmotionBand.CRITICAL
        assert mapping.leak_cue == LEAK_CUES["anger"]

    def test_below_critical_masking_stays_hidden(self):
        mapping = compute_presentation(CONV, 0, ULID_A, "calm", Tone.NEUTRAL, "anger", 799)
        assert mapping.committed_emotion_band == CommittedEmotionBand.PRESSING
        assert mapping.leak_cue is None

    def test_critical_without_masking_has_no_leak(self):
        mapping = compute_presentation(CONV, 0, ULID_A, "anger", Tone.HOSTILE, "anger", 1000)
        assert mapping.leak_cue is None

    @pytest.mark.parametrize(
        "intensity,expected_band",
        [
            (0, CommittedEmotionBand.SATISFIED),
            (249, CommittedEmotionBand.SATISFIED),
            (250, CommittedEmotionBand.NOTICE),
            (499, CommittedEmotionBand.NOTICE),
            (500, CommittedEmotionBand.PRESSING),
            (799, CommittedEmotionBand.PRESSING),
            (800, CommittedEmotionBand.CRITICAL),
            (1000, CommittedEmotionBand.CRITICAL),
        ],
    )
    def test_band_boundaries(self, intensity, expected_band):
        assert band_of_intensity(intensity) == expected_band

    def test_projection_carries_band_not_number(self):
        mapping = compute_presentation(CONV, 0, ULID_A, "joy", Tone.WARM, "joy", 900)
        # RULE-DIALOGUE-036：只暴露段位，Committed 数值不进入呈现层
        assert mapping.committed_emotion_band in CommittedEmotionBand.ALL
        assert not hasattr(mapping, "committed_intensity_q1000")

    def test_player_has_no_expressed_emotion(self):
        with pytest.raises(EmotionPresentationError) as excinfo:
            compute_presentation(CONV, 0, ULID_A, "joy", Tone.WARM, "joy", 100, is_player=True)
        assert excinfo.value.code == "DIALOGUE_PLAYER_NO_EXPRESSED_EMOTION"

    def test_presentation_never_writes_back(self):
        assert_no_writeback(("anger", 800), ("anger", 800))
        with pytest.raises(EmotionPresentationError) as excinfo:
            assert_no_writeback(("anger", 800), ("calm", 200))
        assert excinfo.value.code == "DIALOGUE_PRESENTATION_WRITEBACK"
