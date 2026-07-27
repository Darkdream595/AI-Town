"""
Token、缓存与成本控制

符合 DOC-AI-008：
- RULE-AI-044：cache hit 仍必须 strict decode、stale check 和最新 Domain validation
- RULE-AI-045：缓存键包含全部行为/访问相关版本与 Context hash
- RULE-AI-046：缓存值仅含模型 artifact、非敏感 usage 和版本 metadata
- RULE-AI-047：价格缺失/过期时显示 token，不显示伪精确金额
"""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional

from .constants import PlanKind

#: 默认硬预算（DES-AI-008）：max input / max output / cache TTL（real seconds）
TOKEN_BUDGETS: dict[PlanKind, tuple[int, int, Optional[float]]] = {
    PlanKind.IMMEDIATE_ACTION: (3000, 700, 300.0),  # 5 RealTime min
    PlanKind.HOURLY_INTENT: (4500, 1000, 600.0),  # 10 RealTime min
    PlanKind.DAILY_PLAN: (7000, 1600, None),  # 当前 game day（由调用方判）
    PlanKind.COMBAT_TURN: (2500, 600, 0.0),  # 当前 turn only（不缓存）
}

#: 内存 LRU 上限（DOC-AI-008 §9）
CACHE_MAX_ENTRIES = 256
CACHE_MAX_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True)
class CacheKeyComponents:
    """缓存键成分（DES-AI-008）：任一变化均 cache miss（TEST-AI-030）"""

    profile_id: str
    model: str
    prompt_id: str
    template_sha256: str
    artifact_schema_id: str
    context_hash: str
    action_catalog_digest: str
    thinking_enabled: bool
    reasoning_effort: Optional[str]
    max_output_tokens: int
    access_policy_version: int


def compute_cache_key(components: CacheKeyComponents) -> str:
    """sha256 缓存键（RULE-AI-045）"""
    canonical = json.dumps(
        {
            "profile_id": components.profile_id,
            "model": components.model,
            "prompt_id": components.prompt_id,
            "template_sha256": components.template_sha256,
            "artifact_schema_id": components.artifact_schema_id,
            "context_hash": components.context_hash,
            "action_catalog_digest": components.action_catalog_digest,
            "thinking_enabled": components.thinking_enabled,
            "reasoning_effort": components.reasoning_effort,
            "max_output_tokens": components.max_output_tokens,
            "access_policy_version": components.access_policy_version,
        },
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class UsageRecord:
    """Usage 记账（DES-AI-008）"""

    request_id: str
    profile_id: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    usage_source: str  # "provider_reported" | "estimated"
    price_profile_id: Optional[str]
    estimated_cost_minor_unit: Optional[int]


def build_usage_record(
    request_id: str,
    profile_id: str,
    input_tokens: Optional[int],
    output_tokens: Optional[int],
    estimated_input: int,
    estimated_output: int,
    price_per_input_token: Optional[float] = None,
    price_per_output_token: Optional[float] = None,
    price_profile_id: Optional[str] = None,
) -> UsageRecord:
    """
    provider 不返回 usage 时 usage_source=estimated（DOC-AI-008 §7）

    价格缺失时不显示伪精确金额（RULE-AI-047）。
    """
    if input_tokens is not None and output_tokens is not None:
        usage_source = "provider_reported"
        final_input, final_output = input_tokens, output_tokens
    else:
        usage_source = "estimated"
        final_input, final_output = estimated_input, estimated_output

    estimated_cost: Optional[int] = None
    if price_per_input_token is not None and price_per_output_token is not None and price_profile_id:
        cost = final_input * price_per_input_token + final_output * price_per_output_token
        estimated_cost = int(round(cost))

    return UsageRecord(
        request_id=request_id,
        profile_id=profile_id,
        input_tokens=final_input,
        output_tokens=final_output,
        cache_read_tokens=0,
        usage_source=usage_source,
        price_profile_id=price_profile_id if estimated_cost is not None else None,
        estimated_cost_minor_unit=estimated_cost,
    )


@dataclass
class CachedArtifact:
    """缓存值：仅模型 artifact、非敏感 usage 和版本 metadata（RULE-AI-046）"""

    artifact_bytes: bytes
    input_tokens: int
    output_tokens: int
    stored_at_monotonic_s: float
    ttl_seconds: Optional[float]

    def is_expired(self, now_monotonic_s: float) -> bool:
        if self.ttl_seconds is None:
            return False  # 如 daily plan 由调用方按 game day 判定
        return now_monotonic_s - self.stored_at_monotonic_s > self.ttl_seconds


class ArtifactCache:
    """内存 LRU 缓存（DOC-AI-008 §9）"""

    def __init__(self, max_entries: int = CACHE_MAX_ENTRIES):
        self._max_entries = max_entries
        self._entries: OrderedDict[str, CachedArtifact] = OrderedDict()

    def get(self, cache_key: str, now_monotonic_s: float) -> Optional[CachedArtifact]:
        entry = self._entries.get(cache_key)
        if entry is None:
            return None
        if entry.is_expired(now_monotonic_s):
            del self._entries[cache_key]
            return None
        self._entries.move_to_end(cache_key)
        return entry

    def put(self, cache_key: str, artifact: CachedArtifact) -> None:
        if artifact.ttl_seconds == 0.0:
            return  # combat turn 不跨 turn 缓存
        self._entries[cache_key] = artifact
        self._entries.move_to_end(cache_key)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def invalidate(self, cache_key: str) -> None:
        """cache 损坏/Schema hash mismatch 视 miss 并删除（DOC-AI-008 §8）"""
        self._entries.pop(cache_key, None)

    def __len__(self) -> int:
        return len(self._entries)


def estimate_tokens(text: str) -> int:
    """tokenizer 不可用时保守字符估计并预留 20%（DOC-AI-008 §8）"""
    base = max(1, len(text) // 3)
    return int(base * 1.2)
