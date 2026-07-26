---
doc_id: DOC-ECON-012
title: 经济守恒、平衡与恢复测试
version: 1.0.0
status: approved-for-implementation
owner_domain: economy
canonical_for:
  - economy-acceptance-suite
  - conservation-audit
  - economy-recovery-tests
depends_on:
  - DOC-FOUNDATION-005
  - DOC-ECON-001
  - DOC-ECON-002
  - DOC-ECON-003
  - DOC-ECON-004
  - DOC-ECON-005
  - DOC-ECON-006
  - DOC-ECON-007
  - DOC-ECON-008
  - DOC-ECON-009
  - DOC-ECON-010
  - DOC-ECON-011
requirements:
  - REQ-ECON-012
last_updated: 2026-07-26
---

# 经济守恒、平衡与恢复测试

## 1. 目的

`REQ-ECON-012`：给出可自动执行的 Contract、Property、Integration、Simulation 与 Recovery 验收，覆盖货币/物品守恒、并发、价格边界、高倍速、短缺、工资、制作、产权和公共预算。

## 2. 非目标

本文不以“看起来合理”的单次游玩替代统计与不变量断言，不调用真实 DeepSeek 决定测试结果，也不要求首版经济达到现实宏观精度。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Conservation Snapshot | 在 Revision 边界统计账户、Item、batch 与 active Reservation 的测试投影 |
| Source/Sink Allowlist | 允许改变总量的注册事件类型与预期 delta |
| Crash Boundary | Unit of Work 中每个可注入中断点 |
| Speed Equivalence | 相同 Seed、Command/Event 序列和 GameTime 终点在不同倍率下状态 hash 相同 |
| Balance Envelope | 30 日模拟中允许的库存、价格、欠薪和短缺有界范围 |

## 4. 规则与不变量

- `RULE-ECON-045`：每个成功 Transaction 后必须立即检查 currency sum、unique ownership、stack quantity、Inventory capacity 与 Reservation consumed/released 一致性。
- `RULE-ECON-046`：恢复解除 Recovery Barrier 前必须全量验证 Ledger 重算余额、Item ownership index、Inventory cache、active Reservation 与 terminal Transaction。
- `RULE-ECON-047`：`0.5×/1×/2×/4×` 在相同 GameTime 终点必须产生相同经济 state hash；`0×` 不滚动窗口、不计工时、不使 Reservation 自然过期。
- `RULE-ECON-048`：1/7/30 日模拟不得出现负余额/库存、重复 unique、无界 Quote、永久 active Reservation、无限 production cycle 或无来源 Item/Currency。

## 5. 数据与接口

`DES-ECON-012`：最小 machine-readable acceptance fixture：

```json
{
  "fixture_version": 1,
  "world_seed_hex": "000102030405060708090a0b0c0d0e0f",
  "residents": 10,
  "initial_currency_copper_feather": 50000,
  "initial_unique_item_ids": 12,
  "simulation_end_game_times": [1440, 10080, 43200],
  "speed_multipliers": [0.5, 1, 2, 4],
  "crash_boundaries": [
    "after_reservations",
    "after_state_writes_before_events",
    "after_events_before_idempotency",
    "after_database_commit_before_outbox"
  ],
  "required_assertions": [
    "currency_conserved_except_allowlisted_sources_sinks",
    "unique_owner_count_equals_one",
    "stack_and_inventory_non_negative",
    "transaction_exactly_once",
    "speed_state_hash_equal",
    "recovery_barrier_audit_passed"
  ]
}
```

`TEST-ECON-001..044` 的 machine-readable fixture/case/oracle registry 如下。`fixture.initial_state` 是 runner 的最小权威输入；`command_sequence` 按顺序执行，`concurrent(...)` 与 `crash(...)` 是 runner 注册操作，不是自由文本解释：

