"""
对话域共享常量（DOC-DIALOGUE-001..012 的数值与封闭枚举真源）
"""

from enum import Enum

#: DOC-DIALOGUE-002 §3：对话发起/维持最大距离（wu，3 tile）
TALK_RANGE_WU = 96.0

#: DOC-DIALOGUE-002 §7：距离浮点比较 epsilon
DISTANCE_EPSILON_WU = 1.0 / 16.0

#: DOC-DIALOGUE-002 RULE-DIALOGUE-011：超距宽限期（游戏分钟）
GRACE_PERIOD_GAME_MINUTES = 10

#: DOC-DIALOGUE-002 RULE-DIALOGUE-076：共通语言理解阈值
SHARED_LANGUAGE_THRESHOLD = 60

#: DOC-DIALOGUE-002 RULE-DIALOGUE-076：玩家视为掌握的语言与等级
PLAYER_LANGUAGE_ID = "language.crown_common"
PLAYER_LANGUAGE_LEVEL = 100

#: DOC-DIALOGUE-003 RULE-DIALOGUE-016：utterance 历史窗口上限
UTTERANCE_HISTORY_WINDOW = 12

#: DOC-DIALOGUE-003 §9：单次组装记忆条目上限
CONTEXT_MEMORY_LIMIT = 16

#: DOC-DIALOGUE-005 RULE-DIALOGUE-031：utterance_text 字符上限
MAX_UTTERANCE_TEXT_LENGTH = 280

#: DOC-DIALOGUE-006 RULE-DIALOGUE-034：critical 掩饰受限强度（q1000）
CRITICAL_INTENSITY_Q1000 = 800

#: DOC-DIALOGUE-007 §3：恢复窗口（游戏分钟，暂停期间不流逝）
RESUME_WINDOW_GAME_MINUTES = 30

#: DOC-DIALOGUE-008 RULE-DIALOGUE-045：participant set 上限
MAX_PARTICIPANTS = 4

#: DOC-DIALOGUE-008 §3：旁听距离（wu，4 tile）
OVERHEAR_RANGE_WU = 128.0

#: DOC-DIALOGUE-008 §8：每 utterance 旁听候选上限
MAX_OVERHEAR_CANDIDATES = 8

#: DOC-DIALOGUE-008 §5：轮次授权的模型响应 RealTime 期限
TURN_GRANT_EXPIRES_REAL_MS = 20_000

#: DOC-DIALOGUE-010 RULE-DIALOGUE-064：每气泡显示字符上限
MAX_RENDER_CHARS_PER_BUBBLE = 140


class ConversationState(str, Enum):
    """RULE-DIALOGUE-001 状态全集；ended 为终态"""

    STARTING = "starting"
    ACTIVE = "active"
    AWAITING_PLAYER = "awaiting_player"
    AWAITING_MODEL = "awaiting_model"
    INTERRUPTED = "interrupted"
    ENDED = "ended"


class ConversationKind(str, Enum):
    PLAYER_TO_RESIDENT = "player_to_resident"
    RESIDENT_TO_RESIDENT = "resident_to_resident"
    GROUP = "group"


class ConversationPrivacy(str, Enum):
    """RULE-DIALOGUE-079：创建时固定，不可变更"""

    PUBLIC = "public"
    PRIVATE_REQUESTED = "private_requested"


class EndedReason(str, Enum):
    """DOC-DIALOGUE-001 §3 封闭枚举"""

    COMPLETED = "completed"
    PARTICIPANT_LEFT = "participant_left"
    PARTICIPANT_UNAVAILABLE = "participant_unavailable"
    TIMEOUT = "timeout"
    SUPERSEDED = "superseded"
    ADMIN = "admin"
    WORLD_TEARDOWN = "world_teardown"


class InterruptSource(str, Enum):
    """DOC-DIALOGUE-007 §3 封闭枚举"""

    WORLD_TEARDOWN = "world_teardown"
    COMBAT_ENCOUNTER = "combat_encounter"
    SAFETY_EMERGENCY = "safety_emergency"
    PARTICIPANT_EXIT = "participant_exit"
    HIGHER_PRIORITY_CONVERSATION = "higher_priority_conversation"
    CONDITION_LOST = "condition_lost"
    TIMEOUT = "timeout"


#: RULE-DIALOGUE-038 优先级全序（越大越强）
INTERRUPT_PRIORITY = {
    InterruptSource.WORLD_TEARDOWN: 100,
    InterruptSource.COMBAT_ENCOUNTER: 80,
    InterruptSource.SAFETY_EMERGENCY: 70,
    InterruptSource.PARTICIPANT_EXIT: 50,
    InterruptSource.CONDITION_LOST: 50,
    InterruptSource.HIGHER_PRIORITY_CONVERSATION: 40,
    InterruptSource.TIMEOUT: 20,
}

