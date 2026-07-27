"""
EVENT 域常量与封闭枚举（DOC-EVENT-001..012）

所有跨模块共享的字面量集中在此，避免循环导入。
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 事件来源（RULE-EVENT-004）：七种，admin 必须带审计标记
# ---------------------------------------------------------------------------

EVENT_SOURCES = frozenset(
    {"time", "state", "resident", "player", "environment", "director", "admin"}
)

SEVERITIES = ("minor", "moderate", "major", "crisis")

#: RULE-EVENT-009：Narrative Pressure Budget 权重
SEVERITY_WEIGHT = {"minor": 1, "moderate": 2, "major": 4, "crisis": 8}

#: RULE-EVENT-009：全世界同时 active 权重和上限 / crisis 并发上限
ACTIVE_WEIGHT_CAP = 12
CRISIS_CONCURRENCY_CAP = 1

#: RULE-EVENT-002：单世界 active（含 escalated）实例上限
ACTIVE_EVENT_CAP = 16

#: RULE-EVENT-009：事件进入 aftermath 后预算线性返还周期（game minutes）
BUDGET_REFUND_GAME_MINUTES = 1440

#: RULE-EVENT-009：Calm Window = 无 moderate 以上新激活的连续区间，每 7 日至少 1 个
CALM_WINDOW_MIN_GAME_MINUTES = 1440
CALM_WINDOW_PERIOD_GAME_DAYS = 7
GAME_DAY_MINUTES = 1440

#: RULE-EVENT-011：重复灾害冷却下限（admin 可越过但仍占预算）
DISASTER_COOLDOWN_MIN_GAME_MINUTES = 4320

#: RULE-EVENT-026：单事件后果上限
CONSEQUENCE_CAP = 32

#: RULE-EVENT-022：open（offered/accepted/active）Quest 上限
QUEST_OPEN_CAP = 64

#: RULE-EVENT-040：单 Scene 建筑上限
SCENE_BUILDING_CAP = 256

#: RULE-EVENT-061：单 Diff Entry operations 上限（沿用 patch 预算）
DIFF_OPERATIONS_CAP = 256

#: 周期任务间隔（game minutes）
WEATHER_EVAL_INTERVAL = 30
DIRECTOR_REVIEW_INTERVAL = 360
DIRECTOR_FAILURE_BACKOFF_INTERVAL = 1440
DIRECTOR_MAX_CONSECUTIVE_FAILURES = 3
DIRECTOR_DAILY_PROPOSAL_CAP = 4
DECAY_EVAL_INTERVAL = 1440

#: RULE-EVENT-052：施工停滞判定（无 Work Session 的时长）
CONSTRUCTION_STALLED_GAME_MINUTES = 4320

# ---------------------------------------------------------------------------
# WorldEvent 生命周期（RULE-EVENT-003）
# ---------------------------------------------------------------------------

EVENT_STATES = frozenset(
    {
        "candidate",
        "scheduled",
        "active",
        "escalated",
        "resolved",
        "failed",
        "expired",
        "aftermath",
        "archived",
    }
)

#: 合法迁移表；active↔escalated 可往返；scheduled 到期未激活 → expired
EVENT_TRANSITIONS = frozenset(
    {
        ("candidate", "scheduled"),
        ("candidate", "active"),
        ("scheduled", "active"),
        ("scheduled", "expired"),
        ("active", "escalated"),
        ("escalated", "active"),
        ("active", "resolved"),
        ("active", "failed"),
        ("escalated", "resolved"),
        ("escalated", "failed"),
        ("resolved", "aftermath"),
        ("failed", "aftermath"),
        ("expired", "aftermath"),
        ("aftermath", "archived"),
        # scheduled 到期失效可直接归档（记录原因码，无 aftermath）
        ("expired", "archived"),
    }
)

TERMINAL_EVENT_STATES = frozenset({"resolved", "failed", "expired"})

# ---------------------------------------------------------------------------
# Quest 状态机（RULE-EVENT-019）
# ---------------------------------------------------------------------------

QUEST_STATES = frozenset(
    {
        "draft",
        "offered",
        "accepted",
        "active",
        "completed",
        "failed",
        "expired",
        "abandoned",
        "declined",
        "archived",
    }
)

QUEST_TRANSITIONS = frozenset(
    {
        ("draft", "offered"),
        ("offered", "accepted"),
        ("offered", "declined"),
        ("offered", "expired"),
        ("accepted", "active"),
        ("accepted", "expired"),
        ("accepted", "failed"),
        ("active", "completed"),
        ("active", "failed"),
        ("active", "expired"),
        ("active", "abandoned"),
        ("completed", "archived"),
        ("failed", "archived"),
        ("expired", "archived"),
        ("abandoned", "archived"),
        ("declined", "archived"),
    }
)

QUEST_OPEN_STATES = frozenset({"offered", "accepted", "active"})

#: RULE-EVENT-020：九类 Objective
OBJECTIVE_KINDS = frozenset(
    {
        "reach_location",
        "deliver_item",
        "talk_to",
        "craft_item",
        "protect_target",
        "investigate",
        "win_encounter",
        "repair_structure",
        "maintain_condition",
    }
)

OBJECTIVE_ORDERINGS = frozenset({"sequential", "parallel"})

# ---------------------------------------------------------------------------
# 后果与善后（DOC-EVENT-005）
# ---------------------------------------------------------------------------

CONSEQUENCE_PHASES = frozenset(
    {"on_scheduled", "on_active", "on_escalated", "on_terminal", "on_aftermath"}
)

AFTERMATH_TASK_KINDS = frozenset(
    {
        "casualty_care",
        "rescue",
        "compensation",
        "reconstruction",
        "cleanup",
        "commemoration",
    }
)

AFTERMATH_TASK_STATES = frozenset({"pending", "in_progress", "completed", "cancelled"})

AFTERMATH_TASK_TRANSITIONS = frozenset(
    {
        ("pending", "in_progress"),
        ("pending", "cancelled"),
        ("in_progress", "completed"),
        ("in_progress", "cancelled"),
    }
)

#: 后果分发的目标域 → 端口路由键
CONSEQUENCE_TARGET_DOMAINS = frozenset(
    {"econ", "resident", "map", "memory", "quest", "environment"}
)

# ---------------------------------------------------------------------------
# 天气（DOC-EVENT-006）
# ---------------------------------------------------------------------------

WEATHER_IDS = (
    "clear",
    "cloudy",
    "rain.light",
    "rain.heavy",
    "fog",
    "thunderstorm",
    "snow",
    "magical_cold_snap",
    "mana_anomaly",
)

#: 降水类天气 → 火源点 wet 判定
PRECIPITATION_WEATHERS = frozenset({"rain.light", "rain.heavy", "thunderstorm", "snow"})

SEASONS = frozenset({"spring", "summer", "autumn", "winter"})

#: 转移矩阵行和容差
TRANSITION_ROW_TOLERANCE = 1e-9

# ---------------------------------------------------------------------------
# 建筑（DOC-EVENT-007..010）
# ---------------------------------------------------------------------------

PHYSICAL_STATES = (
    "foundation",
    "construction",
    "intact",
    "lightly_damaged",
    "severely_damaged",
    "ruins",
)

CONSTRUCTION_PHASES = (
    "planning",
    "clearing",
    "foundation_work",
    "structure_work",
    "fitting",
    "acceptance",
)

#: 阶段完成会产生几何变更（四件套同步）的阶段
GEOMETRIC_PHASES = frozenset({"clearing", "foundation_work", "structure_work", "acceptance"})

#: RULE-EVENT-037：foundation/construction 必须携带有效 phase；其余 phase=None
PHASE_REQUIRED_STATES = frozenset({"foundation", "construction"})

DAMAGE_SOURCES = frozenset(
    {"combat", "fire", "flood", "storm", "mana_anomaly", "decay"}
)

#: RULE-EVENT-056：damage_points → physical_state 阈值表（唯一映射）
DEFAULT_DAMAGE_THRESHOLDS = (
    (0, 9, "intact"),
    (10, 39, "lightly_damaged"),
    (40, 79, "severely_damaged"),
    (80, None, "ruins"),
)

ORIENTATIONS = (0, 90, 180, 270)

# ---------------------------------------------------------------------------
# WorldDiff（DOC-EVENT-011）
# ---------------------------------------------------------------------------

DIFF_KINDS = frozenset(
    {"road", "building", "environment_blockade", "semantic", "terrain_object"}
)

DIFF_LAYERS = frozenset({"structure", "walkability", "collision", "semantic"})

DIFF_OPS = frozenset({"add", "replace", "remove"})

# ---------------------------------------------------------------------------
# 周期任务种类（TIME Scheduled Event 的 occurrence kind）
# ---------------------------------------------------------------------------

OCCURRENCE_KINDS = frozenset(
    {
        "event_activate",
        "event_deadline",
        "quest_deadline",
        "trigger_eval",
        "weather_eval",
        "director_review",
        "decay_eval",
        "construction_stall_check",
        "consequence_retry",
    }
)
