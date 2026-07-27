"""
TEST-ECON-037..040：制作与资源消耗（DOC-ECON-010）

- TEST-ECON-037：Recipe 校验与 DAG 环拒绝
- TEST-ECON-038：开始前原子预留全部资源；并发冲突且失败无泄漏
- TEST-ECON-039：成功/失败 floor/取消三种结局
- TEST-ECON-040：崩溃重放 exactly-once，seed 位置不变
"""

import pytest

from src.economy import (
    CraftingEngine,
    CraftingError,
    CraftOrderState,
    InventoryKind,
    InventoryManager,
    ItemRegistry,
    RecipeDefinition,
    RecipeIO,
    RecipeRegistry,
    ReservationLedger,
    ReservationState,
)


def _stackable_definition(definition_id: str):
    return {
        "schema_version": 1,
        "item_definition_id": definition_id,
        "item_kind": "stackable",
        "display_name_key": f"item.name.{definition_id}",
        "unit_weight_grams": 100,
        "max_stack_quantity": 99,
        "tags": [],
        "quality_grade_min": 0,
        "quality_grade_max": 9,
        "kind_config": {"merge_field_ids": ["quality_grade", "condition_key"]},
    }


def _unique_definition(definition_id: str):
    record = _stackable_definition(definition_id)
    record["item_kind"] = "unique"
    record["max_stack_quantity"] = 1
    record["kind_config"] = {}
    return record


def _recipe(failure_bps=2500, iron=3, wood=1):
    return RecipeDefinition(
        recipe_id="recipe.smith.iron_pickaxe.v1",
        recipe_version=1,
        inputs=(RecipeIO("item.iron_ingot", iron), RecipeIO("item.treated_wood", wood)),
        outputs=(RecipeIO("item.iron_pickaxe", 1),),
        tool_capability_ids=("cap.smith_hammer",),
        station_capability_id="cap.anvil",
        duration_game_minutes=60,
        failure_consumption_bps=failure_bps,
    )


def _engine_with_stock(iron_qty=10, wood_qty=5):
    items = ItemRegistry()
    for definition_id in ("item.iron_ingot", "item.treated_wood", "item.iron_pickaxe"):
        items.register_definition(_stackable_definition(definition_id))
    items.register_definition(_unique_definition("item.smith_hammer"))
    inventories = InventoryManager()
    workshop = inventories.create_inventory("resident.smith", InventoryKind.WORKPLACE, 10, 100000)
    output = inventories.create_inventory("resident.smith", InventoryKind.RESIDENT, 10, 100000)
    iron = items.create_batch("item.iron_ingot", iron_qty, workshop.inventory_id, "slot.1", "event.stock", 0)
    wood = items.create_batch("item.treated_wood", wood_qty, workshop.inventory_id, "slot.2", "event.stock", 0)
    hammer = items.create_instance("item.smith_hammer", workshop.inventory_id, "slot.3", "event.stock", 0)
    reservations = ReservationLedger()
    engine = CraftingEngine(reservations, items, inventories)
    return {
        "engine": engine, "items": items, "inventories": inventories,
        "reservations": reservations, "workshop": workshop, "output": output,
        "iron": iron, "wood": wood, "hammer": hammer,
    }


def _begin(ctx, command_id="cmd-craft-1", action_id="action.craft.1", recipe=None, batch_size=1):
    recipe = recipe or _recipe()
    return ctx["engine"].begin_order(
        command_id=command_id,
        recipe=recipe,
        batch_size=batch_size,
        action_id=action_id,
        worker_id="resident.smith",
        target_inventory_id=ctx["output"].inventory_id,
        input_batches=[
            (ctx["iron"]["batch_id"], 0, ctx["iron"]["quantity"], ctx["workshop"].inventory_id),
            (ctx["wood"]["batch_id"], 0, ctx["wood"]["quantity"], ctx["workshop"].inventory_id),
        ],
        tool_items=[(ctx["hammer"]["item_id"], 0, ctx["workshop"].inventory_id)],
        station_id="station.anvil.1",
        game_time=0,
    )


