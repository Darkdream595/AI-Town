"""
TEST-ECON-013..016：物品数据模型（DOC-ECON-004）

- TEST-ECON-013：五种 kind strict schema；额外字段拒绝
- TEST-ECON-014：active Item 唯一 current_container 索引
- TEST-ECON-015：split/merge/consume 数量守恒
- TEST-ECON-016：provenance 追加链与 tombstone 出索引
"""

import pytest

from src.economy import (
    InventoryError,
    ItemError,
    ItemRegistry,
    ItemState,
    ReservationLedger,
    ResourceKind,
    decode_item_definition,
    decode_item_instance,
    decode_stack_batch,
)

_KIND_CONFIG = {
    "stackable": {"merge_field_ids": ["quality_grade", "condition_key"]},
    "unique": {},
    "container": {"child_inventory_kind": "container", "max_nested_depth": 2},
    "property_deed": {"allowed_subject_kinds": ["building"]},
    "magical": {"magic_definition_id": "magic.fixture.spark"},
}


def _definition(kind: str, **overrides):
    record = {
        "schema_version": 1,
        "item_definition_id": f"item.fixture.{kind}",
        "item_kind": kind,
        "display_name_key": f"item.name.{kind}",
        "unit_weight_grams": 100,
        "max_stack_quantity": 99 if kind == "stackable" else 1,
        "tags": [],
        "quality_grade_min": 0,
        "quality_grade_max": 9,
        "kind_config": dict(_KIND_CONFIG[kind]),
    }
    record.update(overrides)
    return record


def _registry_with_definitions():
    registry = ItemRegistry()
    for kind in ("stackable", "unique", "container", "property_deed", "magical"):
        registry.register_definition(_definition(kind))
    return registry


class TestStrictKindSchema:
    """TEST-ECON-013"""

    def test_all_five_kinds_decode(self):
        for kind in ("stackable", "unique", "container", "property_deed", "magical"):
            assert decode_item_definition(_definition(kind))["item_kind"] == kind

    def test_additional_field_rejected(self):
        with pytest.raises(ItemError) as excinfo:
            decode_item_definition(_definition("unique", rarity="legendary"))
        assert excinfo.value.code == "schema_additional_property"

    def test_missing_field_rejected(self):
        record = _definition("unique")
        del record["tags"]
        with pytest.raises(ItemError) as excinfo:
            decode_item_definition(record)
        assert excinfo.value.code == "schema_missing_field"

    def test_kind_config_extra_field_rejected(self):
        record = _definition("unique")
        record["kind_config"] = {"backdoor": True}
        with pytest.raises(ItemError) as excinfo:
            decode_item_definition(record)
        assert excinfo.value.code == "schema_additional_property"

    def test_stack_quantity_rules(self):
        with pytest.raises(ItemError) as excinfo:
            decode_item_definition(_definition("stackable", max_stack_quantity=1))
        assert excinfo.value.code == "invalid_stack_quantity"
        with pytest.raises(ItemError) as excinfo:
            decode_item_definition(_definition("unique", max_stack_quantity=2))
        assert excinfo.value.code == "invalid_stack_quantity"

    def test_instance_and_batch_shape_parity(self):
        registry = _registry_with_definitions()
        instance = registry.create_instance(
            "item.fixture.unique", "inventory.fixture.a", "slot.1", "event.create", 0
        )
        assert decode_item_instance(dict(instance))["item_kind"] == "unique"
        batch = registry.create_batch(
            "item.fixture.stackable", 10, "inventory.fixture.a", "slot.2", "event.stock", 0
        )
        assert decode_stack_batch(dict(batch))["quantity"] == 10
        bad_instance = dict(instance)
        bad_instance["color"] = "red"
        with pytest.raises(ItemError) as excinfo:
            decode_item_instance(bad_instance)
        assert excinfo.value.code == "schema_additional_property"

    def test_unknown_definition_rejected(self):
        registry = ItemRegistry()
        with pytest.raises(ItemError) as excinfo:
            registry.create_instance("item.fixture.ghost", "inv", "slot", "event.x", 0)
        assert excinfo.value.code == "item_definition_unknown"

    def test_create_requires_source_event(self):
        registry = _registry_with_definitions()
        with pytest.raises(ItemError) as excinfo:
            registry.create_instance("item.fixture.unique", "inv", "slot", None, 0)
        assert excinfo.value.code == "provenance_missing"


class TestCurrentContainerUnique:
    """TEST-ECON-014"""

    def test_ownership_index_single_entry(self):
        registry = _registry_with_definitions()
        instance = registry.create_instance(
            "item.fixture.unique", "inventory.fixture.a", "slot.1", "event.create", 0
        )
        item_id = instance["item_id"]
        assert registry.ownership_index_count(item_id) == 1
        assert registry.owner_of(item_id) == ("inventory.fixture.a", "slot.1")
        with pytest.raises(ItemError) as excinfo:
            registry.claim_container(item_id, "inventory.fixture.b", "slot.9")
        assert excinfo.value.code == "duplicate_unique_owner"
        assert registry.ownership_index_count(item_id) == 1

    def test_reservation_keeps_current_container(self):
        registry = _registry_with_definitions()
        instance = registry.create_instance(
            "item.fixture.unique", "inventory.fixture.a", "slot.1", "event.create", 0
        )
        item_id = instance["item_id"]
        ledger = ReservationLedger()
        reservation = ledger.reserve(
            owner_action_id="action.buy.1",
            binding_id="buy.unique",
            resource_kind=ResourceKind.UNIQUE_ITEM,
            resource_id=item_id,
            resource_version=0,
            source_inventory_id="inventory.fixture.a",
            holder_actor_id="resident.buyer",
            quantity=1,
            created_game_time=0,
            expires_at_game_time=60,
            request_revision=0,
            available_quantity=1,
            current_container_inventory_id="inventory.fixture.a",
        )
        # active Reservation 不改写 current_container
        assert registry.owner_of(item_id) == ("inventory.fixture.a", "slot.1")
        with pytest.raises(InventoryError) as excinfo:
            ledger.reserve(
                owner_action_id="action.buy.2",
                binding_id="buy.unique",
                resource_kind=ResourceKind.UNIQUE_ITEM,
                resource_id=item_id,
                resource_version=0,
                source_inventory_id="inventory.fixture.a",
                holder_actor_id="resident.buyer2",
                quantity=1,
                created_game_time=0,
                expires_at_game_time=60,
                request_revision=0,
                available_quantity=1,
                current_container_inventory_id="inventory.fixture.a",
            )
        assert excinfo.value.code == "reservation_conflict"
        ledger.release(reservation.reservation_id)
        assert ledger.availability(item_id, 1) == 1


