"""TEST-EVENT-034..038：恢复契约、三层防重探针、fixture 确定性、Simulation Gate、admin 边界（DOC-EVENT-012）"""

import json

import pytest

from src.events import EventError, EventTemplate
from event_helpers import (
    build_cottage_full,
    make_world,
    occ,
    place_cottage,
    work_all_phases,
)
from src.events.fixtures import SCENE_FOREST, SCENE_TOWN


def _snapshot(world, fakes):
    return world.export_state(), fakes.map_port.snapshot_state()


def _restore(seed, state, map_snapshot):
    world2, fakes2 = make_world()
    fakes2.map_port.restore_state(map_snapshot)
    world2.import_state(state)
    return world2, fakes2


# -- TEST-EVENT-034：Recovery Convergence（施工/事件/Quest 中间态） ---------------------


def test_recovery_mid_construction():
    world, fakes = make_world()
    building = place_cottage(world, fakes)
    world.construction.deliver_materials("rc-m", building.building_id,
                                         {"item.stone": 10, "item.timber": 20,
                                          "item.nail": 5}, 0)
    building = world.buildings.get(building.building_id)
    world.construction.submit_work_session(
        "rc-w", building.building_id, "architect", 30, 10_000, 0,
        expected_phase="planning", expected_version=building.version)
    state, map_snapshot = _snapshot(world, fakes)
    world2, _ = _restore("unused", state, map_snapshot)
    assert world2.export_state() == state
    site = world2.construction.site_of(building.building_id)
    assert site.labor_progress["planning"] == 30
    assert site.materials_escrow["item.stone"] == 10
    # 恢复后继续施工：完整链路可用
    work_all_phases(world2, building.building_id, command_prefix="rc2", game_time=10)
    assert world2.buildings.get(building.building_id).physical_state == "intact"
    assert world2.audit_invariants(20)["ok"]


def test_recovery_event_aftermath_pending():
    world, fakes = make_world()
    from event_helpers import activate_event, terminal_to_aftermath
    event = activate_event(world, "rc-e1", template_id="event.disaster.forest_fire",
                           source="environment", admin=False,
                           parameters={"origin": "x"},
                           scope={"scene_id": SCENE_FOREST})
    event = terminal_to_aftermath(world, event)
    state, map_snapshot = _snapshot(world, fakes)
    world2, _ = _restore("unused", state, map_snapshot)
    assert world2.export_state() == state
    # pending Aftermath Task 与崩溃前一致，仍阻止归档
    restored = world2.engine.get(event.world_event_id)
    assert restored.state == "aftermath"
    assert world2.aftermath.pending_count(event.world_event_id) == 2
    with pytest.raises(EventError):
        world2.engine.transition(event.world_event_id, "archived", 99,
                                 expected_version=restored.version)


def test_recovery_quest_progress():
    world, fakes = make_world()
    quest = world.quests.create_offer("rc-q1", "quest.deliver.supplies",
                                      {"courier": ["resident.hero"]}, 0)
    world.quests.respond("rc-q2", quest.quest_id, True, 1,
                         expected_version=quest.version)
    current = world.quests.get(quest.quest_id)
    world.quests.begin("rc-q3", quest.quest_id, 2,
                       expected_version=current.version)
    world.quests.submit_domain_event(
        {"event_id": "ev-rc", "event_type": "item.delivered",
         "payload": {"resident_id": "resident.hero",
                     "item_template_id": "item.supplies",
                     "to": "resident.mayor"}}, 3)
    state, map_snapshot = _snapshot(world, fakes)
    world2, _ = _restore("unused", state, map_snapshot)
    assert world2.export_state() == state
    progress = world2.quests.get(quest.quest_id).objective_progress["deliver"]
    assert progress.count == 1
    assert progress.matched_event_ids == ["ev-rc"]