```json
{
  "test_registry_version": 1,
  "fixtures": [
    {"fixture_id": "econ.currency.v1", "initial_state": {"buyer_balance": 1234, "seller_balance": 0, "public_balance": 0, "mint_allowlist": ["world_bootstrap"]}},
    {"fixture_id": "econ.employment.v1", "initial_state": {"worker_id": "resident.fixture.worker", "player_worker_id": "resident.fixture.player", "workplace_capacity": 1, "qualifications": ["profession.blacksmith"]}},
    {"fixture_id": "econ.shift.v1", "initial_state": {"shift": [480, 720], "wage_per_shift": 180, "employer_balance": 1000, "credited_ranges": []}},
    {"fixture_id": "econ.item.v1", "initial_state": {"definitions": ["stackable", "unique", "container", "property_deed", "magical"], "unique_current_container": "inventory.fixture.a", "stack_quantity": 10}},
    {"fixture_id": "econ.inventory.v1", "initial_state": {"source_slots": 4, "target_max_slots": 2, "target_max_weight_grams": 5000, "container_depth": 0, "item_quantity": 3}},
    {"fixture_id": "econ.transaction.v1", "initial_state": {"buyer_balance": 110, "seller_balance": 0, "public_balance": 0, "unique_current_container": "inventory.fixture.shop", "command_results": {}}},
    {"fixture_id": "econ.shop.v1", "initial_state": {"opening_interval": [480, 1080], "staff_coverage": 1, "stock": 1, "service_capacity": 1, "service_node_ready": true}},
    {"fixture_id": "econ.pricing.v1", "initial_state": {"base_price": 100, "floor": 50, "ceiling": 300, "quote_ttl_minutes": 10, "scarcity_policy": "scarcity_policy.local_market.v1"}},
    {"fixture_id": "econ.market.v1", "initial_state": {"window_minutes": 1440, "bucket_minutes": 60, "reorder_threshold": 10, "policy_version": 1, "buckets": 24}},
    {"fixture_id": "econ.crafting.v1", "initial_state": {"recipe_id": "recipe.smith.iron_pickaxe.v1", "inputs": {"iron_ingot": 3, "treated_wood": 1}, "station_capacity": 1, "output_capacity": 1}},
    {"fixture_id": "econ.property_budget.v1", "initial_state": {"subject_id": "building.fixture.one", "active_deed_count": 1, "public_balance": 5000, "appropriation_authorized": 5000, "spent": 1200, "active_encumbrance": 1800}}
  ],
  "cases": [
    {"test_id": "TEST-ECON-001", "fixture_id": "econ.currency.v1", "case_id": "currency_round_trip", "runner": "economy.currency.contract", "command_sequence": ["format(1234)", "parse(display)"], "oracle": "parsed_copper_feather == 1234 && display == '12SC34CF'"},
    {"test_id": "TEST-ECON-002", "fixture_id": "econ.currency.v1", "case_id": "ledger_conservation", "runner": "economy.currency.contract", "command_sequence": ["transfer(110,buyer,seller=100,public=10)"], "oracle": "sum(currency_legs) == 0 && balances == [1124,100,10]"},
    {"test_id": "TEST-ECON-003", "fixture_id": "econ.currency.v1", "case_id": "concurrent_overdraft", "runner": "economy.currency.concurrent", "command_sequence": ["concurrent(debit_900,debit_900)", "unauthorized_mint(1)"], "oracle": "committed_count == 1 && loser_error == 'insufficient_funds' && mint_error == 'mint_permission_denied'"},
    {"test_id": "TEST-ECON-004", "fixture_id": "econ.currency.v1", "case_id": "ledger_recovery", "runner": "economy.currency.recovery", "command_sequence": ["transfer(100)", "snapshot", "replay_events"], "oracle": "replayed_balances_hash == committed_balances_hash"},

    {"test_id": "TEST-ECON-005", "fixture_id": "econ.employment.v1", "case_id": "profession_catalog", "runner": "economy.employment.contract", "command_sequence": ["load_profession_catalog"], "oracle": "required_profession_ids == 11 && duplicate_ids == 0"},
    {"test_id": "TEST-ECON-006", "fixture_id": "econ.employment.v1", "case_id": "workplace_refs", "runner": "economy.employment.contract", "command_sequence": ["resolve_workplace_building_and_node"], "oracle": "building_ref_resolved && semantic_node_ref_resolved && economy_writes_external_state == 0"},
    {"test_id": "TEST-ECON-007", "fixture_id": "econ.employment.v1", "case_id": "player_ai_job_parity", "runner": "economy.employment.parity", "command_sequence": ["offer_same_job(ai)", "offer_same_job(player)", "evaluate_qualification"], "oracle": "ai_result == player_result && unqualified_error == 'qualification_failed'"},
    {"test_id": "TEST-ECON-008", "fixture_id": "econ.employment.v1", "case_id": "overlap_and_suspend", "runner": "economy.employment.concurrent", "command_sequence": ["concurrent(start_shift_a,start_shift_b)", "damage_workplace", "change_profession"], "oracle": "active_shift_count == 1 && contract_state == 'suspended' && history_preserved"},

    {"test_id": "TEST-ECON-009", "fixture_id": "econ.shift.v1", "case_id": "shift_boundaries", "runner": "economy.shift.contract", "command_sequence": ["credit(480,600)", "credit(600,720)", "credit(720,721)"], "oracle": "credited_minutes == 240 && outside_window_credit == 0"},
    {"test_id": "TEST-ECON-010", "fixture_id": "econ.shift.v1", "case_id": "credit_payroll_idempotency", "runner": "economy.shift.idempotency", "command_sequence": ["credit(480,600)", "credit(480,600)", "payroll(command_x)", "payroll(command_x)"], "oracle": "credited_minutes == 120 && payroll_commit_count == 1"},
    {"test_id": "TEST-ECON-011", "fixture_id": "econ.shift.v1", "case_id": "speed_credit_equivalence", "runner": "economy.shift.speed_matrix", "command_sequence": ["run_to(720,speeds=[0.5,1,2,4])", "pause_at(600)"], "oracle": "all_state_hashes_equal && paused_credit_delta == 0"},
    {"test_id": "TEST-ECON-012", "fixture_id": "econ.shift.v1", "case_id": "wage_claim_recovery", "runner": "economy.shift.recovery", "command_sequence": ["set_employer_balance(0)", "settle", "crash(after_accrual)", "recover"], "oracle": "wage_claim_amount == 180 && payroll_commit_count == 0 && accrual_preserved"},

    {"test_id": "TEST-ECON-013", "fixture_id": "econ.item.v1", "case_id": "strict_kind_schema", "runner": "economy.item.schema", "command_sequence": ["validate_all_kind_branches", "inject_additional_field"], "oracle": "valid_kind_count == 5 && additional_field_error == 'schema_additional_property'"},
    {"test_id": "TEST-ECON-014", "fixture_id": "econ.item.v1", "case_id": "current_container_unique", "runner": "economy.item.property", "command_sequence": ["reserve_unique", "attempt_second_container", "release_reservation"], "oracle": "ownership_index_count == 1 && current_container_unchanged_during_reservation"},
    {"test_id": "TEST-ECON-015", "fixture_id": "econ.item.v1", "case_id": "stack_conservation", "runner": "economy.item.property", "command_sequence": ["split(4,6)", "merge", "consume(3)"], "oracle": "quantity_after_split_merge == 10 && quantity_after_consume == 7"},
    {"test_id": "TEST-ECON-016", "fixture_id": "econ.item.v1", "case_id": "provenance_tombstone", "runner": "economy.item.recovery", "command_sequence": ["transfer", "consume", "trace_provenance"], "oracle": "source_event_resolved && tombstone_not_in_ownership_index && external_domain_writes == 0"},

    {"test_id": "TEST-ECON-017", "fixture_id": "econ.inventory.v1", "case_id": "slot_weight_cache", "runner": "economy.inventory.contract", "command_sequence": ["transfer_within_limits", "transfer_over_slot", "transfer_over_weight", "recompute_cache"], "oracle": "valid_transfer_committed && errors == ['slot_limit_exceeded','weight_limit_exceeded'] && cache_matches_recompute"},
    {"test_id": "TEST-ECON-018", "fixture_id": "econ.inventory.v1", "case_id": "container_cycle_depth", "runner": "economy.inventory.property", "command_sequence": ["nest_depth_2", "nest_depth_3", "move_parent_into_child"], "oracle": "depth_2_valid && errors == ['container_depth_exceeded','container_cycle']"},
    {"test_id": "TEST-ECON-019", "fixture_id": "econ.inventory.v1", "case_id": "inventory_access_parity", "runner": "economy.inventory.parity", "command_sequence": ["private_access(ai)", "private_access(player)", "authorized_trade_access"], "oracle": "ai_denied && player_denied && authorized_trade_allowed"},
    {"test_id": "TEST-ECON-020", "fixture_id": "econ.inventory.v1", "case_id": "reservation_lifecycle", "runner": "economy.inventory.recovery", "command_sequence": ["reserve_quantity(3)", "pause", "release", "reserve_again", "expire_at_game_time", "recover"], "oracle": "current_container_unchanged && active_total_never_exceeds_quantity && terminal_state_unique"},

    {"test_id": "TEST-ECON-021", "fixture_id": "econ.transaction.v1", "case_id": "atomic_sale", "runner": "economy.transaction.integration", "command_sequence": ["commit_sale_with_tax"], "oracle": "single_revision_delta == 1 && money_item_inventory_event_all_visible"},
    {"test_id": "TEST-ECON-022", "fixture_id": "econ.transaction.v1", "case_id": "payload_hash_idempotency", "runner": "economy.transaction.idempotency", "command_sequence": ["submit(command_x,payload_a)", "submit(command_x,payload_a)", "submit(command_x,payload_b)"], "oracle": "commit_count == 1 && third_error == 'idempotency_payload_conflict'"},
    {"test_id": "TEST-ECON-023", "fixture_id": "econ.transaction.v1", "case_id": "last_item_double_spend", "runner": "economy.transaction.concurrent", "command_sequence": ["concurrent(buy_unique_a,buy_unique_b)"], "oracle": "committed_count == 1 && ownership_index_count == 1 && loser_error == 'reservation_conflict'"},
    {"test_id": "TEST-ECON-024", "fixture_id": "econ.transaction.v1", "case_id": "crash_and_refund", "runner": "economy.transaction.recovery", "command_sequence": ["crash_each_boundary", "recover", "resend_outbox", "refund_as_new_transaction"], "oracle": "no_partial_state && original_commit_count <= 1 && refund_has_new_transaction_id"},

    {"test_id": "TEST-ECON-025", "fixture_id": "econ.shop.v1", "case_id": "opening_intervals", "runner": "economy.shop.contract", "command_sequence": ["query_at(479)", "query_at(480)", "query_at(1079)", "query_at(1080)"], "oracle": "states == ['closed','open','open','closed']"},
    {"test_id": "TEST-ECON-026", "fixture_id": "econ.shop.v1", "case_id": "shop_reservations", "runner": "economy.shop.integration", "command_sequence": ["reserve_stock_staff_node_capacity", "attempt_second_order"], "oracle": "first_reserved && second_error in ['out_of_stock','service_capacity_full']"},
    {"test_id": "TEST-ECON-027", "fixture_id": "econ.shop.v1", "case_id": "service_cancel_refund", "runner": "economy.shop.recovery", "command_sequence": ["start_service", "staff_leave", "apply_cancel_policy"], "oracle": "service_terminal && refund_amount == service_policy_refund && no_partial_delivery"},
    {"test_id": "TEST-ECON-028", "fixture_id": "econ.shop.v1", "case_id": "offer_disclosure_parity", "runner": "economy.shop.parity", "command_sequence": ["query_offer(ai)", "query_offer(player)", "inspect_disclosure"], "oracle": "ai_offer == player_offer && hidden_stock_fields == 0"},

    {"test_id": "TEST-ECON-029", "fixture_id": "econ.pricing.v1", "case_id": "q1000_golden", "runner": "economy.pricing.golden", "command_sequence": ["price(base=100,scarcity=1200,event=1000,margin=1250,discount=900)"], "oracle": "unit_price_copper_feather == 135 && supply_demand_factor_count == 1"},
    {"test_id": "TEST-ECON-030", "fixture_id": "econ.pricing.v1", "case_id": "price_bounds_and_strict_multipliers", "runner": "economy.pricing.property", "command_sequence": ["generate_valid_multiplier_edges", "generate_out_of_range_multiplier", "inject_multiplier_field(demand=1100)"], "oracle": "all_valid_prices_between_floor_ceiling && errors == ['price_multiplier_out_of_range','quote_schema_additional_property']"},
    {"test_id": "TEST-ECON-031", "fixture_id": "econ.pricing.v1", "case_id": "quote_validation", "runner": "economy.pricing.contract", "command_sequence": ["quote", "advance(11)", "change_input_hash", "set_maximum_below_quote"], "oracle": "errors == ['quote_expired','quote_input_changed','maximum_price_exceeded']"},
    {"test_id": "TEST-ECON-032", "fixture_id": "econ.pricing.v1", "case_id": "local_information", "runner": "economy.pricing.security", "command_sequence": ["quote_with_entitlement", "inspect_context"], "oracle": "discount_applied && private_relationship_fields == 0 && unobserved_shop_fields == 0"},

    {"test_id": "TEST-ECON-033", "fixture_id": "econ.market.v1", "case_id": "production_chain_dag", "runner": "economy.market.contract", "command_sequence": ["load_required_region_chains", "detect_cycle"], "oracle": "required_resource_and_product_sets_complete && cycle_count == 0"},
    {"test_id": "TEST-ECON-034", "fixture_id": "econ.market.v1", "case_id": "market_delta_idempotency", "runner": "economy.market.idempotency", "command_sequence": ["commit_sale(action_x)", "repeat_sale_delta(action_x)", "record_lost_demand(action_y)", "repeat_lost_demand(action_y)"], "oracle": "sale_delta_count == 1 && lost_demand_count == 1"},
    {"test_id": "TEST-ECON-035", "fixture_id": "econ.market.v1", "case_id": "window_speed_equivalence", "runner": "economy.market.speed_matrix", "command_sequence": ["run_1440_minutes(speeds=[0.5,1,2,4])", "pause_window"], "oracle": "bucket_hashes_all_equal && paused_window_delta == 0"},
    {"test_id": "TEST-ECON-036", "fixture_id": "econ.market.v1", "case_id": "scarcity_policy_golden", "runner": "economy.market.golden", "command_sequence": ["evaluate_scarcity_golden_vectors", "run_hysteresis_signals([shortage,shortage,recovery,recovery])"], "oracle": "q1000_results == [1000,1800,700,1496] && states == ['watch','active','recovering','normal']"},

    {"test_id": "TEST-ECON-037", "fixture_id": "econ.crafting.v1", "case_id": "recipe_schema_dag", "runner": "economy.crafting.contract", "command_sequence": ["validate_recipe", "inject_recipe_cycle"], "oracle": "valid_recipe_accepted && unapproved_cycle_error == 'production_chain_cycle'"},
    {"test_id": "TEST-ECON-038", "fixture_id": "econ.crafting.v1", "case_id": "craft_reservation_set", "runner": "economy.crafting.concurrent", "command_sequence": ["reserve_inputs_tool_station_output", "concurrent_second_craft"], "oracle": "first_reserved && second_error == 'reservation_conflict'"},
    {"test_id": "TEST-ECON-039", "fixture_id": "econ.crafting.v1", "case_id": "craft_outcomes", "runner": "economy.crafting.integration", "command_sequence": ["complete_success", "complete_failure(2500bps)", "cancel"], "oracle": "success_output == 1 && failure_consumed_iron == 0 && cancel_releases_unconsumed"},
    {"test_id": "TEST-ECON-040", "fixture_id": "econ.crafting.v1", "case_id": "craft_crash_replay", "runner": "economy.crafting.recovery", "command_sequence": ["crash(before_commit)", "recover", "complete", "resend_completion"], "oracle": "output_create_count == 1 && seed_position_unchanged_on_replay"},

    {"test_id": "TEST-ECON-041", "fixture_id": "econ.property_budget.v1", "case_id": "deed_subject_uniqueness", "runner": "economy.property.property", "command_sequence": ["issue_second_active_deed_same_subject"], "oracle": "error == 'deed_conflict' && active_deed_count == 1"},
    {"test_id": "TEST-ECON-042", "fixture_id": "econ.property_budget.v1", "case_id": "deed_transfer_authority", "runner": "economy.property.security", "command_sequence": ["transfer_with_consent", "mayor_confiscate_without_order"], "oracle": "first_committed && second_error == 'transfer_consent_missing'"},
    {"test_id": "TEST-ECON-043", "fixture_id": "econ.property_budget.v1", "case_id": "appropriation_encumbrance_concurrency", "runner": "economy.budget.concurrent", "command_sequence": ["concurrent(encumber_2000,encumber_2000)", "commit_winner_with_budget_binding"], "oracle": "encumbrance_commit_count == 1 && public_debit_binding_count == 1 && spent_plus_active <= authorized"},
    {"test_id": "TEST-ECON-044", "fixture_id": "econ.property_budget.v1", "case_id": "budget_event_failure_recovery", "runner": "economy.budget.recovery", "command_sequence": ["encumber(1800)", "event_stage_failure", "release", "crash_each_boundary", "recover"], "oracle": "active_encumbrance_returns_to_1800_initial && no_public_debit && orphan_encumbrance_count == 0 && external_building_writes == 0"}
  ]
}
```

