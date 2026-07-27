"""
Action Catalog 与 Domain 所有权映射

符合 DOC-AI-005：19 行 Catalog 与 DOC-AI-004 discriminator 集合完全一致。
- RULE-AI-026：每项 action 只有一个 Parameters Ref
- RULE-AI-027：AI semantic validation 只验证形状、可见引用与跨字段
- §4.1 跨字段语义表
"""

from __future__ import annotations

from dataclasses import dataclass

from .constants import ActionId
from .schema import DecodedProposal


@dataclass(frozen=True)
class CatalogEntry:
    """Catalog 单行（DES-AI-005）"""

    action_id: str
    parameters_ref: str  # schema.ai.action_proposal.v1#/$defs/<action>_parameters
    owner_domain: str  # canonical owner
    committed_event: str  # 典型 committed event 语义名
    requires_target: bool
    requires_destination: bool
    requires_target_null: bool  # work/eat/wait 顶层 target 必须为 null
    requires_destination_null: bool  # work/eat/wait 顶层 destination 必须为 null


ACTION_CATALOG: dict[str, CatalogEntry] = {
    entry.action_id: entry
    for entry in [
        CatalogEntry(
            action_id="move_to",
            parameters_ref="move_to_parameters",
            owner_domain="MAP",
            committed_event="ActorMovementStarted",
            requires_target=False,
            requires_destination=False,  # 按 destination_kind 由跨字段规则判定
            requires_target_null=False,
            requires_destination_null=False,
        ),
        CatalogEntry(
            action_id="talk",
            parameters_ref="talk_parameters",
            owner_domain="DIALOGUE",
            committed_event="ConversationStarted",
            requires_target=True,
            requires_destination=False,
            requires_target_null=False,
            requires_destination_null=False,
        ),
        CatalogEntry(
            action_id="work",
            parameters_ref="work_parameters",
            owner_domain="ECON",
            committed_event="WorkSessionStarted",
            requires_target=False,
            requires_destination=False,
            requires_target_null=True,
            requires_destination_null=True,
        ),
        CatalogEntry(
            action_id="rest",
            parameters_ref="rest_parameters",
            owner_domain="RESIDENT",
            committed_event="RestStarted",
            requires_target=False,
            requires_destination=True,
            requires_target_null=False,
            requires_destination_null=False,
        ),
        CatalogEntry(
            action_id="eat",
            parameters_ref="eat_parameters",
            owner_domain="ECON",
            committed_event="ItemConsumed",
            requires_target=False,
            requires_destination=False,
            requires_target_null=True,
            requires_destination_null=True,
        ),
        CatalogEntry(
            action_id="buy",
            parameters_ref="buy_parameters",
            owner_domain="ECON",
            committed_event="TransactionCommitted",
            requires_target=True,
            requires_destination=True,
            requires_target_null=False,
            requires_destination_null=False,
        ),
        CatalogEntry(
            action_id="sell",
            parameters_ref="sell_parameters",
            owner_domain="ECON",
            committed_event="TransactionCommitted",
            requires_target=True,
            requires_destination=True,
            requires_target_null=False,
            requires_destination_null=False,
        ),
        CatalogEntry(
            action_id="give_item",
            parameters_ref="give_item_parameters",
            owner_domain="ECON",
            committed_event="ItemTransferred",
            requires_target=True,
            requires_destination=False,
            requires_target_null=False,
            requires_destination_null=False,
        ),
        CatalogEntry(
            action_id="use_object",
            parameters_ref="use_object_parameters",
            owner_domain="WORLD",
            committed_event="ObjectUsed",
            requires_target=True,
            requires_destination=False,
            requires_target_null=False,
            requires_destination_null=False,
        ),
        CatalogEntry(
            action_id="craft",
            parameters_ref="craft_parameters",
            owner_domain="ECON",
            committed_event="CraftOrderStarted",
            requires_target=False,
            requires_destination=True,
            requires_target_null=False,
            requires_destination_null=False,
        ),
        CatalogEntry(
            action_id="gather",
            parameters_ref="gather_parameters",
            owner_domain="EVENT",
            committed_event="GatherActionStarted",
            requires_target=True,
            requires_destination=False,
            requires_target_null=False,
            requires_destination_null=False,
        ),
        CatalogEntry(
            action_id="explore",
            parameters_ref="explore_parameters",
            owner_domain="MAP",
            committed_event="ExplorationStarted",
            requires_target=False,
            requires_destination=True,
            requires_target_null=False,
            requires_destination_null=False,
        ),
        CatalogEntry(
            action_id="cast_spell",
            parameters_ref="cast_spell_parameters",
            owner_domain="MAGIC",
            committed_event="SpellCastCommitted",
            requires_target=False,  # 由 SpellDefinition 决定
            requires_destination=False,
            requires_target_null=False,
            requires_destination_null=False,
        ),
        CatalogEntry(
            action_id="start_encounter",
            parameters_ref="start_encounter_parameters",
            owner_domain="COMBAT",
            committed_event="EncounterStarted",
            requires_target=True,
            requires_destination=False,
            requires_target_null=False,
            requires_destination_null=False,
        ),
        CatalogEntry(
            action_id="combat_action",
            parameters_ref="combat_action_parameters",
            owner_domain="COMBAT",
            committed_event="CombatActionResolved",
            requires_target=False,  # 按 option 可选
            requires_destination=False,
            requires_target_null=False,
            requires_destination_null=False,
        ),
        CatalogEntry(
            action_id="build",
            parameters_ref="build_parameters",
            owner_domain="EVENT",
            committed_event="ConstructionPlanned",
            requires_target=False,
            requires_destination=True,
            requires_target_null=False,
            requires_destination_null=False,
        ),
        CatalogEntry(
            action_id="repair",
            parameters_ref="repair_parameters",
            owner_domain="EVENT",
            committed_event="RepairStarted",
            requires_target=True,
            requires_destination=False,
            requires_target_null=False,
            requires_destination_null=False,
        ),
        CatalogEntry(
            action_id="wait",
            parameters_ref="wait_parameters",
            owner_domain="TIME",
            committed_event="WaitStarted",
            requires_target=False,
            requires_destination=False,
            requires_target_null=True,
            requires_destination_null=True,
        ),
        CatalogEntry(
            action_id="observe",
            parameters_ref="observe_parameters",
            owner_domain="MAP",
            committed_event="ObservationCompleted",
            requires_target=True,
            requires_destination=False,
            requires_target_null=False,
            requires_destination_null=False,
        ),
    ]
}


