"""
EVENT 域：世界事件、触发器、Director、Quest、后果、天气、建筑、施工、WorldDiff

DOC-EVENT-001..012 的实现。唯一写入口 MapChangeCommitter 保证
业务状态 + NavigationPatch + DomainEvent + WorldDiff 四件套原子提交。
"""

from .budget import BudgetError, NarrativePressureLedger
from .buildings import (
    Building,
    BuildingError,
    BuildingService,
    BuildingTemplate,
    BuildingTemplateRegistry,
    RelocationFailed,
)
from .consequences import (
    AftermathBoard,
    AftermathTask,
    ConsequenceDispatcher,
    ConsequenceError,
    OwnerUnavailable,
    PortRejected,
    TargetMissing,
)
from .constants import (
    ACTIVE_EVENT_CAP,
    ACTIVE_WEIGHT_CAP,
    AFTERMATH_TASK_KINDS,
    CONSEQUENCE_CAP,
    DAMAGE_SOURCES,
    EVENT_SOURCES,
    EVENT_STATES,
    EVENT_TRANSITIONS,
    PHYSICAL_STATES,
    CONSTRUCTION_PHASES,
    QUEST_OPEN_CAP,
    SEVERITY_WEIGHT,
    WEATHER_IDS,
)
from .construction import ConstructionError, ConstructionService
from .diff import (
    DiffEntry,
    DiffError,
    DiffOperation,
    MapChangeCommitter,
    WorldDiffLog,
)
from .director import (
    DIRECTOR_MODEL,
    DIRECTOR_PROMPT_ID,
    DirectorError,
    DirectorReview,
    WorldSummaryProjectionBuilder,
    repair_proposal,
    validate_proposal,
)
from .engine import EventEngine, EventError, WorldEvent
from .environment import (
    EVENT_MAGIC_PORT_METHODS,
    EnvironmentError,
    EnvironmentService,
    EventMagicPort,
)
from .fixtures import (
    TEST_COVERAGE_MATRIX,
    DeterministicIdFactory,
    FakeDirectorModel,
    FakeEconPort,
    FakeMapPort,
    FakeMemoryPort,
    FakeResidentPort,
    MapAccessError,
    audit_coverage,
    make_event_world,
    make_id_factory,
)
from .log import AppendOnlyEventLog
from .placement import (
    Parcel,
    ParcelRegistry,
    PlacementError,
    PlacementService,
    validate_ai_build_proposal,
)
from .quests import QuestEngine, QuestError, QuestInstance, match_objective
from .rng import EventRngHub, trigger_stream_name, weather_stream_name
from .templates import (
    AftermathTaskSpec,
    ConsequenceSpec,
    DirectorWhitelist,
    EventTemplate,
    EventTemplateRegistry,
    ObjectiveSpec,
    QuestTemplate,
    QuestTemplateRegistry,
    RewardSpec,
    TemplateError,
    TriggerRegistry,
    TriggerSpec,
)
from .triggers import TriggerEngine, TriggerError, evaluate_condition, scopes_intersect
from .weather import (
    RegionWeatherState,
    TransitionMatrix,
    WeatherError,
    WeatherService,
    default_catalog,
)
from .world import EventWorld, WorldError

__all__ = [name for name in dir() if not name.startswith("_")]