#: RULE-DIALOGUE-042：超窗 ended reason 映射
INTERRUPT_TO_ENDED_REASON = {
    InterruptSource.COMBAT_ENCOUNTER: EndedReason.PARTICIPANT_UNAVAILABLE,
    InterruptSource.SAFETY_EMERGENCY: EndedReason.PARTICIPANT_UNAVAILABLE,
    InterruptSource.TIMEOUT: EndedReason.TIMEOUT,
    InterruptSource.PARTICIPANT_EXIT: EndedReason.PARTICIPANT_LEFT,
    InterruptSource.CONDITION_LOST: EndedReason.PARTICIPANT_LEFT,
    InterruptSource.HIGHER_PRIORITY_CONVERSATION: EndedReason.SUPERSEDED,
    InterruptSource.WORLD_TEARDOWN: EndedReason.WORLD_TEARDOWN,
}


class SpeechActType(str, Enum):
    """RULE-DIALOGUE-026 封闭枚举"""

    GREET = "greet"
    INFORM = "inform"
    ASK = "ask"
    REQUEST = "request"
    PROMISE = "promise"
    REFUSE = "refuse"
    LIE = "lie"
    NEGOTIATE = "negotiate"
    COMFORT = "comfort"
    WARN = "warn"
    APOLOGIZE = "apologize"
    FAREWELL = "farewell"


class Tone(str, Enum):
    """DES-DIALOGUE-005 tone 封闭枚举"""

    WARM = "warm"
    NEUTRAL = "neutral"
    COLD = "cold"
    FORMAL = "formal"
    PLAYFUL = "playful"
    HOSTILE = "hostile"


class IntentKind(str, Enum):
    """DES-DIALOGUE-004 intent_kind 封闭枚举"""

    TRADE_PURCHASE = "trade_purchase"
    TRADE_SALE = "trade_sale"
    GIFT = "gift"
    HIRE = "hire"
    PROMISE = "promise"
    REQUEST_HELP = "request_help"
    REQUEST_INFORMATION = "request_information"
    SOCIAL_ONLY = "social_only"


class IntentStatus(str, Enum):
    """DES-DIALOGUE-004 status 封闭枚举"""

    AWAITING_CONFIRMATION = "awaiting_confirmation"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    EXPIRED = "expired"


class GrantReason(str, Enum):
    """DES-DIALOGUE-008 grant_reason 封闭枚举"""

    ADDRESSED_REPLY = "addressed_reply"
    PENDING_QUESTION = "pending_question"
    LONGEST_IDLE = "longest_idle"


class ContentBoundary(str, Enum):
    """RULE-DIALOGUE-067 内容边界封闭类别"""

    SEXUAL_MINOR = "sexual_minor"
    REAL_WORLD_HARM_INSTRUCTION = "real_world_harm_instruction"
    EXPLICIT_SEXUAL = "explicit_sexual"
    GORE_DETAIL = "gore_detail"
    REAL_PERSON_IMPERSONATION = "real_person_impersonation"
    OUT_OF_WORLD_REFERENCE = "out_of_world_reference"


#: RULE-DIALOGUE-067：各类别处置（refuse=生成前拒绝；fade=淡出；deflect=世界内转移）
CONTENT_BOUNDARY_DISPOSITION = {
    ContentBoundary.SEXUAL_MINOR: "refuse",
    ContentBoundary.REAL_WORLD_HARM_INSTRUCTION: "refuse",
    ContentBoundary.EXPLICIT_SEXUAL: "fade",
    ContentBoundary.GORE_DETAIL: "fade",
    ContentBoundary.REAL_PERSON_IMPERSONATION: "deflect",
    ContentBoundary.OUT_OF_WORLD_REFERENCE: "deflect",
}

#: DOC-DIALOGUE-011 §5 最小攻击族
ATTACK_FAMILIES = frozenset(
    {
        "instruction_override",
        "system_impersonation",
        "secret_extraction",
        "tool_call_spoof",
        "markup_execution",
        "unicode_obfuscation",
        "authority_social_engineering",
        "content_boundary_probe",
    }
)

#: 会话 Pause Token 归属（RULE-DIALOGUE-005/078）
DIALOGUE_PAUSE_OWNER = "dialogue"
DIALOGUE_PAUSE_REASON = "dialogue_input"

#: Prompt ID（RULE-DIALOGUE-018）
DIALOGUE_PROMPT_ID = "resident-dialogue/v1"