Registry Contract：`test_id` 必须恰好覆盖 `TEST-ECON-001..044` 且唯一；每条的 `fixture_id` 必须解析、`case_id/runner/oracle` 非空、`command_sequence` 至少一项。runner 必须把 oracle 作为断言执行，不能只打印文本。`TEST-ECON-045..048` 则审计此 registry 与全局 simulation/recovery envelope。

建议实现入口：

```powershell
python -m pytest tests/economy -q
python -m app.tools.run_simulation --fixture economy_baseline_v1 --game-days 1,7,30 --speeds 0.5,1,2,4
python -m app.tools.audit_economy --world-fixture economy_baseline_v1 --format json
```

## 6. 正常流程

1. 解析 test registry，验证 44 个 Test ID、fixture reference、runner 和 oracle 闭合。
2. 使用 FakeModelProvider 和固定 Seed 创建 10 Resident、三个 Region 生产链与初始账本，并按 registry 执行工资、Shop sale、税费、赠与、Craft、退款、产权转移和公共工程场景。
3. 每次提交运行增量 invariant；每个模拟终点运行全量 Conservation Snapshot。
4. 对每个 Crash Boundary 复制测试数据库、注入中断、恢复并重放。
5. 比较不同速度 state hash、Ledger/Event projection 与 source/sink delta。
6. 输出 JSON 报告，任一 assertion false 即进程 exit non-zero。