class TestStackConservation:
    """TEST-ECON-015"""

    def test_split_merge_conserve_quantity(self):
        registry = _registry_with_definitions()
        batch = registry.create_batch(
            "item.fixture.stackable", 10, "inventory.fixture.a", "slot.1", "event.stock", 0
        )
        parts = registry.split_batch(batch["batch_id"], [4], ["slot.2"], game_time=10)
        assert parts[0]["quantity"] == 4
        assert batch["quantity"] == 6
        assert parts[0]["quantity"] + batch["quantity"] == 10
        survivor = registry.merge_batches([batch["batch_id"], parts[0]["batch_id"]], game_time=20)
        assert survivor["quantity"] == 10
        # 被合并方 tombstone 出索引
        assert registry.ownership_index_count(parts[0]["batch_id"]) == 0

    def test_split_rejects_full_or_excess(self):
        registry = _registry_with_definitions()
        batch = registry.create_batch(
            "item.fixture.stackable", 10, "inventory.fixture.a", "slot.1", "event.stock", 0
        )
        with pytest.raises(ItemError) as excinfo:
            registry.split_batch(batch["batch_id"], [4, 6], ["s1", "s2"], 10)
        assert excinfo.value.code == "invalid_stack_quantity"
        with pytest.raises(ItemError):
            registry.split_batch(batch["batch_id"], [11], ["s1"], 10)
        with pytest.raises(ItemError):
            registry.split_batch(batch["batch_id"], [0], ["s1"], 10)

    def test_consume_to_zero_tombstones(self):
        registry = _registry_with_definitions()
        batch = registry.create_batch(
            "item.fixture.stackable", 10, "inventory.fixture.a", "slot.1", "event.stock", 0
        )
        registry.consume_batch(batch["batch_id"], 3, game_time=10)
        assert batch["quantity"] == 7
        assert batch["state"] == ItemState.ACTIVE.value
        registry.consume_batch(batch["batch_id"], 7, game_time=20)
        assert batch["quantity"] == 0
        assert batch["state"] == ItemState.CONSUMED.value
        assert registry.ownership_index_count(batch["batch_id"]) == 0
        with pytest.raises(ItemError) as excinfo:
            registry.consume_batch(batch["batch_id"], 1, game_time=30)
        assert excinfo.value.code == "invalid_stack_quantity"

    def test_merge_key_mismatch_rejected(self):
        registry = _registry_with_definitions()
        first = registry.create_batch(
            "item.fixture.stackable", 5, "inventory.fixture.a", "slot.1", "event.stock", 0
        )
        second = registry.create_batch(
            "item.fixture.stackable", 5, "inventory.fixture.a", "slot.2", "event.stock", 0,
            quality_grade=3,
        )
        with pytest.raises(ItemError) as excinfo:
            registry.merge_batches([first["batch_id"], second["batch_id"]], game_time=10)
        assert excinfo.value.code == "merge_key_mismatch"


class TestProvenanceTombstone:
    """TEST-ECON-016"""

    def test_transfer_and_destroy_append_only_chain(self):
        registry = _registry_with_definitions()
        instance = registry.create_instance(
            "item.fixture.unique", "inventory.fixture.a", "slot.1", "event.create", 0
        )
        item_id = instance["item_id"]
        registry.move_container(item_id, "inventory.fixture.b", "slot.4")
        assert registry.owner_of(item_id) == ("inventory.fixture.b", "slot.4")
        registry.destroy_instance(item_id, game_time=30)
        # tombstone 保留审计但离开 ownership 索引
        assert registry.ownership_index_count(item_id) == 0
        assert registry.get_instance(item_id)["state"] == ItemState.DESTROYED.value
        chain = registry.provenance_chain(item_id)
        assert chain[0]["event_id"] == "event.create"
        assert chain[-1]["kind"] == "destroyed"
        assert len(chain) == 2  # 追加式，不改写不截断

    def test_consumed_batch_provenance_resolves_source(self):
        registry = _registry_with_definitions()
        batch = registry.create_batch(
            "item.fixture.stackable", 3, "inventory.fixture.a", "slot.1", "event.harvest", 0
        )
        registry.consume_batch(batch["batch_id"], 3, game_time=10)
        chain = registry.provenance_chain(batch["batch_id"])
        assert chain[0]["event_id"] == "event.harvest"
        assert [edge["kind"] for edge in chain] == ["created", "consumed"]
        assert registry.ownership_index_count(batch["batch_id"]) == 0
