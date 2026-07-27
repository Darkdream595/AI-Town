"""TEST-EVENT-004..006：触发器求值、预算/冷却/Calm Window、裁决与互斥（DOC-EVENT-002）"""

import pytest

from src.events import TemplateError, TriggerSpec
from src.events.rng import trigger_stream_name
from src.events.triggers import evaluate_condition, scopes_intersect
from event_helpers import activate_event, make_world, occ
from src.events.fixtures import SCENE_TOWN


def _projection(**fields):
    return {"scene_id": SCENE_TOWN, "game_time": 0, **fields}


def _eval(world, key, game_time, projection, source="time"):
    return world.on_occurrence(occ(
        "trigger_eval", key, game_time, projection=projection, source=source,
    ))


# -- TEST-EVENT-004：受限谓词与确定性抽样 --------------------------------------


def test_condition_predicates():
    projection = {"public": {"harvest_stock": 120, "mood": "high", "tags": ["a", "b"]}}
    ok, _ = evaluate_condition(
        {"all_of": [["projection_at_least", "public.harvest_stock", 100]]}, projection)
    assert ok
    ok, _ = evaluate_condition(
        {"all_of": [["projection_at_most", "public.harvest_stock", 100]]}, projection)
    assert not ok
    ok, _ = evaluate_condition(
        {"all_of": [["projection_equals", "public.mood", "high"]]}, projection)
    assert ok
    ok, _ = evaluate_condition(
        {"all_of": [["projection_in", "public.mood", ["low", "high"]]]}, projection)
    assert ok


def test_condition_missing_field_is_false_with_warning():
    ok, warnings = evaluate_condition(
        {"all_of": [["projection_at_least", "public.nonexistent", 1]]},
        {"public": {}},
    )
    assert not ok
    assert warnings and "nonexistent" in warnings[0]


def test_condition_schema_rejected_at_registration():
    with pytest.raises(TemplateError) as exc:
        TriggerSpec(
            trigger_id="trigger.bad", event_template_id="event.minor.rumor",
            allowed_sources=frozenset({"time"}), severity="minor", trigger_priority=0,
            condition={"any_of": []}, activation_chance_0_to_1=1.0,
            cooldown_game_minutes=0,
        )
    assert exc.value.code == "condition_schema_invalid"
    with pytest.raises(TemplateError):
        TriggerSpec(
            trigger_id="trigger.bad2", event_template_id="event.minor.rumor",
            allowed_sources=frozenset({"time"}), severity="minor", trigger_priority=0,
            condition={"all_of": [["drop_table", "public.x", 1]]},
            activation_chance_0_to_1=1.0, cooldown_game_minutes=0,
        )


def test_trigger_fires_and_instantiates():
    world, _fakes = make_world()
    result = _eval(world, "te-1", 0, _projection(public={"harvest_stock": 150}))
    fired = result["result"]["fired"]
    assert [f["trigger_id"] for f in fired] == ["trigger.harvest_season"]
    event = world.engine.get(fired[0]["world_event_id"])
    assert event.state == "active"
    assert event.source == "time"
    assert event.source_evidence_id == "trigger.harvest_season"


def test_trigger_condition_unmet_no_fire():
    world, _fakes = make_world()
    result = _eval(world, "te-2", 0, _projection(public={"harvest_stock": 5}))
    assert result["result"]["fired"] == []


def test_activation_chance_zero_never_fires():
    world, _fakes = make_world()
    world.trigger_registry.register(TriggerSpec(
        trigger_id="trigger.never", event_template_id="event.minor.rumor",
        allowed_sources=frozenset({"time"}), severity="minor", trigger_priority=9,
        condition={"all_of": []}, activation_chance_0_to_1=0.0,
        cooldown_game_minutes=0,
    ))
    result = _eval(world, "te-3", 0, _projection())
    assert result["result"]["fired"] == []
    assert any(r["code"] == "chance_missed" for r in result["result"]["rejected"])


def test_sampling_deterministic_across_worlds():
    world_a, _ = make_world()
    world_b, _ = make_world()
    projection = _projection(public={"tavern_visits": 20})
    result_a = _eval(world_a, "te-4", 0, projection)
    result_b = _eval(world_b, "te-4", 0, projection)
    assert result_a["result"]["fired"] == result_b["result"]["fired"]
    assert result_a["result"]["rejected"] == result_b["result"]["rejected"]


def test_stream_naming():
    assert trigger_stream_name("trigger.drought_fire") == "event.trigger.drought_fire"


def test_source_not_permitted_rejection():
    world, _fakes = make_world()
    # harvest_season 只允许 time；以 state 评估被拒
    result = _eval(world, "te-5", 0, _projection(public={"harvest_stock": 150}),
                   source="state")
    assert result["result"]["fired"] == []
    assert any(r["code"] == "source_not_permitted"
               for r in result["result"]["rejected"])


# -- TEST-EVENT-005：预算上限、crisis 并发、冷却、Calm Window --------------------


