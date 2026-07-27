"""
AI 编排常量定义

符合 DOC-AI-004 / DOC-AI-005：19 个 Action 的集合唯一真源。
"""

from enum import Enum


class ActionId(str, Enum):
    """19 个 Action ID（DOC-AI-004 wire enum）"""

    MOVE_TO = "move_to"
    TALK = "talk"
    WORK = "work"
    REST = "rest"
    EAT = "eat"
    BUY = "buy"
    SELL = "sell"
    GIVE_ITEM = "give_item"
    USE_OBJECT = "use_object"
    CRAFT = "craft"
    GATHER = "gather"
    EXPLORE = "explore"
    CAST_SPELL = "cast_spell"
    START_ENCOUNTER = "start_encounter"
    COMBAT_ACTION = "combat_action"
    BUILD = "build"
    REPAIR = "repair"
    WAIT = "wait"
    OBSERVE = "observe"


#: 与 DOC-AI-004 schema enum 顺序一致的列表
ACTION_IDS: list[str] = [a.value for a in ActionId]


class ProposalEmotion(str, Enum):
    """Proposal emotion enum（DOC-AI-004）"""

    CALM = "calm"
    JOY = "joy"
    SADNESS = "sadness"
    ANGER = "anger"
    FEAR = "fear"
    ANXIETY = "anxiety"
    DISGUST = "disgust"
    HOPE = "hope"


class AbortCondition(str, Enum):
    """abort_conditions 白名单（DOC-AI-004）"""

    DANGER_DETECTED = "danger_detected"
    CRITICAL_NEED = "critical_need"
    HEALTH_RESTRICTED = "health_restricted"
    TARGET_UNAVAILABLE = "target_unavailable"
    DESTINATION_UNREACHABLE = "destination_unreachable"
    PERMISSION_DENIED = "permission_denied"
    RESOURCE_UNAVAILABLE = "resource_unavailable"
    RESERVATION_CONFLICT = "reservation_conflict"
    DEADLINE_MISSED = "deadline_missed"
    SHOP_CLOSED = "shop_closed"
    INSUFFICIENT_FUNDS = "insufficient_funds"
    QUOTE_CHANGED = "quote_changed"
    COMBAT_STARTED = "combat_started"
    PLAYER_INTERRUPT = "player_interrupt"
    WORLD_EVENT_CHANGED = "world_event_changed"
    ACTION_NO_LONGER_USEFUL = "action_no_longer_useful"


class SecretLabel(str, Enum):
    """六级秘密标签（DOC-AI-002）"""

    PUBLIC = "public"
    COMMUNITY = "community"
    FACTION = "faction"
    RELATIONSHIP = "relationship"
    PERSONAL = "personal"
    SHARED_SECRET = "shared_secret"


class PlanKind(str, Enum):
    """认知计划层（DOC-AI-006 / DOC-AI-007）"""

    DAILY_PLAN = "daily_plan"
    HOURLY_INTENT = "hourly_intent"
    IMMEDIATE_ACTION = "immediate_action"
    COMBAT_TURN = "combat_turn"


class ProviderFailureKind(str, Enum):
    """Provider 失败分类（DOC-AI-007 §8）"""

    CONNECT_TIMEOUT = "connect_timeout"
    REQUEST_TIMEOUT = "request_timeout"
    RATE_LIMITED = "rate_limited"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    EMPTY_RESPONSE = "empty_response"
    RESPONSE_TOO_LARGE = "response_too_large"
    INVALID_JSON = "invalid_json"
    SCHEMA_INVALID = "schema_invalid"
    CONTENT_REFUSED = "content_refused"
    CONFIG_INVALID = "config_invalid"
    CANCELLED = "cancelled"


#: 可按 DOC-AI-009 重试的失败类别
RETRYABLE_FAILURES: frozenset[ProviderFailureKind] = frozenset(
    {
        ProviderFailureKind.CONNECT_TIMEOUT,
        ProviderFailureKind.PROVIDER_UNAVAILABLE,
        ProviderFailureKind.RATE_LIMITED,
    }
)


class ValidationOutcomeKind(str, Enum):
    """校验 outcome 分类（DOC-AI-010 §3）"""

    VALID = "VALID"
    REPAIRABLE = "REPAIRABLE"
    REPLAN_REQUIRED = "REPLAN_REQUIRED"
    FORBIDDEN = "FORBIDDEN"
    TRANSIENT_OWNER_UNAVAILABLE = "TRANSIENT_OWNER_UNAVAILABLE"