def test_recovery_weather_and_rubble():
    world, fakes = make_world()
    for step in range(5):
        world.on_occurrence(occ("weather_eval", f"rc-w{step}", (step + 1) * 60,
                                payload={"region_id": SCENE_TOWN,
                                         "season": "summer"}))
    building = build_cottage_full(world, fakes)
    world.buildings.apply_damage("rc-d1", building.building_id, "fire", 85, 400)
    state, map_snapshot = _snapshot(world, fakes)
    world2, fakes2 = _restore("unused", state, map_snapshot)
    assert world2.export_state() == state
    # Diff Hash 恢复审计：重放 == 地图现状
    assert world2.audit_invariants(500)["ok"]
    base = fakes2.map_port.base_layers(SCENE_TOWN)
    replayed = world2.diff_log.replay(SCENE_TOWN, base, None)
    assert world2.diff_log.compute_diff_hash(replayed) == \
        fakes2.map_port.current_layers_hash(SCENE_TOWN)


# -- TEST-EVENT-035：三层防重与逐层失效探针 ----------------------------------------------


def _layer_probe_kwargs():
    return dict(
        event_template_id="event.festival.harvest", source="admin",
        source_evidence_id=None, scope={"scene_id": SCENE_TOWN},
        parameters={}, game_time=0, admin=True, occurrence_key="layer-occ-1",
    )


def test_three_layers_all_present():
    world, _fakes = make_world()
    world.engine.instantiate(command_id="layer-c1", **_layer_probe_kwargs())
    # 层 1：occurrence key
    with pytest.raises(EventError) as exc:
        world.engine.instantiate(command_id="layer-c2", **_layer_probe_kwargs())
    assert exc.value.code == "occurrence_replayed"
    # 层 2：命令幂等（不同 occurrence、同 command）
    kwargs = _layer_probe_kwargs()
    kwargs["occurrence_key"] = None
    same = world.engine.instantiate(command_id="layer-c1", **kwargs)
    assert same.world_event_id == world.engine.all()[0].world_event_id
    # 层 3：语义窗口
    kwargs2 = _layer_probe_kwargs()
    kwargs2["occurrence_key"] = "layer-occ-2"
    with pytest.raises(EventError) as exc:
        world.engine.instantiate(command_id="layer-c3", **kwargs2)
    assert exc.value.code == "duplicate_semantic_window"


def test_layer1_disabled_probe_fails():
    world, _fakes = make_world()
    world.engine.instantiate(command_id="p1", **_layer_probe_kwargs())
    world.engine._occurrences.clear()  # 人为禁用层 1
    with pytest.raises(EventError) as exc:
        world.engine.instantiate(command_id="p2", **_layer_probe_kwargs())
    # 层 1 缺失时由层 3 兜底拦截 → 证明层 1 独立承载 occurrence 防重
    assert exc.value.code == "duplicate_semantic_window"


def test_layer2_disabled_probe_fails():
    world, _fakes = make_world()
    kwargs = _layer_probe_kwargs()
    kwargs["occurrence_key"] = None
    world.engine.instantiate(command_id="p3", **kwargs)
    world.engine._command_results.clear()  # 人为禁用层 2
    kwargs["occurrence_key"] = "p3-occ-2"
    with pytest.raises(EventError) as exc:
        world.engine.instantiate(command_id="p3", **kwargs)
    assert exc.value.code == "duplicate_semantic_window"


def test_layer3_disabled_probe_fails():
    world, _fakes = make_world()
    world.event_templates.register(EventTemplate(
        event_template_id="event.test.nodedup", name="无窗口",
        default_severity="minor", allowed_sources=frozenset({"admin"}),
        max_concurrent_instances=99, dedup_window_game_minutes=0,
    ))
    kwargs = dict(_layer_probe_kwargs(),
                  event_template_id="event.test.nodedup")
    first = world.engine.instantiate(command_id="p4", **kwargs)
    kwargs["occurrence_key"] = "layer-occ-3"
    # 层 3 缺失（窗口=0）：同 (template, scope) 第二个实例被创建
    second = world.engine.instantiate(command_id="p5", **kwargs)
    assert first.world_event_id != second.world_event_id


# -- TEST-EVENT-036：fixture 确定性与 Oracle 纪律 ----------------------------------------