def test_budget_exceeded_rejection():
    world, _fakes = make_world()
    # 先激活 12 权重（crisis 8 + major 4），再触发 minor 也被预算拒绝
    activate_event(world, "b1", template_id="event.crisis.dragon",
                   source="admin", admin=True)
    activate_event(world, "b2", template_id="event.disaster.forest_fire",
                   source="environment", admin=False, parameters={"origin": "x"},
                   scope={"scene_id": "region.twilight_whisper_forest"})
    result = _eval(world, "te-6", 0, _projection(public={"harvest_stock": 150}))
    assert result["result"]["fired"] == []
    assert any(r["code"] == "budget_exceeded" for r in result["result"]["rejected"])


def test_crisis_concurrency_cap():
    world, _fakes = make_world()
    from src.events.templates import EventTemplate
    world.event_templates.register(EventTemplate(
        event_template_id="event.test.crisis2", name="测试危机",
        default_severity="crisis", allowed_sources=frozenset({"admin"}),
        max_concurrent_instances=2, dedup_window_game_minutes=0,
    ))
    activate_event(world, "c1", template_id="event.test.crisis2",
                   source="admin", admin=True, game_time=0)
    from src.events import EventError
    with pytest.raises(EventError) as exc:
        activate_event(world, "c2", template_id="event.test.crisis2",
                       source="admin", admin=True, game_time=1)
    assert exc.value.code == "budget_exceeded"


def test_disaster_cooldown_minimum():
    world, _fakes = make_world()
    from src.events.templates import EventTemplate
    world.event_templates.register(EventTemplate(
        event_template_id="event.test.disaster", name="测试灾害",
        default_severity="major", allowed_sources=frozenset({"admin", "environment"}),
        max_concurrent_instances=4, dedup_window_game_minutes=10,
        is_disaster=True,
    ))
    event = activate_event(world, "cd-1", template_id="event.test.disaster",
                           source="environment", admin=False, game_time=0)
    world.engine.transition(event.world_event_id, "resolved", 50,
                            expected_version=event.version)
    event2 = world.engine.instantiate(
        command_id="cd-2", event_template_id="event.test.disaster",
        source="admin", source_evidence_id=None,
        scope={"scene_id": SCENE_TOWN}, parameters={}, game_time=100, admin=True,
    )
    from src.events import EventError
    with pytest.raises(EventError) as exc:
        world.engine.transition(event2.world_event_id, "active", 100,
                                expected_version=event2.version, admin=False)
    assert exc.value.code == "cooldown_active"


def test_admin_bypasses_cooldown_but_consumes_budget():
    world, _fakes = make_world()
    from src.events.templates import EventTemplate
    world.event_templates.register(EventTemplate(
        event_template_id="event.test.disaster", name="测试灾害",
        default_severity="major", allowed_sources=frozenset({"admin", "environment"}),
        max_concurrent_instances=4, dedup_window_game_minutes=10,
        is_disaster=True,
    ))
    first = activate_event(world, "cd-3", template_id="event.test.disaster",
                           source="environment", admin=False, game_time=0)
    world.engine.transition(first.world_event_id, "resolved", 50,
                            expected_version=first.version)
    event = world.engine.instantiate(
        command_id="cd-4", event_template_id="event.test.disaster",
        source="admin", source_evidence_id=None,
        scope={"scene_id": "region.crown_creek_town"},
        parameters={}, game_time=100, admin=True,
    )
    # 冷却剩余 4220，admin 越过冷却直接激活
    world.engine.transition(event.world_event_id, "active", 100,
                            expected_version=event.version, admin=True)
    assert world.engine.get(event.world_event_id).state == "active"
    # 预算确实被占用（两个 major 各 4；resolved 未进 aftermath 仍占）
    assert world.budget.current_pressure(100) == 8


def test_budget_refund_linear_after_aftermath():
    world, _fakes = make_world()
    event = activate_event(world, "rf-1", template_id="event.weird.lights",
                           source="environment", admin=False, game_time=0)
    assert world.budget.current_pressure(0) == 2
    world.engine.transition(event.world_event_id, "resolved", 100,
                            expected_version=event.version)
    current = world.engine.get(event.world_event_id)
    world.engine.transition(current.world_event_id, "aftermath", 200,
                            expected_version=current.version)
    assert world.budget.current_pressure(200) == 2     # aftermath 起点全额
    assert world.budget.current_pressure(920) == 1     # 720/1440 → 线性减半
    assert world.budget.current_pressure(1640) == 0    # 1440 后返还完毕


def test_calm_window_statistics():
    world, _fakes = make_world()
    activate_event(world, "cw-1", template_id="event.weird.lights",
                   source="environment", admin=False, game_time=2000)
    activate_event(world, "cw-2", template_id="event.weird.lights",
                   source="environment", admin=False,
                   scope={"scene_id": "region.twilight_whisper_forest"},
                   game_time=6000)
    windows = world.budget.calm_windows(0, 10080)
    # 激活间隔 ≥1440 的每段都是 Calm Window（含首尾边界）
    assert windows == [(0, 2000), (2000, 6000), (6000, 10080)]
    assert world.budget.calm_window_ok(0, 10080)