class TestRecipeSchemaDag:
    """TEST-ECON-037"""

    def test_valid_recipe_accepted(self):
        registry = RecipeRegistry()
        registry.register(_recipe())
        assert registry.get("recipe.smith.iron_pickaxe.v1", 1).duration_game_minutes == 60

    def test_version_mismatch_rejected(self):
        registry = RecipeRegistry()
        registry.register(_recipe())
        with pytest.raises(CraftingError) as excinfo:
            registry.get("recipe.smith.iron_pickaxe.v1", 2)
        assert excinfo.value.code == "recipe_version_mismatch"

    def test_invalid_recipe_rejected(self):
        registry = RecipeRegistry()
        with pytest.raises(CraftingError):
            registry.register(RecipeDefinition(
                "r.bad", 1, (RecipeIO("item.a", 0),), (RecipeIO("item.b", 1),),
                (), "cap", 30, 2500,
            ))
        with pytest.raises(CraftingError):
            registry.register(RecipeDefinition(
                "r.bad2", 1, (RecipeIO("item.a", 1),), (RecipeIO("item.b", 1),),
                (), "cap", 30, 10001,
            ))
        with pytest.raises(CraftingError) as excinfo:
            registry.register(RecipeDefinition(
                "r.bad3", 0, (RecipeIO("item.a", 1),), (RecipeIO("item.b", 1),),
                (), "cap", 30, 2500,
            ))
        assert excinfo.value.code == "recipe_version_mismatch"

    def test_cycle_rejected(self):
        registry = RecipeRegistry()
        registry.register(RecipeDefinition(
            "recipe.a", 1, (RecipeIO("item.y", 1),), (RecipeIO("item.x", 1),),
            (), "cap", 30, 2500,
        ))
        with pytest.raises(CraftingError) as excinfo:
            registry.register(RecipeDefinition(
                "recipe.b", 1, (RecipeIO("item.x", 1),), (RecipeIO("item.y", 1),),
                (), "cap", 30, 2500,
            ))
        assert excinfo.value.code == "production_chain_cycle"


class TestCraftReservationSet:
    """TEST-ECON-038"""

    def test_begin_reserves_all_resources(self):
        ctx = _engine_with_stock()
        order = _begin(ctx)
        assert order.state is CraftOrderState.RESERVED
        assert len(order.reservation_ids) == 4  # iron + wood + hammer + station
        reservations = ctx["reservations"]
        assert reservations.active_quantity(ctx["iron"]["batch_id"]) == 3
        assert reservations.active_quantity(ctx["wood"]["batch_id"]) == 1
        assert reservations.active_quantity(ctx["hammer"]["item_id"]) == 1
        assert reservations.active_quantity("station.anvil.1") == 1
        # 预留不改写 current_container
        assert ctx["items"].owner_of(ctx["iron"]["batch_id"])[0] == ctx["workshop"].inventory_id

    def test_concurrent_second_craft_conflict(self):
        ctx = _engine_with_stock()
        _begin(ctx)
        with pytest.raises(Exception) as excinfo:
            _begin(ctx, command_id="cmd-craft-2", action_id="action.craft.2")
        assert excinfo.value.code == "reservation_conflict"
        # 第二单失败无泄漏：active 数量仍只有第一单的 3/1/1/1
        reservations = ctx["reservations"]
        assert reservations.active_quantity(ctx["iron"]["batch_id"]) == 3
        assert reservations.active_quantity("station.anvil.1") == 1
        leaked = [
            r for r in reservations._reservations.values()
            if r.owner_action_id == "action.craft.2" and r.state is ReservationState.ACTIVE
        ]
        assert leaked == []

    def test_missing_tool_releases_everything(self):
        ctx = _engine_with_stock()
        recipe = _recipe()
        with pytest.raises(CraftingError) as excinfo:
            ctx["engine"].begin_order(
                command_id="cmd-craft-bad",
                recipe=recipe,
                batch_size=1,
                action_id="action.craft.bad",
                worker_id="resident.smith",
                target_inventory_id=ctx["output"].inventory_id,
                input_batches=[
                    (ctx["iron"]["batch_id"], 0, ctx["iron"]["quantity"], ctx["workshop"].inventory_id),
                    (ctx["wood"]["batch_id"], 0, ctx["wood"]["quantity"], ctx["workshop"].inventory_id),
                ],
                tool_items=[("item.ghost_hammer", 0, ctx["workshop"].inventory_id)],
                station_id="station.anvil.1",
                game_time=0,
            )
        assert excinfo.value.code == "tool_unavailable"
        reservations = ctx["reservations"]
        assert reservations.active_quantity(ctx["iron"]["batch_id"]) == 0
        assert reservations.active_quantity(ctx["wood"]["batch_id"]) == 0
        assert reservations.active_quantity("station.anvil.1") == 0

    def test_batch_size_bounds(self):
        ctx = _engine_with_stock()
        with pytest.raises(CraftingError):
            _begin(ctx, batch_size=0)
        with pytest.raises(CraftingError):
            _begin(ctx, batch_size=33)


