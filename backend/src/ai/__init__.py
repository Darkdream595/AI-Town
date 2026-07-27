"""
AI 编排模块

docs/05-ai-orchestration（DOC-AI-001..012）的实现。
"""

from .catalog import (
    ACTION_CATALOG,
    CatalogEntry,
    SemanticViolation,
    catalog_action_set,
    catalog_digest,
    validate_cross_field_semantics,
)
from .cognition import (
    COGNITION_EDGES,
    CognitionEnvelope,
    CognitionRun,
    CognitionStage,
    CognitionTransitionError,
    DecisionReference,
)
from .constants import (
    ACTION_IDS,
    RETRYABLE_FAILURES,
    AbortCondition,
    ActionId,
    PlanKind,
    ProviderFailureKind,
    ProposalEmotion,
    SecretLabel,
    ValidationOutcomeKind,
)
from .context import (
    ContextItem,
    DecisionContextV1,
    DisclosureGrant,
    SourceKind,
    VisibilityProof,
    budget_context,
    filter_subjective_context,
)
from .planning import (
    DailyGoal,
    DailyPlan,
    HourlyIntent,
    PlanLedger,
    PlanStatus,
    PlanTransitionError,
)
from .prompt_registry import (
    LAYER_ORDER,
    ComposedMessage,
    PromptLayer,
    PromptRegistry,
    PromptRegistryError,
    PromptRegistryRecord,
    build_default_registry,
    compose_messages,
    sanitize_untrusted_text,
)
from .provider import (
    FakeModelProvider,
    ModelRequestV1,
    NormalizedModelResponse,
    ProviderProfile,
    ThinkingPolicy,
    classify_provider_error,
    default_deepseek_profile,
    parse_provider_response,
    route_thinking_policy,
)
from .budget import (
    TOKEN_BUDGETS,
    ArtifactCache,
    CachedArtifact,
    CacheKeyComponents,
    UsageRecord,
    build_usage_record,
    compute_cache_key,
    estimate_tokens,
)
from .queue import (
    AIRequest,
    QueueFullError,
    RequestQueue,
    RequestState,
    compute_request_jitter_ms,
)
from .schema import (
    ACTION_PROPOSAL_SCHEMA,
    ACTION_PROPOSAL_SCHEMA_ID,
    SERVER_ENVELOPE_FIELDS,
    DecodedProposal,
    SchemaDecodeError,
    SchemaError,
    decode_proposal,
    proposal_from_dict,
    schema_action_ids,
    schema_branch_ids,
    schema_parameter_def_ids,
)
from .utility_fallback import (
    FALLBACK_FORBIDDEN_ACTIONS,
    SURVIVAL_WHITELIST,
    FallbackEpisode,
    FallbackNoLegalCandidateError,
    LegalCombatOption,
    SurvivalCandidate,
    UtilityInputs,
    compute_utility_score,
    select_survival_candidate,
    select_tactical_option,
)
from .validation import (
    INTENT_CRITICAL_FIELDS,
    REPAIR_WHITELIST,
    RepairNotPossibleError,
    RepairResult,
    ReplanLoopBreaker,
    ValidationOutcome,
    ValidationPipeline,
    ValidationStage,
    attempt_bounded_repair,
    verify_intent_preserved,
)

__all__ = [name for name in dir() if not name.startswith("_")]