# -- TEST-EVENT-006：裁决排序、互斥、幂等 ----------------------------------------


def test_adjudication_order_severity_then_priority_then_id():
    world, _fakes = make_world()
    for trigger_id, severity, priority in (
        ("trigger.adj.minor", "minor", 99),
        ("trigger.adj.major.b", "major", 1),
        ("trigger.adj.major.a", "major", 1),
        ("trigger.adj.major.c", "major", 5),
    ):
        world.event_templates.register(type(world.event_templates.get(
            "event.minor.rumor"))(
            event_template_id=f"event.test.{trigger_id.split('.')[-1]}",
            name=trigger_id, default_severity=severity,
            allowed_sources=frozenset({"time", "state"}),
            max_concurrent_instances=4, dedup_window_game_minutes=0,
        ))
        world.trigger_registry.register(TriggerSpec(
            trigger_id=trigger_id,
            event_template_id=f"event.test.{trigger_id.split('.')[-1]}",
            allowed_sources=frozenset({"time"}), severity=severity,
            trigger_priority=priority, condition={"all_of": []},
            activation_chance_0_to_1=1.0, cooldown_game_minutes=0,
        ))
    result = _eval(world, "te-7", 0, _projection())
    fired_order = [f["trigger_id"] for f in result["result"]["fired"]]
    # major(4) 先于 minor(1)；同 severity：priority 5 先，同 priority 按 trigger_id 字典序
    assert fired_order == [
        "trigger.adj.major.c", "trigger.adj.major.a", "trigger.adj.major.b",
    ] or fired_order == [
        "trigger.adj.major.c", "trigger.adj.major.a", "trigger.adj.major.b",
        "trigger.adj.minor",
    ]
    # minor 必在 major 之后（预算可能挤掉 minor：3×4=12 已满）
    if "trigger.adj.minor" in fired_order:
        assert fired_order.index("trigger.adj.minor") == 3


def test_exclusion_conflict_between_candidates():
    world, _fakes = make_world()
    from src.events.templates import EventTemplate
    # 非灾害模板隔离出纯互斥约束（灾害 4320 冷却下限会先触达）
    world.event_templates.register(EventTemplate(
        event_template_id="event.test.excl", name="互斥测试",
        default_severity="major", allowed_sources=frozenset({"time", "state"}),
        max_concurrent_instances=8, dedup_window_game_minutes=0,
    ))
    world.trigger_registry.register(TriggerSpec(
        trigger_id="trigger.excl.a", event_template_id="event.test.excl",
        allowed_sources=frozenset({"time", "state"}), severity="major", trigger_priority=5,
        condition={"all_of": []}, activation_chance_0_to_1=1.0,
        cooldown_game_minutes=0, exclusion_tags=frozenset({"test_conflict"}),
    ))
    world.trigger_registry.register(TriggerSpec(
        trigger_id="trigger.excl.b", event_template_id="event.test.excl",
        allowed_sources=frozenset({"time", "state"}), severity="major", trigger_priority=4,
        condition={"all_of": []}, activation_chance_0_to_1=1.0,
        cooldown_game_minutes=0, exclusion_tags=frozenset({"test_conflict"}),
    ))
    result = _eval(world, "te-8", 0, _projection(), source="state")
    fired = result["result"]["fired"]
    assert len(fired) == 1
    assert fired[0]["trigger_id"] == "trigger.excl.a"
    assert any(r["code"] == "exclusion_conflict" and r["trigger_id"] == "trigger.excl.b"
               for r in result["result"]["rejected"])


def test_exclusion_conflict_against_active_event():
    world, _fakes = make_world()
    # drought_fire 激活后带 disaster 标签；冷却过后同 scope 的新 disaster 触发仍被互斥拒绝
    activate_event(world, "ex-1", template_id="event.disaster.forest_fire",
                   source="environment", admin=False, parameters={"origin": "x"},
                   game_time=0)
    result = _eval(world, "te-9", 5000,
                   _projection(public={"drought_days": 5}))
    assert result["result"]["fired"] == []
    assert any(r["code"] == "exclusion_conflict"
               for r in result["result"]["rejected"])


def test_scopes_intersect_helper():
    a = {"scene_id": "s1", "parcel_id": "p1"}
    assert scopes_intersect(a, {"scene_id": "s1", "parcel_id": "p1"})
    assert scopes_intersect(a, {"scene_id": "s1"})
    assert not scopes_intersect(a, {"scene_id": "s2"})
    assert not scopes_intersect(a, {"scene_id": "s1", "parcel_id": "p2"})


def test_evaluation_idempotent_by_occurrence_key():
    world, _fakes = make_world()
    projection = _projection(public={"harvest_stock": 150})
    first = _eval(world, "te-10", 0, projection)
    second = _eval(world, "te-10", 0, projection)
    assert first["status"] == "processed"
    assert second["status"] == "replayed"
    # 不产生第二个事件实例
    festivals = [e for e in world.engine.all()
                 if e.event_template_id == "event.festival.harvest"]
    assert len(festivals) == 1