class TestCraftOutcomes:
    """TEST-ECON-039"""

    def test_success_consumes_inputs_and_creates_output(self):
        ctx = _engine_with_stock()
        order = _begin(ctx)
        completed = ctx["engine"].complete("cmd-complete", order.craft_order_id, _recipe(), success=True, game_time=60)
        assert completed.state is CraftOrderState.COMPLETED
        assert ctx["iron"]["quantity"] == 7
        assert ctx["wood"]["quantity"] == 4
        output_inv = ctx["output"].inventory_id
        outputs = [
            b for b in ctx["items"]._batches.values()
            if b["item_definition_id"] == "item.iron_pickaxe"
            and b["current_container"]["inventory_id"] == output_inv
        ]
        assert len(outputs) == 1
        assert outputs[0]["quantity"] == 1
        crafted = [e for e in ctx["items"].provenance_chain(outputs[0]["batch_id"]) if e["kind"] == "crafted"]
        assert crafted[0]["recipe_id"] == "recipe.smith.iron_pickaxe.v1"
        assert crafted[0]["action_id"] == "action.craft.1"

    def test_failure_floor_rule(self):
        # floor(3 × 2500 / 10000) = 0；floor(4 × 2500 / 10000) = 1
        assert CraftingEngine.failure_consumed_quantity(3, 2500) == 0
        assert CraftingEngine.failure_consumed_quantity(4, 2500) == 1
        ctx = _engine_with_stock()
        order = _begin(ctx)
        failed = ctx["engine"].complete("cmd-fail", order.craft_order_id, _recipe(), success=False, game_time=60)
        assert failed.state is CraftOrderState.FAILED
        # 2500bps 下 iron 3 与 wood 1 的 floor 消耗都是 0：无泄漏也无凭空销毁
        assert ctx["iron"]["quantity"] == 10
        assert ctx["wood"]["quantity"] == 5
        # 未产出
        assert [b for b in ctx["items"]._batches.values() if b["item_definition_id"] == "item.iron_pickaxe"] == []

    def test_failure_with_consumption(self):
        ctx = _engine_with_stock()
        recipe = _recipe(failure_bps=5000)
        order = _begin(ctx, recipe=recipe)
        ctx["engine"].complete("cmd-fail", order.craft_order_id, recipe, success=False, game_time=60)
        # floor(3 × 5000 / 10000) = 1；floor(1 × 5000 / 10000) = 0
        assert ctx["iron"]["quantity"] == 9
        assert ctx["wood"]["quantity"] == 5

    def test_cancel_releases_unconsumed(self):
        ctx = _engine_with_stock()
        order = _begin(ctx)
        cancelled = ctx["engine"].cancel("cmd-cancel", order.craft_order_id)
        assert cancelled.state is CraftOrderState.CANCELLED
        reservations = ctx["reservations"]
        assert reservations.active_quantity(ctx["iron"]["batch_id"]) == 0
        assert reservations.active_quantity("station.anvil.1") == 0
        assert ctx["iron"]["quantity"] == 10
        assert ctx["wood"]["quantity"] == 5


class TestCraftCrashReplay:
    """TEST-ECON-040"""

    def test_begin_replay_does_not_double_reserve(self):
        ctx = _engine_with_stock()
        first = _begin(ctx)
        replay = _begin(ctx)
        assert replay.craft_order_id == first.craft_order_id
        assert ctx["reservations"].active_quantity(ctx["iron"]["batch_id"]) == 3

    def test_complete_replay_creates_output_once(self):
        ctx = _engine_with_stock()
        order = _begin(ctx)
        recipe = _recipe()
        completed = ctx["engine"].complete("cmd-complete", order.craft_order_id, recipe, success=True, game_time=60)
        seed_before = completed.seed_stream_position
        replay = ctx["engine"].complete("cmd-complete", order.craft_order_id, recipe, success=True, game_time=60)
        assert replay.craft_order_id == completed.craft_order_id
        outputs = [
            b for b in ctx["items"]._batches.values()
            if b["item_definition_id"] == "item.iron_pickaxe"
        ]
        assert len(outputs) == 1
        assert ctx["iron"]["quantity"] == 7
        assert replay.seed_stream_position == seed_before

    def test_resend_completion_command_after_recovery(self):
        ctx = _engine_with_stock()
        order = _begin(ctx)
        recipe = _recipe()
        first = ctx["engine"].complete("cmd-complete", order.craft_order_id, recipe, success=True, game_time=60)
        # 崩溃恢复后重发同一完成命令：结果一致且不重复产出
        resent = ctx["engine"].complete("cmd-complete", order.craft_order_id, recipe, success=True, game_time=60)
        assert resent.state is CraftOrderState.COMPLETED
        assert first.seed_stream_position == resent.seed_stream_position
        with pytest.raises(CraftingError) as excinfo:
            ctx["engine"].complete("cmd-complete-new", order.craft_order_id, recipe, success=True, game_time=60)
        assert excinfo.value.code == "craft_recovery_required"