def _determinism_script(world):
    world.on_occurrence(occ(
        "trigger_eval", "det-1", 0,
        projection={"scene_id": SCENE_TOWN, "game_time": 0,
                    "public": {"harvest_stock": 150, "tavern_visits": 20}},
    ))
    world.on_occurrence(occ(
        "weather_eval", "det-2", 60,
        payload={"region_id": SCENE_TOWN, "season": "spring"},
    ))
    world.director_whitelist.allow("event.festival.harvest")
    world.on_occurrence(occ(
        "director_review", "det-3", 360,
        projection={"scene_id": SCENE_TOWN, "game_time": 360,
                    "public": {"harvest_stock": 150}},
    ))


def test_fixture_determinism_same_seed_same_result():
    world_a, fakes_a = make_world()
    fakes_a.director_model.push(None)
    world_b, fakes_b = make_world()
    fakes_b.director_model.push(None)
    _determinism_script(world_a)
    _determinism_script(world_b)
    assert world_a.event_log.timeline() == world_b.event_log.timeline()
    canonical_a = json.dumps(world_a.export_state(), sort_keys=True)
    canonical_b = json.dumps(world_b.export_state(), sort_keys=True)
    assert canonical_a == canonical_b


def test_oracle_discipline_fake_provider_only():
    world, fakes = make_world()
    fakes.director_model.push({
        "proposal_kind": "world_event",
        "event_template_id": "event.festival.harvest",
        "parameters": {}, "narrative_reason": "丰收庆典正当其时",
    })
    _determinism_script(world)
    # 模型调用全部经 FakeProvider；投影只含 public 白名单字段
    assert len(fakes.director_model.calls) == 1
    projection = fakes.director_model.calls[0]["projection"]
    assert set(projection) <= {"scene_id", "game_time", "public"}


# -- TEST-EVENT-037：Simulation Gate 1/7/30 ----------------------------------------------


