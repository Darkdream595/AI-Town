"""
情绪与语气表达（DOC-DIALOGUE-006）

- RULE-DIALOGUE-032：Expressed/Tone 是呈现层数据，永不写回 Committed Emotion
- RULE-DIALOGUE-033：emotion 枚举与 RESIDENT/AI 同一注册表（复用 ai.constants）
- RULE-DIALOGUE-034：critical（intensity>=800）掩饰受限，叠加 leak cue
- RULE-DIALOGUE-035：同输入快照下 Portrait Cue 映射完全确定
- RULE-DIALOGUE-036：UI 只展示呈现结果，Committed 数值不暴露
- RULE-DIALOGUE-037：玩家无 Expressed Emotion，系统不替玩家表演
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from ..ai.constants import ProposalEmotion
from .constants import CRITICAL_INTENSITY_Q1000, Tone


class EmotionPresentationError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


#: RULE-DIALOGUE-033：dialogue emotion 与 AI/RESIDENT 共享同一枚举注册表
DIALOGUE_EMOTION_ENUM = ProposalEmotion
DIALOGUE_EMOTION_VALUES = tuple(e.value for e in ProposalEmotion)


class CommittedEmotionBand:
    """DES-DIALOGUE-006：只携带段位，不携带数值（RULE-DIALOGUE-036）"""

    SATISFIED = "satisfied"
    NOTICE = "notice"
    PRESSING = "pressing"
    CRITICAL = "critical"

    ALL = frozenset({SATISFIED, NOTICE, PRESSING, CRITICAL})


def band_of_intensity(intensity_q1000: int) -> str:
    """Committed intensity → band（段位边界 250/500/800）"""
    if intensity_q1000 >= CRITICAL_INTENSITY_Q1000:
        return CommittedEmotionBand.CRITICAL
    if intensity_q1000 >= 500:
        return CommittedEmotionBand.PRESSING
    if intensity_q1000 >= 250:
        return CommittedEmotionBand.NOTICE
    return CommittedEmotionBand.SATISFIED


#: 版本化 Portrait Cue Catalog：emotion × tone → cue（RULE-DIALOGUE-035 确定性）
PORTRAIT_CUE_CATALOG_VERSION = 1


def _build_portrait_catalog() -> Dict[Tuple[str, str], str]:
    catalog: Dict[Tuple[str, str], str] = {}
    for emotion in DIALOGUE_EMOTION_VALUES:
        for tone in Tone:
            catalog[(emotion, tone.value)] = f"{emotion}_{tone.value}"
    # 特例键：guard 系组合有美术语义名（示例固化，资产由 ART 域实现）
    catalog[("calm", "formal")] = "calm_guarded"
    return catalog


PORTRAIT_CUE_CATALOG: Dict[Tuple[str, str], str] = _build_portrait_catalog()

#: critical 掩饰时的微表情 cue（RULE-DIALOGUE-034）
LEAK_CUES: Dict[str, str] = {
    "anger": "brow_tension",
    "fear": "eye_flicker",
    "anxiety": "lip_press",
    "sadness": "shoulder_sag",
    "disgust": "nose_wrinkle",
    "joy": "eye_crinkle",
    "calm": "jaw_set",
    "hope": "gaze_lift",
}


@dataclass(frozen=True)
class PresentationMapping:
    """DES-DIALOGUE-006：随 speech_act_committed 投影给渲染层"""

    conversation_id: str
    utterance_index: int
    speaker_id: str
    expressed_emotion: str
    tone: str
    portrait_cue: str
    leak_cue: Optional[str]
    committed_emotion_band: str


def compute_presentation(
    conversation_id: str,
    utterance_index: int,
    speaker_id: str,
    expressed_emotion: str,
    tone: Tone,
    committed_emotion: str,
    committed_intensity_q1000: int,
    is_player: bool = False,
) -> PresentationMapping:
    """
    RULE-DIALOGUE-035：同输入快照完全确定的映射（纯函数查表）。

    RULE-DIALOGUE-037：玩家 utterance 无呈现情绪，调用方应跳过本函数；
    此处对玩家 fail closed。
    """
    if is_player:
        raise EmotionPresentationError(
            "DIALOGUE_PLAYER_NO_EXPRESSED_EMOTION",
            "player utterances have no expressed emotion",
        )
    if expressed_emotion not in DIALOGUE_EMOTION_VALUES:
        raise EmotionPresentationError(
            "DIALOGUE_EMOTION_ENUM_MISMATCH",
            f"emotion {expressed_emotion!r} not in shared registry",
        )

    portrait_cue = PORTRAIT_CUE_CATALOG.get((expressed_emotion, tone.value))
    if portrait_cue is None:
        # §8：Catalog 缺失回退 neutral，禁止渲染层自造映射
        portrait_cue = PORTRAIT_CUE_CATALOG[(expressed_emotion, Tone.NEUTRAL.value)]

    band = band_of_intensity(committed_intensity_q1000)
    leak_cue: Optional[str] = None
    if (
        band == CommittedEmotionBand.CRITICAL
        and expressed_emotion != committed_emotion
    ):
        # RULE-DIALOGUE-034：critical 下掩饰受限，叠加不可抑制微表情
        leak_cue = LEAK_CUES.get(committed_emotion, "brow_tension")

    return PresentationMapping(
        conversation_id=conversation_id,
        utterance_index=utterance_index,
        speaker_id=speaker_id,
        expressed_emotion=expressed_emotion,
        tone=tone.value,
        portrait_cue=portrait_cue,
        leak_cue=leak_cue,
        committed_emotion_band=band,
    )


def assert_no_writeback(
    committed_before: Tuple[str, int], committed_after: Tuple[str, int]
) -> None:
    """RULE-DIALOGUE-032：呈现层永不写回 Committed Emotion"""
    if committed_before != committed_after:
        raise EmotionPresentationError(
            "DIALOGUE_PRESENTATION_WRITEBACK",
            "presentation layer must never mutate committed emotion",
        )