@dataclass(frozen=True)
class SemanticViolation:
    """跨字段语义违规（DOC-AI-005 §4.1）"""

    reason_code: str
    detail: str


def validate_cross_field_semantics(proposal: DecodedProposal) -> list[SemanticViolation]:
    """
    跨字段语义表检查（DOC-AI-005 §4.1 / TEST-AI-018）

    只验证形状与引用可见性，不做 Domain 授权（RULE-AI-027）。
    """
    violations: list[SemanticViolation] = []
    entry = ACTION_CATALOG.get(proposal.action)
    if entry is None:
        return [SemanticViolation("unknown_action", f"action {proposal.action!r} 不在 catalog")]

    if entry.requires_target and proposal.target_entity_id is None:
        violations.append(
            SemanticViolation("target_required", f"{proposal.action} 要求 target_entity_id 非 null")
        )
    if entry.requires_destination and proposal.destination_id is None:
        violations.append(
            SemanticViolation("destination_required", f"{proposal.action} 要求 destination_id 非 null")
        )
    if entry.requires_target_null and proposal.target_entity_id is not None:
        violations.append(
            SemanticViolation("target_must_be_null", f"{proposal.action} 要求 target_entity_id 为 null")
        )
    if entry.requires_destination_null and proposal.destination_id is not None:
        violations.append(
            SemanticViolation(
                "destination_must_be_null", f"{proposal.action} 要求 destination_id 为 null"
            )
        )

    # move_to 的 destination_kind 与顶层 destination_id 联动（DOC-AI-004 §4 尾注）
    if proposal.action == ActionId.MOVE_TO.value:
        destination_kind = proposal.parameters.get("destination_kind")
        world_point = proposal.parameters.get("world_point")
        if destination_kind == "semantic_node":
            if proposal.destination_id is None:
                violations.append(
                    SemanticViolation(
                        "destination_required",
                        "semantic_node 模式要求顶层 destination_id 非 null",
                    )
                )
            if world_point is not None:
                violations.append(
                    SemanticViolation(
                        "world_point_must_be_null",
                        "semantic_node 模式要求 world_point 为 null",
                    )
                )
        elif destination_kind == "world_point":
            if proposal.destination_id is not None:
                violations.append(
                    SemanticViolation(
                        "destination_must_be_null", "world_point 模式要求 destination_id 为 null"
                    )
                )
            if world_point is None:
                violations.append(
                    SemanticViolation("world_point_required", "world_point 模式要求参数中存在点")
                )

    return violations


def catalog_action_set() -> frozenset[str]:
    """catalog action 集合（RULE-AI-025 一致性基准）"""
    return frozenset(ACTION_CATALOG.keys())


def catalog_digest() -> str:
    """catalog 内容摘要（Prompt 缓存键用，RULE-AI-017）"""
    import hashlib

    canonical = "|".join(
        f"{e.action_id}:{e.parameters_ref}:{e.owner_domain}:{e.committed_event}"
        for e in sorted(ACTION_CATALOG.values(), key=lambda x: x.action_id)
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
