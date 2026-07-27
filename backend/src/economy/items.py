"""
物品数据模型（DOC-ECON-004）

- RULE-ECON-013：Definition 严格 Schema、五种 kind、未知 Definition 禁止创建
- RULE-ECON-014：active Item/Batch 同一 Revision 恰有一个 current_container
- RULE-ECON-015：stack 数量守恒；quantity=0 同事务移除
- RULE-ECON-016：provenance 追加式，不改写不截断
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..foundation import generate_ulid
from .constants import ItemKind, ItemState


class ItemError(Exception):
    """物品操作失败；code 为稳定 reason code"""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


#: DES-ECON-004 strict manifest（实现与 Contract Test 的权威）
ITEM_DEFINITION_FIELDS = frozenset(
    {
        "schema_version", "item_definition_id", "item_kind", "display_name_key",
        "unit_weight_grams", "max_stack_quantity", "tags",
        "quality_grade_min", "quality_grade_max", "kind_config",
    }
)
ITEM_INSTANCE_FIELDS = frozenset(
    {
        "schema_version", "item_id", "item_definition_id", "item_kind",
        "quality_grade", "current_container", "provenance_head_event_id",
        "state", "kind_data", "created_game_time", "last_revision",
    }
)
STACK_BATCH_FIELDS = frozenset(
    {
        "schema_version", "batch_id", "item_definition_id", "item_kind",
        "quality_grade", "condition_key", "provenance_class_id", "quantity",
        "current_container", "provenance_head_event_id", "state",
        "created_game_time", "last_revision",
    }
)
CONTAINER_FIELDS = frozenset({"inventory_id", "slot_key"})

#: kind 分支的 kind_config / kind_data 精确字段
KIND_CONFIG_FIELDS = {
    ItemKind.STACKABLE: frozenset({"merge_field_ids"}),
    ItemKind.UNIQUE: frozenset(),
    ItemKind.CONTAINER: frozenset({"child_inventory_kind", "max_nested_depth"}),
    ItemKind.PROPERTY_DEED: frozenset({"allowed_subject_kinds"}),
    ItemKind.MAGICAL: frozenset({"magic_definition_id"}),
}
KIND_DATA_FIELDS = {
    ItemKind.UNIQUE: frozenset(),
    ItemKind.CONTAINER: frozenset({"child_inventory_id"}),
    ItemKind.PROPERTY_DEED: frozenset(
        {"property_subject_kind", "property_subject_id", "property_subject_version"}
    ),
    ItemKind.MAGICAL: frozenset({"magic_definition_id"}),
}
INSTANCE_ALLOWED_KINDS = frozenset(
    {ItemKind.UNIQUE, ItemKind.CONTAINER, ItemKind.PROPERTY_DEED, ItemKind.MAGICAL}
)

_RANGES_DEFINITION = {
    "unit_weight_grams": (0, 1_000_000),
    "max_stack_quantity": (1, 9999),
    "quality_grade_min": (0, 9),
    "quality_grade_max": (0, 9),
}


def _check_exact_fields(record: dict, exact: frozenset, record_name: str) -> None:
    extra = set(record) - set(exact)
    if extra:
        raise ItemError(
            "schema_additional_property", f"{record_name} extra: {sorted(extra)}"
        )
    missing = set(exact) - set(record)
    if missing:
        raise ItemError(
            "schema_missing_field", f"{record_name} missing: {sorted(missing)}"
        )


def _check_int_range(record: dict, field_name: str, low: int, high: int) -> None:
    value = record[field_name]
    if isinstance(value, bool) or not isinstance(value, int) or not (low <= value <= high):
        raise ItemError(
            "invalid_stack_quantity" if field_name == "quantity" else "schema_field_out_of_range",
            f"{field_name}={value!r} outside [{low},{high}]",
        )


def _check_container(value: object) -> Dict:
    if not isinstance(value, dict):
        raise ItemError("schema_missing_field", "current_container must be object")
    _check_exact_fields(value, CONTAINER_FIELDS, "current_container")
    if value["inventory_id"] is None or value["slot_key"] is None:
        raise ItemError(
            "schema_missing_field", "current_container fields must be non-null"
        )
    return value


def decode_item_definition(record: dict) -> Dict:
    """RULE-ECON-013：构建期 Definition 严格解析"""
    _check_exact_fields(record, ITEM_DEFINITION_FIELDS, "item_definition")
    try:
        kind = ItemKind(record["item_kind"])
    except ValueError as exc:
        raise ItemError("item_kind_mismatch", str(exc)) from exc
    for field_name, (low, high) in _RANGES_DEFINITION.items():
        _check_int_range(record, field_name, low, high)
    if record["quality_grade_min"] > record["quality_grade_max"]:
        raise ItemError("schema_field_out_of_range", "quality min > max")
    config = record["kind_config"]
    if not isinstance(config, dict):
        raise ItemError("schema_missing_field", "kind_config must be object")
    _check_exact_fields(config, KIND_CONFIG_FIELDS[kind], f"kind_config.{kind.value}")
    if kind is ItemKind.STACKABLE:
        if not (2 <= record["max_stack_quantity"] <= 9999):
            raise ItemError(
                "invalid_stack_quantity", "stackable max_stack_quantity must be 2..9999"
            )
    elif record["max_stack_quantity"] != 1:
        # §5：非 stackable 的 max_stack_quantity 固定为 1
        raise ItemError(
            "invalid_stack_quantity", f"{kind.value} max_stack_quantity must be 1"
        )
    return record


def decode_item_instance(record: dict) -> Dict:
    _check_exact_fields(record, ITEM_INSTANCE_FIELDS, "item_instance")
    try:
        kind = ItemKind(record["item_kind"])
    except ValueError as exc:
        raise ItemError("item_kind_mismatch", str(exc)) from exc
    if kind is ItemKind.STACKABLE:
        # manifest：stackable 禁止 item_instance 形态
        raise ItemError("item_kind_mismatch", "stackable must use stack_batch record")
    if kind not in INSTANCE_ALLOWED_KINDS:
        raise ItemError("item_kind_mismatch", f"{kind.value} not allowed for instance")
    ItemState(record["state"])
    _check_int_range(record, "quality_grade", 0, 9)
    _check_container(record["current_container"])
    kind_data = record["kind_data"]
    if not isinstance(kind_data, dict):
        raise ItemError("schema_missing_field", "kind_data must be object")
    _check_exact_fields(kind_data, KIND_DATA_FIELDS[kind], f"kind_data.{kind.value}")
    return record


def decode_stack_batch(record: dict) -> Dict:
    _check_exact_fields(record, STACK_BATCH_FIELDS, "stack_batch")
    if record["item_kind"] != ItemKind.STACKABLE.value:
        raise ItemError("item_kind_mismatch", "stack_batch item_kind must be stackable")
    ItemState(record["state"])
    _check_int_range(record, "quality_grade", 0, 9)
    _check_int_range(record, "quantity", 1, 999999)
    _check_container(record["current_container"])
    return record


@dataclass
class ItemRegistry:
    """
    ItemInstance/StackBatch 运行时注册表：ownership 唯一索引 + provenance 链。
    """

    definitions: Dict[str, Dict] = field(default_factory=dict)
    _instances: Dict[str, Dict] = field(default_factory=dict)
    _batches: Dict[str, Dict] = field(default_factory=dict)
    # RULE-ECON-014：item_or_batch_id -> (inventory_id, slot_key)
    _ownership_index: Dict[str, Tuple[str, str]] = field(default_factory=dict)
    # RULE-ECON-016：追加式 provenance：entity_id -> [event payloads]
    _provenance: Dict[str, List[Dict]] = field(default_factory=dict)

    # -- 注册 --

    def register_definition(self, record: dict) -> None:
        decode_item_definition(record)
        self.definitions[record["item_definition_id"]] = record

    def _require_definition(self, item_definition_id: str) -> Dict:
        definition = self.definitions.get(item_definition_id)
        if definition is None:
            raise ItemError("item_definition_unknown", item_definition_id)
        return definition

    def _append_provenance(self, entity_id: str, edge: Dict) -> None:
        self._provenance.setdefault(entity_id, []).append(edge)

    def provenance_chain(self, entity_id: str) -> List[Dict]:
        return list(self._provenance.get(entity_id, []))

    def claim_container(self, entity_id: str, inventory_id: str, slot_key: str) -> None:
        """RULE-ECON-014：唯一 ownership 索引；重复声明即冲突"""
        if entity_id in self._ownership_index:
            raise ItemError("duplicate_unique_owner", entity_id)
        self._ownership_index[entity_id] = (inventory_id, slot_key)

    def move_container(self, entity_id: str, inventory_id: str, slot_key: str) -> None:
        """Transaction commit 才允许改写 current_container（原子由调用方保证）"""
        if entity_id not in self._ownership_index:
            raise ItemError("provenance_missing", f"{entity_id} not in ownership index")
        self._ownership_index[entity_id] = (inventory_id, slot_key)
        record = self._instances.get(entity_id) or self._batches.get(entity_id)
        if record is not None:
            record["current_container"] = {"inventory_id": inventory_id, "slot_key": slot_key}

    def owner_of(self, entity_id: str) -> Optional[Tuple[str, str]]:
        return self._ownership_index.get(entity_id)

    def ownership_index_count(self, entity_id: str) -> int:
        return 1 if entity_id in self._ownership_index else 0

    # -- 创建 --

    def create_instance(
        self,
        item_definition_id: str,
        inventory_id: str,
        slot_key: str,
        source_event_id: Optional[str],
        game_time: int,
        quality_grade: int = 0,
        kind_data: Optional[Dict] = None,
    ) -> Dict:
        definition = self._require_definition(item_definition_id)
        if not source_event_id:
            raise ItemError("provenance_missing", "source event required")
        kind = ItemKind(definition["item_kind"])
        if kind is ItemKind.STACKABLE:
            raise ItemError("item_kind_mismatch", "use create_batch for stackable")
        record = {
            "schema_version": 1,
            "item_id": generate_ulid(),
            "item_definition_id": item_definition_id,
            "item_kind": kind.value,
            "quality_grade": quality_grade,
            "current_container": {"inventory_id": inventory_id, "slot_key": slot_key},
            "provenance_head_event_id": source_event_id,
            "state": ItemState.ACTIVE.value,
            "kind_data": kind_data if kind_data is not None else _default_kind_data(kind),
            "created_game_time": game_time,
            "last_revision": 0,
        }
        decode_item_instance(record)
        self.claim_container(record["item_id"], inventory_id, slot_key)
        self._instances[record["item_id"]] = record
        self._append_provenance(
            record["item_id"], {"event_id": source_event_id, "kind": "created", "game_time": game_time}
        )
        return record

    def create_batch(
        self,
        item_definition_id: str,
        quantity: int,
        inventory_id: str,
        slot_key: str,
        source_event_id: Optional[str],
        game_time: int,
        quality_grade: int = 0,
        condition_key: str = "condition.default",
        provenance_class_id: str = "provenance.registered",
    ) -> Dict:
        definition = self._require_definition(item_definition_id)
        if not source_event_id:
            raise ItemError("provenance_missing", "source event required")
        if ItemKind(definition["item_kind"]) is not ItemKind.STACKABLE:
            raise ItemError("item_kind_mismatch", "definition is not stackable")
        record = {
            "schema_version": 1,
            "batch_id": generate_ulid(),
            "item_definition_id": item_definition_id,
            "item_kind": ItemKind.STACKABLE.value,
            "quality_grade": quality_grade,
            "condition_key": condition_key,
            "provenance_class_id": provenance_class_id,
            "quantity": quantity,
            "current_container": {"inventory_id": inventory_id, "slot_key": slot_key},
            "provenance_head_event_id": source_event_id,
            "state": ItemState.ACTIVE.value,
            "created_game_time": game_time,
            "last_revision": 0,
        }
        decode_stack_batch(record)
        self.claim_container(record["batch_id"], inventory_id, slot_key)
        self._batches[record["batch_id"]] = record
        self._append_provenance(
            record["batch_id"], {"event_id": source_event_id, "kind": "created", "quantity": quantity, "game_time": game_time}
        )
        return record

    # -- stack 守恒 --

    def _require_batch(self, batch_id: str) -> Dict:
        batch = self._batches.get(batch_id)
        if batch is None:
            raise ItemError("item_definition_unknown", f"unknown batch {batch_id}")
        return batch

    def split_batch(self, batch_id: str, quantities: List[int], slot_keys: List[str], game_time: int) -> List[Dict]:
        """RULE-ECON-015：拆分前后总量与 provenance 数量守恒"""
        batch = self._require_batch(batch_id)
        if batch["state"] != ItemState.ACTIVE.value:
            raise ItemError("item_kind_mismatch", "cannot split tombstone")
        if not quantities or any(q <= 0 for q in quantities) or sum(quantities) >= batch["quantity"]:
            raise ItemError(
                "invalid_stack_quantity",
                "parts must be positive and sum < original",
            )
        if len(quantities) != len(slot_keys):
            raise ItemError("invalid_stack_quantity", "slot_keys must match parts")
        inventory_id = batch["current_container"]["inventory_id"]
        remainder = batch["quantity"] - sum(quantities)
        created: List[Dict] = []
        for part, slot_key in zip(quantities, slot_keys):
            record = self.create_batch(
                batch["item_definition_id"], part, inventory_id, slot_key,
                source_event_id=batch["provenance_head_event_id"], game_time=game_time,
                quality_grade=batch["quality_grade"],
                condition_key=batch["condition_key"],
                provenance_class_id=batch["provenance_class_id"],
            )
            self._append_provenance(
                record["batch_id"],
                {"kind": "split_from", "source_batch_id": batch_id, "quantity": part, "game_time": game_time},
            )
            created.append(record)
        batch["quantity"] = remainder
        self._append_provenance(
            batch_id, {"kind": "split_to", "new_batch_ids": [r["batch_id"] for r in created], "remainder": remainder, "game_time": game_time}
        )
        return created

    @staticmethod
    def _merge_key(batch: Dict) -> Tuple:
        return (
            batch["item_definition_id"],
            batch["quality_grade"],
            batch["condition_key"],
            batch["provenance_class_id"],
        )

    def merge_batches(self, batch_ids: List[str], game_time: int) -> Dict:
        """§7：只有 merge key 完全一致才可合并"""
        if len(batch_ids) < 2:
            raise ItemError("merge_key_mismatch", "need at least two batches")
        batches = [self._require_batch(bid) for bid in batch_ids]
        keys = {self._merge_key(b) for b in batches}
        if len(keys) != 1:
            raise ItemError("merge_key_mismatch", "merge keys differ")
        containers = {b["current_container"]["inventory_id"] for b in batches}
        if len(containers) != 1:
            raise ItemError("merge_key_mismatch", "batches must share inventory")
        total = sum(b["quantity"] for b in batches)
        survivor = batches[0]
        survivor["quantity"] = total
        for consumed in batches[1:]:
            self._tombstone(consumed["batch_id"], is_batch=True, state=ItemState.CONSUMED)
            self._append_provenance(
                consumed["batch_id"], {"kind": "merged_into", "survivor_batch_id": survivor["batch_id"], "game_time": game_time}
            )
        self._append_provenance(
            survivor["batch_id"], {"kind": "merged", "quantity": total, "game_time": game_time}
        )
        return survivor

    def consume_batch(self, batch_id: str, quantity: int, game_time: int) -> Dict:
        """RULE-ECON-015：quantity=0 的 batch 必须在同事务移除"""
        batch = self._require_batch(batch_id)
        if quantity <= 0 or quantity > batch["quantity"]:
            raise ItemError("invalid_stack_quantity", f"consume {quantity}")
        batch["quantity"] -= quantity
        self._append_provenance(
            batch_id, {"kind": "consumed", "quantity": quantity, "game_time": game_time}
        )
        if batch["quantity"] == 0:
            self._tombstone(batch_id, is_batch=True, state=ItemState.CONSUMED)
        return batch

    # -- tombstone --

    def _tombstone(self, entity_id: str, is_batch: bool, state: ItemState) -> None:
        """§5：tombstone 离开 ownership 索引，保留最后 container 供审计"""
        record = (self._batches if is_batch else self._instances).get(entity_id)
        if record is None:
            raise ItemError("item_definition_unknown", entity_id)
        record["state"] = state.value
        self._ownership_index.pop(entity_id, None)

    def destroy_instance(self, item_id: str, game_time: int) -> Dict:
        instance = self._instances.get(item_id)
        if instance is None:
            raise ItemError("item_definition_unknown", item_id)
        self._append_provenance(item_id, {"kind": "destroyed", "game_time": game_time})
        self._tombstone(item_id, is_batch=False, state=ItemState.DESTROYED)
        return instance

    def get_instance(self, item_id: str) -> Optional[Dict]:
        return self._instances.get(item_id)

    def get_batch(self, batch_id: str) -> Optional[Dict]:
        return self._batches.get(batch_id)


def _default_kind_data(kind: ItemKind) -> Dict:
    """kind_data 的合法默认（字段齐全、引用留空由调用方补齐）"""
    if kind is ItemKind.UNIQUE:
        return {}
    if kind is ItemKind.CONTAINER:
        return {"child_inventory_id": None}
    if kind is ItemKind.PROPERTY_DEED:
        return {
            "property_subject_kind": None,
            "property_subject_id": None,
            "property_subject_version": None,
        }
    return {"magic_definition_id": None}
