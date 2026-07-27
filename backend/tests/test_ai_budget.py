"""
测试 Token、缓存与成本控制

覆盖 TEST-AI-029/030/031/032（DOC-AI-008 §11）
"""

import pytest

from src.ai import (
    TOKEN_BUDGETS,
    ArtifactCache,
    CachedArtifact,
    CacheKeyComponents,
    PlanKind,
    build_usage_record,
    compute_cache_key,
    estimate_tokens,
)

from ai_helpers import ULID_A


def _components(**overrides) -> CacheKeyComponents:
    defaults = dict(
        profile_id="provider.deepseek.v4_flash.v1",
        model="deepseek-v4-flash",
        prompt_id="resident-action/v1",
        template_sha256="sha256:8b30d4f31c17",
        artifact_schema_id="schema.ai.action_proposal.v1",
        context_hash="sha256:8de5c7a8d5f0",
        action_catalog_digest="sha256:cat1",
        thinking_enabled=False,
        reasoning_effort=None,
        max_output_tokens=700,
        access_policy_version=1,
    )
    defaults.update(overrides)
    return CacheKeyComponents(**defaults)


class TestTokenBudgets:
    """TEST-AI-029：token budget/truncation boundaries"""

    def test_budget_table(self):
        assert TOKEN_BUDGETS[PlanKind.IMMEDIATE_ACTION][:2] == (3000, 700)
        assert TOKEN_BUDGETS[PlanKind.HOURLY_INTENT][:2] == (4500, 1000)
        assert TOKEN_BUDGETS[PlanKind.DAILY_PLAN][:2] == (7000, 1600)
        assert TOKEN_BUDGETS[PlanKind.COMBAT_TURN][:2] == (2500, 600)

    def test_estimate_tokens_conservative(self):
        # 保守字符估计 +20% 预留
        assert estimate_tokens("x" * 300) >= 100


class TestCacheKeyMutationMatrix:
    """TEST-AI-030：任一安全/Prompt/Schema/model/version 改变均 cache miss"""

    @pytest.mark.parametrize(
        "field,new_value",
        [
            ("profile_id", "provider.other.v1"),
            ("model", "deepseek-other"),
            ("prompt_id", "resident-action/v2"),
            ("template_sha256", "sha256:changed"),
            ("artifact_schema_id", "schema.ai.action_proposal.v2"),
            ("context_hash", "sha256:changed"),
            ("action_catalog_digest", "sha256:changed"),
            ("thinking_enabled", True),
            ("reasoning_effort", "high"),
            ("max_output_tokens", 701),
            ("access_policy_version", 2),
        ],
    )
    def test_mutation_changes_key(self, field, new_value):
        base_key = compute_cache_key(_components())
        mutated_key = compute_cache_key(_components(**{field: new_value}))
        assert base_key != mutated_key

    def test_same_components_same_key(self):
        assert compute_cache_key(_components()) == compute_cache_key(_components())


class TestArtifactCache:
    """缓存行为（RULE-AI-044/046）"""

    def test_put_get(self):
        cache = ArtifactCache()
        artifact = CachedArtifact(
            artifact_bytes=b"{}", input_tokens=10, output_tokens=5,
            stored_at_monotonic_s=100.0, ttl_seconds=300.0,
        )
        cache.put("key1", artifact)
        assert cache.get("key1", now_monotonic_s=200.0) is artifact

    def test_expired_entry_treated_as_miss(self):
        cache = ArtifactCache()
        artifact = CachedArtifact(
            artifact_bytes=b"{}", input_tokens=10, output_tokens=5,
            stored_at_monotonic_s=100.0, ttl_seconds=300.0,
        )
        cache.put("key1", artifact)
        assert cache.get("key1", now_monotonic_s=500.0) is None

    def test_combat_turn_not_cached(self):
        # TTL=0（当前 turn only）不写入
        cache = ArtifactCache()
        artifact = CachedArtifact(
            artifact_bytes=b"{}", input_tokens=10, output_tokens=5,
            stored_at_monotonic_s=100.0, ttl_seconds=0.0,
        )
        cache.put("key1", artifact)
        assert len(cache) == 0

    def test_lru_eviction(self):
        cache = ArtifactCache(max_entries=3)
        for index in range(5):
            cache.put(
                f"key{index}",
                CachedArtifact(
                    artifact_bytes=b"{}", input_tokens=1, output_tokens=1,
                    stored_at_monotonic_s=100.0, ttl_seconds=300.0,
                ),
            )
        assert len(cache) == 3
        assert cache.get("key0", now_monotonic_s=100.0) is None
        assert cache.get("key4", now_monotonic_s=100.0) is not None

    def test_invalidate(self):
        cache = ArtifactCache()
        cache.put(
            "key1",
            CachedArtifact(
                artifact_bytes=b"{}", input_tokens=1, output_tokens=1,
                stored_at_monotonic_s=100.0, ttl_seconds=None,
            ),
        )
        cache.invalidate("key1")
        assert cache.get("key1", now_monotonic_s=100.0) is None


class TestUsageAndPrice:
    """TEST-AI-032：usage/price missing/estimated display"""

    def test_provider_reported_usage(self):
        usage = build_usage_record(
            request_id=ULID_A,
            profile_id="provider.deepseek.v4_flash.v1",
            input_tokens=2450,
            output_tokens=312,
            estimated_input=2500,
            estimated_output=400,
        )
        assert usage.usage_source == "provider_reported"
        assert usage.input_tokens == 2450

    def test_estimated_usage_when_provider_silent(self):
        usage = build_usage_record(
            request_id=ULID_A,
            profile_id="provider.deepseek.v4_flash.v1",
            input_tokens=None,
            output_tokens=None,
            estimated_input=2500,
            estimated_output=400,
        )
        assert usage.usage_source == "estimated"
        assert usage.input_tokens == 2500

    def test_no_price_profile_no_fake_amount(self):
        # 无 Price Profile 时不显示伪精确金额（RULE-AI-047）
        usage = build_usage_record(
            request_id=ULID_A,
            profile_id="provider.deepseek.v4_flash.v1",
            input_tokens=100,
            output_tokens=50,
            estimated_input=100,
            estimated_output=50,
        )
        assert usage.estimated_cost_minor_unit is None
        assert usage.price_profile_id is None

    def test_price_profile_computes_cost(self):
        usage = build_usage_record(
            request_id=ULID_A,
            profile_id="provider.deepseek.v4_flash.v1",
            input_tokens=1000,
            output_tokens=500,
            estimated_input=1000,
            estimated_output=500,
            price_per_input_token=0.001,
            price_per_output_token=0.002,
            price_profile_id="price.local.v1",
        )
        assert usage.estimated_cost_minor_unit == 2
        assert usage.price_profile_id == "price.local.v1"
