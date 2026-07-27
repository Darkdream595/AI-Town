"""
状态效果与叠加规则（DOC-COMBAT-005）

- RULE-COMBAT-026：实例只在解析事务内施加，引用注册 definition 与 source_event
- RULE-COMBAT-027：definition 必须声明全部字段；control 类必须声明禁止集合
- RULE-COMBAT-028：四种叠加策略各有唯一结果
- RULE-COMBAT-029：tick 在宿主 actor_turn 开始时按 ULID 升序结算
- RULE-COMBAT-030：属性修正是派生投影，实例移除即还原
- RULE-COMBAT-031：终结统一清理并按 Persist Mapping 转换
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..foundation import generate_ulid
from .constants import (
    STATUS_INSTANCE_CAP,
    ActionKind,
    StatusCategory,
    StackingPolicy,
)


class StatusError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True)
class StatusDefinition:
    """DES-COMBAT-005 的注册模板（构建期数据）"""

    definition_id: str
    category: StatusCategory
    attribute_deltas: Dict[str, int]
    per_tick_formula_ref: Optional[str]
    duration_turns: int
    stacking_policy: StackingPolicy
    max_stacks: int
    forbidden_action_kinds: Tuple[ActionKind, ...]
    persist_mapping: Optional[str]  # injury.* / illness.* / None

    def validate(self) -> None:
        if not (1 <= self.duration_turns <= 20):
            raise StatusError("COMBAT_STATUS_DEFINITION_INVALID", "duration_turns 1..20")
        if not (1 <= self.max_stacks <= 5):
            raise StatusError("COMBAT_STATUS_DEFINITION_INVALID", "max_stacks 1..5")
        if self.category is StatusCategory.CONTROL and not self.forbidden_action_kinds:
            raise StatusError("COMBAT_STATUS_DEFINITION_INVALID", "control needs forbidden kinds")
        for name in self.attribute_deltas:
            if name not in ("strength", "defense", "magic", "resistance", "agility", "focus"):
                raise StatusError("COMBAT_STATUS_DEFINITION_INVALID", f"attr {name}")


@dataclass
class StatusInstance:
    """DES-COMBAT-005：Encounter 内单个 Combatant 上的效果实例"""

    status_instance_id: str
    encounter_id: str
    definition_id: str
    holder_combatant_id: str
    source_event_id: str
    stack_count: int
    remaining_turns: int
    applied_at_turn_index: int
    status_schema_version: int = 1


class StatusRegistry:
    """构建期不可变 Catalog；未注册 definition fail closed"""

    def __init__(self) -> None:
        self._definitions: Dict[str, StatusDefinition] = {}

    def register(self, definition: StatusDefinition) -> None:
        definition.validate()
        if definition.definition_id in self._definitions:
            raise StatusError("COMBAT_STATUS_DEFINITION_INVALID", f"duplicate {definition.definition_id}")
        self._definitions[definition.definition_id] = definition

    def get(self, definition_id: str) -> StatusDefinition:
        definition = self._definitions.get(definition_id)
        if definition is None:
            raise StatusError("COMBAT_STATUS_DEFINITION_INVALID", definition_id)
        return definition

    def __len__(self) -> int:
        return len(self._definitions)


def build_default_statuses() -> StatusRegistry:
    """首版注册表：覆盖四种叠加策略与五类 category"""
    registry = StatusRegistry()
    registry.register(StatusDefinition(
        definition_id="status.burning",
        category=StatusCategory.DAMAGE_OVER_TIME,
        attribute_deltas={},
        per_tick_formula_ref="combat_formula.v1.dot_burning",
        duration_turns=3,
        stacking_policy=StackingPolicy.STACK_INTENSITY,
        max_stacks=3,
        forbidden_action_kinds=(),
        persist_mapping="injury.burn_wound",
    ))
    registry.register(StatusDefinition(
        definition_id="status.regeneration",
        category=StatusCategory.HEAL_OVER_TIME,
        attribute_deltas={},
        per_tick_formula_ref="combat_formula.v1.hot_regeneration",
        duration_turns=4,
        stacking_policy=StackingPolicy.REFRESH_DURATION,
        max_stacks=1,
        forbidden_action_kinds=(),
        persist_mapping=None,
    ))
    registry.register(StatusDefinition(
        definition_id="status.weakened",
        category=StatusCategory.DEBUFF,
        attribute_deltas={"strength": -10},
        per_tick_formula_ref=None,
        duration_turns=3,
        stacking_policy=StackingPolicy.REJECT_DUPLICATE,
        max_stacks=1,
        forbidden_action_kinds=(),
        persist_mapping=None,
    ))
    registry.register(StatusDefinition(
        definition_id="status.guarded",
        category=StatusCategory.BUFF,
        attribute_deltas={"defense": 8},
        per_tick_formula_ref=None,
        duration_turns=2,
        stacking_policy=StackingPolicy.INDEPENDENT_INSTANCES,
        max_stacks=2,
        forbidden_action_kinds=(),
        persist_mapping=None,
    ))
    registry.register(StatusDefinition(
        definition_id="status.stunned",
        category=StatusCategory.CONTROL,
        attribute_deltas={},
        per_tick_formula_ref=None,
        duration_turns=1,
        stacking_policy=StackingPolicy.REFRESH_DURATION,
        max_stacks=1,
        forbidden_action_kinds=(
            ActionKind.ATTACK, ActionKind.SKILL, ActionKind.CAST_SPELL,
            ActionKind.USE_ITEM, ActionKind.FLEE, ActionKind.SWITCH_POSITION,
        ),
        persist_mapping=None,
    ))
    return registry


class StatusStore:
    """Encounter 内实例聚合：施加、叠加、tick、到期、终结清理"""

    def __init__(self, registry: StatusRegistry, id_factory=generate_ulid) -> None:
        self._registry = registry
        self._id_factory = id_factory
        self._instances: Dict[str, StatusInstance] = {}

    def instances_of(self, holder_combatant_id: str) -> List[StatusInstance]:
        return sorted(
            (i for i in self._instances.values() if i.holder_combatant_id == holder_combatant_id),
            key=lambda i: i.status_instance_id,  # RULE-COMBAT-029：ULID 升序
        )

    def all_instances(self) -> List[StatusInstance]:
        return list(self._instances.values())

    def apply(
        self,
        encounter_id: str,
        definition_id: str,
        holder_combatant_id: str,
        source_event_id: str,
        turn_index: int,
    ) -> Tuple[StatusInstance, str]:
        """RULE-COMBAT-028：返回 (实例, applied_kind)；applied_kind 供事件记录"""
        definition = self._registry.get(definition_id)
        existing = [
            i for i in self.instances_of(holder_combatant_id)
            if i.definition_id == definition_id
        ]
        if len(self.instances_of(holder_combatant_id)) >= STATUS_INSTANCE_CAP and not existing:
            raise StatusError("combat_status_instance_cap", holder_combatant_id)
        policy = definition.stacking_policy
        if policy is StackingPolicy.REJECT_DUPLICATE and existing:
            raise StatusError("combat_status_rejected", definition_id)
        if policy is StackingPolicy.REFRESH_DURATION and existing:
            instance = existing[0]
            instance.remaining_turns = definition.duration_turns
            return instance, "refreshed"
        if policy is StackingPolicy.STACK_INTENSITY and existing:
            instance = existing[0]
            if instance.stack_count >= definition.max_stacks:
                # 满层拒绝加层但刷新剩余回合（注册表固定语义）
                instance.remaining_turns = definition.duration_turns
                return instance, "refreshed"
            instance.stack_count += 1
            instance.remaining_turns = definition.duration_turns
            return instance, "stacked"
        if policy is StackingPolicy.INDEPENDENT_INSTANCES and existing and len(existing) >= definition.max_stacks:
            raise StatusError("combat_status_rejected", f"{definition_id} at max instances")
        instance = StatusInstance(
            status_instance_id=self._id_factory(),
            encounter_id=encounter_id,
            definition_id=definition_id,
            holder_combatant_id=holder_combatant_id,
            source_event_id=source_event_id,
            stack_count=1,
            remaining_turns=definition.duration_turns,
            applied_at_turn_index=turn_index,
        )
        self._instances[instance.status_instance_id] = instance
        return instance, "created"

    def attribute_delta_for(self, holder_combatant_id: str, attribute: str) -> int:
        """RULE-COMBAT-030：全部活跃实例 deltas 之和（含层数）"""
        total = 0
        for instance in self.instances_of(holder_combatant_id):
            definition = self._registry.get(instance.definition_id)
            total += definition.attribute_deltas.get(attribute, 0) * instance.stack_count
        return total

    def forbidden_kinds_for(self, holder_combatant_id: str) -> frozenset:
        forbidden = set()
        for instance in self.instances_of(holder_combatant_id):
            definition = self._registry.get(instance.definition_id)
            forbidden.update(definition.forbidden_action_kinds)
        return frozenset(forbidden)

    def tick(self, holder_combatant_id: str) -> Tuple[List[Dict], List[str]]:
        """RULE-COMBAT-029：返回 (tick 结果, 过期移除的 instance_id)

        tick 后 remaining_turns - 1，减到 0 同一事务移除（StatusExpired）。
        """
        results: List[Dict] = []
        expired: List[str] = []
        for instance in self.instances_of(holder_combatant_id):
            definition = self._registry.get(instance.definition_id)
            delta = 0
            if definition.per_tick_formula_ref == "combat_formula.v1.dot_burning":
                delta = -(2 * instance.stack_count)
            elif definition.per_tick_formula_ref == "combat_formula.v1.hot_regeneration":
                delta = 3 * instance.stack_count
            results.append({
                "status_instance_id": instance.status_instance_id,
                "definition_id": instance.definition_id,
                "hp_delta": delta,
                "stack_count": instance.stack_count,
            })
            instance.remaining_turns -= 1
            if instance.remaining_turns <= 0:
                expired.append(instance.status_instance_id)
        for instance_id in expired:
            del self._instances[instance_id]
        return results, expired

    def remove_by_category(self, holder_combatant_id: str, category: StatusCategory, count: int) -> List[str]:
        """净化类行动：按 category 匹配、ULID 升序移除注册数量"""
        removed = []
        for instance in self.instances_of(holder_combatant_id):
            if len(removed) >= count:
                break
            if self._registry.get(instance.definition_id).category is category:
                removed.append(instance.status_instance_id)
        for instance_id in removed:
            del self._instances[instance_id]
        return removed

    def persist_mappings_for(self, holder_combatant_id: str) -> List[str]:
        """RULE-COMBAT-031：终结时收集非 null persist mapping"""
        mappings = []
        for instance in self.instances_of(holder_combatant_id):
            mapping = self._registry.get(instance.definition_id).persist_mapping
            if mapping is not None:
                mappings.append(mapping)
        return mappings

    def clear_encounter(self) -> None:
        """RULE-COMBAT-031：Encounter 终结时所有实例结束，无 Overworld 残留"""
        self._instances.clear()
