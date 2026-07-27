"""
战利品、装备损耗与社会后果（DOC-COMBAT-010）

- RULE-COMBAT-055：来源封闭——died/dissipated Creature 的注册 Loot Table
  与谈判条款让渡；Resident Inventory 永不自动掠夺
- RULE-COMBAT-056：Loot Roll 在结果事务内按 combatant_id 升序、条目注册序
  消费 combat.loot 流；combat_loot provenance；货币走 mint
- RULE-COMBAT-057：Victor Assignment 确定性轮转；溢出/无存活/平手落地点容器
- RULE-COMBAT-058：Wear 无掷骰逐回合记账，结果事务一次性聚合提交；
  归零转 Damaged，永不删除；单件单场 500 q1000 截断并记录诊断
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Protocol, Tuple

from .constants import (
    DURABILITY_FULL_Q1000,
    LOOT_DRAW_CAP,
    Side,
    WEAR_ARMOR_PER_HIT_Q1000,
    WEAR_CAP_PER_ITEM_PER_BATTLE_Q1000,
    WEAR_WEAPON_PER_USE_Q1000,
)
from .rng import DeterministicRandomStream

LOOT_SCHEMA_VERSION = 1

#: 货币条目定义 ID：掉落走 mint 事件而非物品实例（RULE-FOUNDATION-019）
CURRENCY_ITEM_DEFINITION_ID = "item.currency.copper_feather"


class LootError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


class CombatEconPort(Protocol):
    """结果事务对 ECON 的写入契约（适配器接 DOC-ECON-004/005/006）

    所有方法以 idempotency_key 保证跨域重放至多生效一次；
    任何抛错使整个结果事务回滚（不允许先掉落后补账）。
    """

    def mint_loot_item(
        self, *, item_definition_id: str, quantity: int, idempotency_key: str, provenance: Mapping
    ) -> str:
        """创建掉落物品实例，返回 item_instance_id"""
        ...

    def mint_currency(
        self, *, amount_copper_feather: int, idempotency_key: str, provenance: Mapping
    ) -> str:
        """货币掉落 mint，返回账本事件引用"""
        ...

    def transfer_yield_item(
        self, *, item_instance_id: str, idempotency_key: str, provenance: Mapping
    ) -> None:
        """谈判让渡：已存在物品的所有权转移（不凭空创建）"""
        ...

    def deposit_to_inventory(self, *, item_ref: str, inventory_id: str) -> bool:
        """存入指定 Inventory；容量不足返回 False（调用方转地点容器）"""
        ...

    def apply_wear(self, *, item_instance_id: str, wear_delta_q1000: int, idempotency_key: str) -> bool:
        """聚合耐久 delta 一次性提交；返回 became_damaged"""
        ...

    def consume_item(self, *, item_instance_id: str, idempotency_key: str) -> None:
        """use_item 消耗品在 Turn 解析事务内按 ECON 规则落账（不属于 Wear）"""
        ...


# ---------------------------------------------------------------------------
# Loot Table 注册表（构建期校验，运行时 fail closed）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LootEntry:
    item_definition_id: str
    drop_permille: int
    quantity_min: int
    quantity_max: int


class LootTableRegistry:
    """Stable Catalog ID `loot_table.*` 注册的掉落模板"""

    def __init__(self) -> None:
        self._tables: Dict[str, Tuple[LootEntry, ...]] = {}

    def register(self, loot_table_id: str, entries: List[LootEntry]) -> None:
        if not loot_table_id or not loot_table_id.startswith("loot_table."):
            raise LootError("COMBAT_LOOT_TABLE_INVALID", f"bad id {loot_table_id!r}")
        if loot_table_id in self._tables:
            raise LootError("COMBAT_LOOT_TABLE_INVALID", f"duplicate {loot_table_id}")
        if not entries:
            raise LootError("COMBAT_LOOT_TABLE_INVALID", "empty entries")
        for entry in entries:
            if not (1 <= entry.drop_permille <= 1000):
                raise LootError("COMBAT_LOOT_TABLE_INVALID", f"permille {entry.drop_permille}")
            if entry.quantity_min < 1 or entry.quantity_max < entry.quantity_min:
                raise LootError(
                    "COMBAT_LOOT_TABLE_INVALID",
                    f"quantity {entry.quantity_min}..{entry.quantity_max}",
                )
        self._tables[loot_table_id] = tuple(entries)

    def table_for(self, loot_table_id: str) -> Tuple[LootEntry, ...]:
        table = self._tables.get(loot_table_id)
        if table is None:
            # 未注册表 fail closed；结果事务整体回滚
            raise LootError("COMBAT_LOOT_TABLE_INVALID", f"unregistered {loot_table_id}")
        return table

    def registered_ids(self) -> List[str]:
        return sorted(self._tables)


# ---------------------------------------------------------------------------
# 结果记录
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LootDrop:
    """单条掉落：creature_loot 为新建；negotiation_yield 为转移"""

    loot_table_id: Optional[str]
    item_definition_id: str
    quantity: int
    item_ref: str  # mint/transfer 后的实例或账本事件引用
    source_kind: str  # creature_loot / negotiation_yield
    source_combatant_id: Optional[str]
    is_currency: bool
    draw_count: int  # 本条目消耗的 stream draw 数（quantity 单值时记 1，仅 drop draw）
    assigned_inventory_id: Optional[str] = None


@dataclass(frozen=True)
class WearSettlement:
    item_instance_id: str
    wear_delta_q1000: int
    became_damaged: bool


@dataclass
class LootOutcome:
    """DES-COMBAT-010：schema.combat.loot_outcome.v1"""

    encounter_id: str
    source_event_id: str
    drops: List[LootDrop] = field(default_factory=list)
    wear_settlements: List[WearSettlement] = field(default_factory=list)
    loot_schema_version: int = LOOT_SCHEMA_VERSION

    def to_record(self) -> Dict:
        return {
            "loot_schema_version": self.loot_schema_version,
            "encounter_id": self.encounter_id,
            "source_event_id": self.source_event_id,
            "drops": [
                {
                    "loot_table_id": d.loot_table_id,
                    "item_definition_id": d.item_definition_id,
                    "quantity": d.quantity,
                    "assigned_inventory_id": d.assigned_inventory_id,
                }
                for d in self.drops
            ],
            "wear_settlements": [
                {
                    "item_instance_id": w.item_instance_id,
                    "wear_delta_q1000": w.wear_delta_q1000,
                    "became_damaged": w.became_damaged,
                }
                for w in self.wear_settlements
            ],
        }


@dataclass(frozen=True)
class NegotiationYield:
    """RULE-COMBAT-055 第二来源：注册谈判条款明确让渡的物品/货币

    物品为对方 Inventory 中已存在实例的转移；货币为整数铜羽 mint。
    条款判定失败时由谈判流程回退为无让渡，不进入本结构。
    """

    item_definition_id: str
    quantity: int
    item_instance_id: Optional[str] = None  # 让渡物品的已存在实例
    is_currency: bool = False


# ---------------------------------------------------------------------------
# Wear 记账（Encounter aggregate 内的逐回合账本）
# ---------------------------------------------------------------------------


class WearLedger:
    """RULE-COMBAT-058：逐 Turn 只记账；结果事务一次性聚合提交"""

    def __init__(self) -> None:
        self._deltas: Dict[str, int] = {}
        self.diagnostics: List[str] = []

    def _add(self, item_instance_id: str, amount: int) -> None:
        current = self._deltas.get(item_instance_id, 0)
        updated = current + amount
        if updated > WEAR_CAP_PER_ITEM_PER_BATTLE_Q1000:
            updated = WEAR_CAP_PER_ITEM_PER_BATTLE_Q1000
            self.diagnostics.append(f"wear_cap_truncated:{item_instance_id}")
        self._deltas[item_instance_id] = updated

    def record_weapon_use(self, item_instance_id: str) -> None:
        """武器每次 attack/skill 使用累计 5 q1000"""
        self._add(item_instance_id, WEAR_WEAPON_PER_USE_Q1000)

    def record_armor_hit(self, item_instance_id: str) -> None:
        """护甲每次被命中累计 3 q1000"""
        self._add(item_instance_id, WEAR_ARMOR_PER_HIT_Q1000)

    def deltas(self) -> Dict[str, int]:
        return dict(self._deltas)

    def settle(self, *, encounter_id: str, econ_port: CombatEconPort) -> List[WearSettlement]:
        """结果事务内按 item_instance_id 升序一次性提交；ECON 失败整体回滚"""
        settlements: List[WearSettlement] = []
        for item_instance_id in sorted(self._deltas):
            became_damaged = econ_port.apply_wear(
                item_instance_id=item_instance_id,
                wear_delta_q1000=self._deltas[item_instance_id],
                idempotency_key=f"{encounter_id}:wear:{item_instance_id}",
            )
            settlements.append(
                WearSettlement(
                    item_instance_id=item_instance_id,
                    wear_delta_q1000=self._deltas[item_instance_id],
                    became_damaged=became_damaged,
                )
            )
        return settlements


# ---------------------------------------------------------------------------
# Loot Roll + Victor Assignment（仅结果事务内调用一次）
# ---------------------------------------------------------------------------


def roll_loot(
    *,
    encounter_id: str,
    source_event_id: str,
    loot_sources: List[Tuple[str, Optional[str]]],
    negotiation_yields: List[NegotiationYield],
    registry: LootTableRegistry,
    loot_stream: DeterministicRandomStream,
    winning_side: Optional[Side],
    surviving_members: List[Tuple[str, str]],
    location_container_inventory_id: str,
    econ_port: CombatEconPort,
) -> LootOutcome:
    """RULE-COMBAT-056/057：确定性抽取与分配

    loot_sources: (combatant_id, loot_table_id)，仅终态 died/dissipated 的 Creature；
    surviving_members: (combatant_id, inventory_id)，winning_side=party 的存活成员；
    货币条目（item.currency.copper_feather）走 mint，其余创建物品实例。
    """
    outcome = LootOutcome(encounter_id=encounter_id, source_event_id=source_event_id)
    provenance = {
        "kind": "combat_loot",
        "encounter_id": encounter_id,
        "source_event_id": source_event_id,
    }
    roll_count = 0
    for combatant_id, loot_table_id in sorted(loot_sources, key=lambda s: s[0]):
        if loot_table_id is None:
            continue
        entries = registry.table_for(loot_table_id)
        for entry_index, entry in enumerate(entries):
            roll_count += 1
            if roll_count > LOOT_DRAW_CAP:
                raise LootError("COMBAT_LOOT_TABLE_INVALID", "loot roll cap exceeded")
            draw_count = 1
            # drop_permille=1000 的保底条目仍消费 draw（顺序稳定性）
            if loot_stream.draw_bounded_uint32(1000) >= entry.drop_permille:
                continue
            if entry.quantity_max == entry.quantity_min:
                quantity = entry.quantity_min  # 单值不消费数量 draw
            else:
                draw_count += 1
                quantity = entry.quantity_min + loot_stream.draw_bounded_uint32(
                    entry.quantity_max - entry.quantity_min + 1
                )
            is_currency = entry.item_definition_id == CURRENCY_ITEM_DEFINITION_ID
            idem = f"{encounter_id}:loot:{combatant_id}:{entry_index}"
            if is_currency:
                item_ref = econ_port.mint_currency(
                    amount_copper_feather=quantity, idempotency_key=idem, provenance=provenance
                )
            else:
                item_ref = econ_port.mint_loot_item(
                    item_definition_id=entry.item_definition_id,
                    quantity=quantity,
                    idempotency_key=idem,
                    provenance=provenance,
                )
            outcome.drops.append(
                LootDrop(
                    loot_table_id=loot_table_id,
                    item_definition_id=entry.item_definition_id,
                    quantity=quantity,
                    item_ref=item_ref,
                    source_kind="creature_loot",
                    source_combatant_id=combatant_id,
                    is_currency=is_currency,
                    draw_count=draw_count,
                )
            )
    for yield_index, yielded in enumerate(negotiation_yields):
        idem = f"{encounter_id}:yield:{yield_index}"
        if yielded.is_currency:
            item_ref = econ_port.mint_currency(
                amount_copper_feather=yielded.quantity, idempotency_key=idem, provenance=provenance
            )
        else:
            if yielded.item_instance_id is None:
                raise LootError("COMBAT_LOOT_TABLE_INVALID", "yield item without instance")
            econ_port.transfer_yield_item(
                item_instance_id=yielded.item_instance_id,
                idempotency_key=idem,
                provenance=provenance,
            )
            item_ref = yielded.item_instance_id
        outcome.drops.append(
            LootDrop(
                loot_table_id=None,
                item_definition_id=yielded.item_definition_id,
                quantity=yielded.quantity,
                item_ref=item_ref,
                source_kind="negotiation_yield",
                source_combatant_id=None,
                is_currency=yielded.is_currency,
                draw_count=0,
            )
        )
    _assign_victors(
        outcome.drops,
        winning_side=winning_side,
        surviving_members=surviving_members,
        location_container_inventory_id=location_container_inventory_id,
        econ_port=econ_port,
    )
    return outcome


def _assign_victors(
    drops: List[LootDrop],
    *,
    winning_side: Optional[Side],
    surviving_members: List[Tuple[str, str]],
    location_container_inventory_id: str,
    econ_port: CombatEconPort,
) -> None:
    """RULE-COMBAT-057：Item ULID 升序轮转；溢出/无存活/平手 → 地点容器"""
    ordered = sorted(drops, key=lambda d: d.item_ref)
    members = sorted(surviving_members, key=lambda m: m[0])
    use_rotation = winning_side is Side.PARTY and len(members) > 0
    for index, drop in enumerate(ordered):
        assigned: Optional[str] = None
        if use_rotation:
            _, inventory_id = members[index % len(members)]
            if econ_port.deposit_to_inventory(item_ref=drop.item_ref, inventory_id=inventory_id):
                assigned = inventory_id
        if assigned is None:
            # 地点容器视为无限容量；False 说明 ECON 故障，回滚整个结果事务
            if not econ_port.deposit_to_inventory(
                item_ref=drop.item_ref, inventory_id=location_container_inventory_id
            ):
                raise LootError(
                    "COMBAT_LOOT_TABLE_INVALID", "location container rejected deposit"
                )
            assigned = location_container_inventory_id
        object.__setattr__(drop, "assigned_inventory_id", assigned)