## 7. 边界情况

- 并发夹具同时购买最后一个 unique、最后一份 stack 和消费同一余额。
- 工资结算与 Shop purchase 同时竞争 worker 账户余额。
- GameTime 在 Reservation 过期前一分钟暂停，恢复后只按 GameTime 到期。
- Shortage 在 bucket 边界产生/恢复，价格必须留在 floor/ceiling。
- Crash 后重发 command、Outbox 与 Craft completion，结果必须 exactly-once。

## 8. 错误与降级

测试工具发现不变量失败时保留最小失败 Seed、Command 序列、Revision、entity IDs 与脱敏 reason code，并 exit 1；不能自动修复后继续计为通过。性能预算超时与断言失败分开报告，真实模型不可用不影响确定性 suite。

## 9. 安全与性能

测试限定明确 fixture 和 ECON 数据，不扫描无关目录。每 1000 次 Transaction 做一次全量 audit，其余增量；30 日模拟记录 p50/p95/p99 提交延迟、最大 active Reservation、账本增长与 state hash，诊断不含 Secret/Prompt。

## 10. 验收标准

- `TEST-ECON-001..044` 恰好 44 条 machine-readable fixture/case/runner/oracle 映射，`TEST-ECON-045..048` 覆盖 registry、恢复、速度与 30 日 envelope。
- source/sink allowlist 之外货币与 Item 总量 delta 为 0。
- 全部 Crash Boundary 恢复到旧 Revision 或完整新 Revision，不存在半事务。
- 四种非零倍率 state hash 相同，`0×` 观察期 state hash 不变。
- 30 日内价格、库存、欠薪、Shortage、Reservation 与数据增长均落入 fixture 的有界 envelope。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-ECON-045` | 每事务守恒、不变量与反例注入 |
| `TEST-ECON-046` | Snapshot/Event/ledger/index/cache/Reservation 恢复 audit |
| `TEST-ECON-047` | `0×..4×` speed equivalence 与暂停 |
| `TEST-ECON-048` | 1/7/30 日 balance envelope、性能与增长上限 |

## 12. 关联文档

- `DOC-FOUNDATION-005`：全局不变量与 Recovery Audit
- `DOC-ECON-001..011`：本套件覆盖的 canonical 经济规格
- `DOC-BACKEND-010`：跨域事务与幂等下游实现
- `DOC-RELEASE-011`：项目级测试策略