def _simulation_run(days: int):
    world, fakes = make_world()
    building = place_cottage(world, fakes, command_id="sim-place", game_time=0)
    world.construction.deliver_materials("sim-mats", building.building_id,
                                         {"item.stone": 10, "item.timber": 20,
                                          "item.nail": 5}, 0)
    work_all_phases(world, building.building_id, command_prefix="sim-ws",
                    game_time=0)
    unexpected_rejections = []
    total_minutes = days * 1440
    for step in range(1, total_minutes // 30 + 1):
        game_time = step * 30
        world.test_clock["now"] = game_time
        for region_id, season in ((SCENE_TOWN, "summer"), (SCENE_FOREST, "summer")):
            world.on_occurrence(occ(
                "weather_eval", f"sim-w-{region_id}-{step}", game_time,
                payload={"region_id": region_id, "season": season}))
        if game_time % 360 == 0:
            result = world.on_occurrence(occ(
                "trigger_eval", f"sim-t-{step}", game_time,
                projection={"scene_id": SCENE_TOWN, "game_time": game_time,
                            "public": {"harvest_stock": 150}},
            ))
            # 预期拒绝（含 cooldown_active 执法拒绝）不是失败；
            # 只统计非预期错误码（DOC-EVENT-012 §7）
            for rejection in result["result"]["rejected"]:
                if rejection["code"] not in (
                    "budget_exceeded", "duplicate_semantic_window",
                    "max_concurrent_exceeded", "source_not_permitted",
                    "exclusion_conflict", "chance_missed", "cooldown_active",
                ):
                    unexpected_rejections.append(rejection)
            world.on_occurrence(occ(
                "director_review", f"sim-d-{step}", game_time,
                projection={"scene_id": SCENE_TOWN, "game_time": game_time,
                            "public": {"harvest_stock": 150}},
            ))
        if game_time % 1440 == 0:
            world.on_occurrence(occ("decay_eval", f"sim-decay-{step}", game_time))
            world.on_occurrence(occ(
                "construction_stall_check", f"sim-stall-{step}", game_time))
            # 每日收束：active → resolved → aftermath → archived（镇长节奏）
            for event in list(world.engine.active_events()):
                current = event
                world.engine.transition(current.world_event_id, "resolved",
                                        game_time,
                                        expected_version=current.version)
                current = world.engine.get(current.world_event_id)
                world.engine.transition(current.world_event_id, "aftermath",
                                        game_time,
                                        expected_version=current.version)
                for task_id in current.aftermath_task_ids:
                    task = world.aftermath.get(task_id)
                    world.aftermath.cancel(task_id, game_time,
                                           expected_version=task.version,
                                           mayor=True)
                current = world.engine.get(current.world_event_id)
                world.engine.transition(current.world_event_id, "archived",
                                        game_time,
                                        expected_version=current.version)
        # 持续断言：预算权重上限、crisis 并发、active 上限
        audit = world.audit_invariants(game_time)
        assert audit["active_weight"] <= 12, game_time
        assert world.budget.active_crisis_count() <= 1, game_time
        assert audit["active_events"] <= 16, game_time
    # 结束全量 invariant
    final_audit = world.audit_invariants(total_minutes)
    assert final_audit["ok"], final_audit["violations"]
    # Calm Window：每 7 日 ≥1
    assert world.budget.calm_window_ok(0, total_minutes)
    # 冷却零违规：同 (template, scene) 激活间隔必须 ≥ 冷却（触发器冷却/灾害下限）
    active_times: dict = {}
    for entry in world.event_log.entries():
        if entry["event_type"] != "world_event.active":
            continue
        event = world.engine.get(entry["payload"]["world_event_id"])
        key = (event.event_template_id, event.scope["scene_id"])
        active_times.setdefault(key, []).append(entry["game_time"])
    for (template_id, scene_id), times in active_times.items():
        template = world.event_templates.get(template_id)
        cooldown = world.budget.effective_cooldown(0, template.is_disaster)
        for trigger in world.trigger_registry.all():
            if trigger.event_template_id == template_id:
                cooldown = max(cooldown, world.budget.effective_cooldown(
                    trigger.cooldown_game_minutes, template.is_disaster))
        times.sort()
        for earlier, later in zip(times, times[1:]):
            gap = later - earlier
            assert gap >= cooldown, f"cooldown violated: {template_id}@{scene_id} gap {gap}"
    assert unexpected_rejections == []
    # 建筑四件套原子性抽样：patch 数 == diff entry 数
    for scene_id in fakes.map_port.scene_ids():
        scene_patches = [p for p in fakes.map_port.patches
                         if p["scene_id"] == scene_id]
        assert len(scene_patches) == len(world.diff_log.entries(scene_id))
    return world


def test_simulation_gate_1_day():
    _simulation_run(1)


def test_simulation_gate_7_days():
    _simulation_run(7)


def test_simulation_gate_30_days():
    _simulation_run(30)


# -- TEST-EVENT-038：admin 使用边界与标记审计 ----------------------------------------------


def test_admin_only_for_setup_and_marked():
    world, _fakes = make_world()
    # admin 无标记被拒
    with pytest.raises(EventError) as exc:
        world.engine.instantiate(
            command_id="adm-1", event_template_id="event.festival.harvest",
            source="admin", source_evidence_id=None,
            scope={"scene_id": SCENE_TOWN}, parameters={}, game_time=0,
            admin=False)
    assert exc.value.code == "source_not_permitted"
    # admin 构造前置状态：显式标记并纳入日志基线
    event = world.engine.instantiate(
        command_id="adm-2", event_template_id="event.festival.harvest",
        source="admin", source_evidence_id=None,
        scope={"scene_id": SCENE_TOWN}, parameters={}, game_time=0, admin=True)
    setup_log = next(e for e in world.event_log.entries()
                     if e["event_type"] == "world_event.instantiated")
    assert setup_log["payload"]["admin_marked"] is True
    assert event.admin_marked is True
    # 非 admin 来源不得携带 admin 标记
    normal = world.engine.instantiate(
        command_id="adm-3", event_template_id="event.minor.rumor",
        source="state", source_evidence_id=None,
        scope={"scene_id": SCENE_TOWN}, parameters={}, game_time=0)
    assert normal.admin_marked is False
