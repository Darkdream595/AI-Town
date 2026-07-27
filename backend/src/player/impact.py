"""
玩家影响世界的因果与事件边界（DOC-PLAYER-006）

- RULE-PLAYER-026：只能通过 registered PlayerCommand 或受限 MayorCommand
  影响世界；禁止 Direct Mutation
- RULE-PLAYER-027：玩家来源 DomainEvent 必须含 causation_id=command_id、
  稳定 correlation_id、actor ResidentId、Revision 与 GameTime
- RULE-PLAYER-028：数值由各 owner 计算；不接受 Client/文本声明的结果值
- RULE-PLAYER-029：动画/toast/对话承诺不是事实
- RULE-PLAYER-030：撤销使用补偿事件，不得删除/改写/重编号原事件
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..foundation import generate_ulid


class DirectMutationError(Exception):
    """Direct Mutation 拒绝；code 为稳定 reason code"""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


#: §5.2 六维影响路径：维度 → (允许的 command 示例, 禁止的直接结果)
IMPACT_DIMENSIONS: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "social": {
        "commands": ("talk", "give_item", "work"),
        "forbidden_mutations": ("set_affection", "set_relationship", "set_trust"),
    },
    "economic": {
        "commands": ("work", "buy", "sell", "craft"),
        "forbidden_mutations": ("set_balance", "mint_currency", "set_stock"),
    },
    "political": {
        "commands": ("vote", "petition", "mayor_governance"),
        "forbidden_mutations": ("set_office", "declare_authority", "set_law"),
    },
    "spatial": {
        "commands": ("move_to", "use_object", "build", "repair"),
        "forbidden_mutations": ("teleport", "edit_collision", "set_stage"),
    },
    "conflict": {
        "commands": ("start_encounter", "combat_action"),
        "forbidden_mutations": ("set_hit", "force_combat_outcome", "set_health"),
    },
    "narrative": {
        "commands": ("accept_quest", "advance_objective"),
        "forbidden_mutations": ("complete_quest", "set_objective_state"),
    },
}

#: 全部禁止字段的快速查询集
_ALL_FORBIDDEN_MUTATIONS = frozenset(
    m for dim in IMPACT_DIMENSIONS.values() for m in dim["forbidden_mutations"]
)


def assert_not_direct_mutation(field_name: str) -> None:
    """RULE-PLAYER-026/§5.2：任何 direct mutation 字段一律拒绝"""
    if field_name in _ALL_FORBIDDEN_MUTATIONS:
        raise DirectMutationError(
            "PLAYER_DIRECT_MUTATION_REJECTED",
            f"direct mutation {field_name!r} is forbidden; use owner workflow",
        )


@dataclass(frozen=True)
class CausalityEnvelope:
    """
    §5.1 因果 Envelope（RULE-PLAYER-027）。

    type/payload 由 owner Schema 定义；PLAYER 只拥有 actor 解析与初始
    correlation。
    """

    event_id: str
    world_id: str
    revision: int
    type: str
    game_time: int
    causation_id: str  # = command_id
    correlation_id: str
    actor_entity_id: str
    payload: dict
    render: Optional[dict] = None
    protocol_version: int = 1

    def __post_init__(self) -> None:
        if self.protocol_version != 1:
            raise DirectMutationError("IMPACT_PROTOCOL_VERSION_UNSUPPORTED")
        for name in ("event_id", "world_id", "type", "causation_id",
                     "correlation_id", "actor_entity_id"):
            if not getattr(self, name):
                raise DirectMutationError(
                    "IMPACT_ENVELOPE_FIELD_EMPTY", f"{name} must be non-empty"
                )
        if self.revision < 0 or self.game_time < 0:
            raise DirectMutationError("IMPACT_ENVELOPE_VERSION_NEGATIVE")


@dataclass(frozen=True)
class ImpactProjection:
    """
    §3/§9：玩家可见后果摘要。

    只展示玩家有权知道的结果；不得包含隐藏 relationship 数值、私人记忆、
    secret source 或模型 reasoning。
    """

    summary: str
    dimension: str
    correlation_id: str
    revision: int
    public_fields: dict = field(default_factory=dict)

    _FORBIDDEN_PROJECTION_KEYS = frozenset(
        {
            "relationship_raw",
            "hidden_relationship",
            "private_memory",
            "secret_source",
            "model_reasoning",
            "chain_of_thought",
        }
    )

    def __post_init__(self) -> None:
        bad = self._FORBIDDEN_PROJECTION_KEYS & set(self.public_fields)
        if bad:
            raise DirectMutationError(
                "IMPACT_PROJECTION_DISCLOSURE_VIOLATION",
                f"projection leaks private fields: {sorted(bad)}",
            )


class ImpactTracker:
    """
    命令 → 事件 → 投影的因果链追踪。

    RULE-PLAYER-028：wrap_event 不接受调用方传入的结算数值覆盖 owner 计算；
    本类只附加因果元数据，payload 原样来自 owner。
    """

    def __init__(self, world_id: str) -> None:
        self._world_id = world_id
        self._events: List[CausalityEnvelope] = []
        self._correlations: Dict[str, List[str]] = {}

    def new_correlation_id(self) -> str:
        """§3：一次玩家意图跨多个 Domain 的稳定关联 ID"""
        return generate_ulid()

    def wrap_event(
        self,
        command_id: str,
        correlation_id: str,
        actor_entity_id: str,
        event_type: str,
        payload: dict,
        revision: int,
        game_time: int,
        render: Optional[dict] = None,
    ) -> CausalityEnvelope:
        """RULE-PLAYER-027：为 owner 事件附加强制因果元数据"""
        envelope = CausalityEnvelope(
            event_id=generate_ulid(),
            world_id=self._world_id,
            revision=revision,
            type=event_type,
            game_time=game_time,
            causation_id=command_id,
            correlation_id=correlation_id,
            actor_entity_id=actor_entity_id,
            payload=payload,
            render=render,
        )
        self._events.append(envelope)
        self._correlations.setdefault(correlation_id, []).append(envelope.event_id)
        return envelope

    def build_compensation(
        self,
        original_event_id: str,
        compensating_command_id: str,
        event_type: str,
        payload: dict,
        revision: int,
        game_time: int,
        actor_entity_id: str,
        correlation_id: Optional[str] = None,
    ) -> CausalityEnvelope:
        """
        RULE-PLAYER-030：补偿产生反向新事件，原历史不被删除/改写/重编号。
        """
        original = self.get_event(original_event_id)
        if original is None:
            raise DirectMutationError(
                "IMPACT_COMPENSATION_TARGET_MISSING",
                f"unknown original event {original_event_id}",
            )
        compensation_payload = dict(payload)
        compensation_payload["compensates_event_id"] = original_event_id
        return self.wrap_event(
            command_id=compensating_command_id,
            correlation_id=correlation_id or original.correlation_id,
            actor_entity_id=actor_entity_id,
            event_type=event_type,
            payload=compensation_payload,
            revision=revision,
            game_time=game_time,
        )

    def get_event(self, event_id: str) -> Optional[CausalityEnvelope]:
        for event in self._events:
            if event.event_id == event_id:
                return event
        return None

    def events_by_correlation(self, correlation_id: str) -> List[CausalityEnvelope]:
        ids = self._correlations.get(correlation_id, [])
        return [e for e in self._events if e.event_id in ids]

    def events_by_command(self, command_id: str) -> List[CausalityEnvelope]:
        return [e for e in self._events if e.causation_id == command_id]

    def verify_chain(self, command_id: str) -> bool:
        """
        验收：命令产生的每个事件都满足 RULE-PLAYER-027 必填因果字段。
        """
        for event in self.events_by_command(command_id):
            if not (
                event.causation_id
                and event.correlation_id
                and event.actor_entity_id
                and event.revision >= 0
                and event.game_time >= 0
            ):
                return False
        return True

    @staticmethod
    def assert_fact_requires_committed_event(source: str) -> None:
        """
        RULE-PLAYER-029：动画、toast、对话承诺文本和预测不是事实来源。
        """
        if source in ("animation", "toast", "dialogue_promise", "prediction"):
            raise DirectMutationError(
                "IMPACT_NON_FACT_SOURCE",
                f"{source} is not a committed DomainEvent and cannot drive projections",
            )
