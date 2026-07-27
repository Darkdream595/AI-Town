"""
谣言传播机制

符合 DOC-MEMORY-008：
- 每 hop confidence 公式（speaker trust factor + distortion penalty）
- 失真选择确定性 selector（不用模型随机）
- RULE-MEMORY-060：chain 每 hop 连续，hop index 从 0 连续递增
- RULE-MEMORY-061：recipient 已在 chain、chain>8 或 fingerprint 已接收时停止
- RULE-MEMORY-062：confidence 每 hop 单调不增
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

RUMOR_DISTORTION_VERSION = "rumor-distortion/v1"

MAX_CHAIN_HOPS = 8
DISTORTION_PENALTY_PER_OPERATION = 80

#: 允许的失真操作
DISTORTION_OPERATIONS: tuple[str, ...] = (
    "omit_qualifier",
    "generalize_quantity",
    "shift_time_bucket",
    "change_certainty",
)


def clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(upper, value))


def compute_next_confidence_q1000(
    previous_confidence_q1000: int,
    speaker_to_recipient_trust: int,
    new_distortion_operation_count: int,
) -> int:
    """
    每 hop confidence（DES-MEMORY-008）

    speaker_factor = clamp((trust + 100) * 5, 0, 1000)
    base_after_trust = floor(previous * factor / 1000)
    next = clamp(base - 80 * distortion_ops, 0, previous)
    """
    speaker_factor = clamp((speaker_to_recipient_trust + 100) * 5, 0, 1000)
    base_after_trust = (previous_confidence_q1000 * speaker_factor) // 1000
    distortion_penalty = DISTORTION_PENALTY_PER_OPERATION * new_distortion_operation_count
    return clamp(base_after_trust - distortion_penalty, 0, previous_confidence_q1000)


def select_distortion_operation(
    origin_claim_hash: str, actor_ids: list[str], eligible_operations: list[str]
) -> str | None:
    """
    确定性失真选择（DES-MEMORY-008）

    selector = first_uint32(SHA256(origin_claim_hash + "\n" + join(actor_ids,",") + "\nrumor-distortion/v1"))
    取 selector mod operation_count；无允许操作时不失真。
    """
    if not eligible_operations:
        return None
    for operation in eligible_operations:
        if operation not in DISTORTION_OPERATIONS:
            raise ValueError(f"未知失真操作: {operation}")
    digest = hashlib.sha256(
        (origin_claim_hash + "\n" + ",".join(actor_ids) + "\n" + RUMOR_DISTORTION_VERSION).encode("utf-8")
    ).digest()
    selector = int.from_bytes(digest[:4], "big")
    return eligible_operations[selector % len(eligible_operations)]


@dataclass(frozen=True)
class ChainHop:
    """传播链单 hop"""

    hop_index: int
    speaker_id: str
    recipient_id: str
    source_event_id: str
    claim_hash_after_hop: str
    confidence_after_hop_q1000: int


@dataclass
class RumorChain:
    """谣言传播链"""

    chain_fingerprint: str
    origin_belief_id: str
    hops: list[ChainHop] = field(default_factory=list)

    def participant_ids(self) -> set[str]:
        participants: set[str] = set()
        for hop in self.hops:
            participants.add(hop.speaker_id)
            participants.add(hop.recipient_id)
        return participants


class ChainValidationError(Exception):
    """chain 不连续/超长/循环"""


def validate_and_append_hop(
    chain: RumorChain,
    speaker_id: str,
    recipient_id: str,
    source_event_id: str,
    claim_hash_after_hop: str,
    confidence_after_hop_q1000: int,
) -> ChainHop | None:
    """
    追加 hop；返回 None 表示停止传播（RULE-MEMORY-061）

    - chain>8 停止
    - recipient 已在 chain 停止
    - 每 hop 连续：前一 recipient 必须等于后一 speaker
    - hop index 从 0 连续递增
    - confidence 单调不增
    """
    if len(chain.hops) >= MAX_CHAIN_HOPS:
        return None
    if recipient_id in chain.participant_ids():
        return None

    expected_index = len(chain.hops)
    if chain.hops:
        last_hop = chain.hops[-1]
        if last_hop.recipient_id != speaker_id:
            raise ChainValidationError(
                f"chain 不连续: 前一 recipient {last_hop.recipient_id} != speaker {speaker_id}"
            )
        if confidence_after_hop_q1000 > last_hop.confidence_after_hop_q1000:
            raise ChainValidationError("confidence 每 hop 必须单调不增")

    hop = ChainHop(
        hop_index=expected_index,
        speaker_id=speaker_id,
        recipient_id=recipient_id,
        source_event_id=source_event_id,
        claim_hash_after_hop=claim_hash_after_hop,
        confidence_after_hop_q1000=confidence_after_hop_q1000,
    )
    chain.hops.append(hop)
    return hop
