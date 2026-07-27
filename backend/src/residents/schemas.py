"""
居民系统 Schema 版本定义

符合 DOC-RESIDENT-001 规范：
- 定义所有 Schema 版本常量
- 确保版本一致性
"""

# Resident Aggregate Schema Version
RESIDENT_AGGREGATE_SCHEMA_VERSION = 1

# Sub-Schema Versions
IDENTITY_SCHEMA_VERSION = 1
PERSONALITY_SCHEMA_VERSION = 1
NEEDS_SCHEMA_VERSION = 1
CAPABILITY_SCHEMA_VERSION = 1
ASSIGNMENT_SCHEMA_VERSION = 1
HEALTH_SCHEMA_VERSION = 1
LIFECYCLE_SCHEMA_VERSION = 1
ROUTINE_SCHEMA_VERSION = 1

# Schema IDs (用于序列化和验证)
SCHEMA_IDS = {
    "resident_aggregate": "schema.resident.aggregate.v1",
    "identity": "schema.resident.identity.v1",
    "personality": "schema.resident.personality.v1",
    "needs_state": "schema.resident.needs_state.v1",
    "capability_state": "schema.resident.capability_state.v1",
    "assignment_state": "schema.resident.assignment_state.v1",
    "health_state": "schema.resident.health_state.v1",
    "lifecycle": "schema.resident.lifecycle.v1",
    "routine_state": "schema.resident.routine_state.v1",
}
