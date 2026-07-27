"""
Memory 记忆与社交模块

docs/06-memory-social（DOC-MEMORY-001..012）的实现。
"""

from .access import (
    AccessDecision,
    AccessDecisionKind,
    AccessLevel,
    AccessPolicy,
    AccessPurpose,
    AccessSnapshot,
    ContextItemEnvelope,
    RelationshipRule,
    SecretBoundaryError,
    authorize_memory_access,
    scan_authorized_context,
)
from .belief import (
    DuplicateEvidenceError,
    EvidenceKind,
    KnowledgeState,
    SemanticBeliefState,
    query_knowledge_state,
    reconcile_belief,
    reconciliation_delta,
)
from .consolidation import (
    CONSOLIDATION_VERSION,
    ConsolidationLedger,
    ConsolidationSourceMetadata,
    ConsolidationState,
    check_consolidation_eligibility,
    compute_lineage_hash,
)
from .record import (
    MEMORY_KINDS,
    MEMORY_RECORD_SCHEMA,
    MEMORY_STATES,
    SOURCE_KINDS,
    MemorySchemaError,
    memory_metadata_projection,
    validate_memory_record,
)
from .relationship import (
    DIMENSIONS,
    DISTRIBUTION_ORDER,
    DuplicateEffectError,
    EvidenceEntry,
    RelationshipDeltaSet,
    RelationshipEdge,
    RelationshipVector,
    apply_relationship_event,
    compute_applied_deltas,
)
from .retention import (
    COLD_THRESHOLD_Q1000,
    REACTIVATION_THRESHOLD_Q1000,
    MemoryStateMachine,
    RetentionClass,
    RetentionDecision,
    TombstoneAudit,
    TombstoneStateError,
    apply_importance_delta,
    compute_strength_q1000,
    evaluate_retention,
    retention_factor_q1000,
)
from .retrieval import (
    AuthorizedMemoryContext,
    ComponentScores,
    RetrievedRecord,
    RetrievalCandidate,
    RetrievalLimits,
    commitment_urgency_q1000,
    compute_score_q1000,
    emotion_match_q1000,
    participant_match_q1000,
    recency_q1000,
    retrieve_authorized_memories,
    weighted_jaccard_q1000,
)
from .rumor import (
    MAX_CHAIN_HOPS,
    ChainHop,
    ChainValidationError,
    RumorChain,
    compute_next_confidence_q1000,
    select_distortion_operation,
    validate_and_append_hop,
)
from .write import (
    Eligibility,
    EligibilityResult,
    MemoryWriteCandidate,
    WriteKeyConflictError,
    WriteKeyStore,
    WriteLifecycle,
    canonical_candidate_hash,
    compute_write_key,
    evaluate_write_eligibility,
)

__all__ = [name for name in dir() if not name.startswith("_")]
