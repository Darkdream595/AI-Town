"""TEST-EVENT-001..003：WorldEvent 引擎生命周期（DOC-EVENT-001）"""

import pytest

from src.events import EventError
from src.events.constants import ACTIVE_EVENT_CAP, ACTIVE_WEIGHT_CAP
from event_helpers import activate_event, make_world, occ, terminal_to_aftermath
from src.events.fixtures import SCENE_TOWN


# -- TEST-EVENT-001：聚合 schema 与实例化 ------------------------------------


def test_world_event_schema_fields():
    world, _fakes = make_world()
    event = world.engine.instantiate(
        command_id="c1", event_template_id="event.festival.harvest",
        source="admin", source_evidence_id="evidence-1",
        scope={"scene_id": SCENE_TOWN}, parameters={}, game_time=5, admin=True,
    )
    data = event.to_dict()
    for field in (
        "schema_version", "world_event_id", "event_template_id", "source",
        "source_evidence_id", "severity", "state", "scope", "parameters",
        "scheduled_start", "deadline", "aftermath_task_ids", "version",
    ):
        assert field in data, field
    assert event.state == "candidate"
    assert event.version == 0


def test_instantiate_with_scheduled_start_enters_scheduled():
    world, _fakes = make_world()
    event = world.engine.instantiate(
        command_id="c2", event_template_id="event.festival.harvest",
        source="admin", source_evidence_id=None,
        scope={"scene_id": SCENE_TOWN}, parameters={}, game_time=0,
        scheduled_start=100, deadline=200, admin=True,
    )
    assert event.state == "scheduled"


def test_active_event_cap_is_sixteen_and_weight_cap_twelve():
    # 上限语义：weight 12 先于实例数 16 触达（minor=1 → 12 个即满）
    assert ACTIVE_EVENT_CAP == 16
    assert ACTIVE_WEIGHT_CAP == 12
    world, _fakes = make_world()
    # 高并发模板隔离出纯预算约束（rumor 模板并发上限 8 会先触达）
    from src.events.templates import EventTemplate
    world.event_templates.register(EventTemplate(
        event_template_id="event.test.chatter", name="测试杂谈",
        default_severity="minor",
        allowed_sources=frozenset({"state"}),
        max_concurrent_instances=64, dedup_window_game_minutes=1,
    ))
    # 同一 (template, scope) 受语义窗口约束：按 dedup 窗口间隔激活
    for index in range(12):
        activate_event(world, f"cap-{index}", template_id="event.test.chatter",
                       source="state", admin=False, game_time=index * 2)
    with pytest.raises(EventError) as exc:
        activate_event(world, "cap-13", template_id="event.test.chatter",
                       source="state", admin=False, game_time=13 * 2)
    assert exc.value.code == "budget_exceeded"


def test_template_concurrency_cap():
    world, _fakes = make_world()
    activate_event(world, "cc-1", template_id="event.disaster.forest_fire",
                   source="environment", admin=False,
                   parameters={"origin": "test"},
                   scope={"scene_id": "region.twilight_whisper_forest"})
    with pytest.raises(EventError) as exc:
        world.engine.instantiate(
            command_id="cc-2", event_template_id="event.disaster.forest_fire",
            source="environment", source_evidence_id=None,
            scope={"scene_id": "region.twilight_whisper_forest"},
            parameters={"origin": "test2"}, game_time=5000,
        )
    # 同 scope 语义窗口先拦截；换 scope 才轮到并发上限
    assert exc.value.code in ("duplicate_semantic_window", "max_concurrent_exceeded")


# -- TEST-EVENT-002：状态机与来源约束 ------------------------------------------


def test_illegal_transition_rejected():
    world, _fakes = make_world()
    event = activate_event(world, "t1")
    with pytest.raises(EventError) as exc:
        world.engine.transition(event.world_event_id, "archived", 1,
                                expected_version=event.version)
    assert exc.value.code == "state_transition_illegal"


def test_version_stale_rejected():
    world, _fakes = make_world()
    event = activate_event(world, "t2")
    with pytest.raises(EventError) as exc:
        world.engine.transition(event.world_event_id, "escalated", 1,
                                expected_version=event.version + 9)
    assert exc.value.code == "version_stale"


def test_active_escalated_roundtrip():
    world, _fakes = make_world()
    event = activate_event(world, "t3")
    world.engine.transition(event.world_event_id, "escalated", 1,
                            expected_version=event.version)
    current = world.engine.get(event.world_event_id)
    assert current.state == "escalated"
    world.engine.transition(current.world_event_id, "active", 2,
                            expected_version=current.version)
    assert world.engine.get(event.world_event_id).state == "active"


def test_terminal_aftermath_archived_chain():
    world, _fakes = make_world()
    event = activate_event(world, "t4")
    event = terminal_to_aftermath(world, event)
    assert event.state == "aftermath"
    world.engine.transition(event.world_event_id, "archived", 20,
                            expected_version=event.version, reason="done")
    assert world.engine.get(event.world_event_id).state == "archived"


def test_archive_blocked_by_pending_aftermath():
    world, _fakes = make_world()
    event = activate_event(
        world, "t5", template_id="event.disaster.forest_fire", source="environment",
        admin=False, parameters={"origin": "x"},
        scope={"scene_id": "region.twilight_whisper_forest"},
    )
    event = terminal_to_aftermath(world, event)
    assert len(event.aftermath_task_ids) == 2  # compensation + reconstruction
    with pytest.raises(EventError) as exc:
        world.engine.transition(event.world_event_id, "archived", 30,
                                expected_version=event.version)
    assert exc.value.code == "state_transition_illegal"


def test_template_unknown_and_parameter_and_scope_errors():
    world, _fakes = make_world()
    with pytest.raises(EventError) as exc:
        world.engine.instantiate(
            command_id="e1", event_template_id="event.unknown", source="admin",
            source_evidence_id=None, scope={"scene_id": SCENE_TOWN},
            parameters={}, game_time=0, admin=True)
    assert exc.value.code == "event_template_unknown"

    with pytest.raises(EventError) as exc:
        world.engine.instantiate(
            command_id="e2", event_template_id="event.festival.harvest",
            source="admin", source_evidence_id=None,
            scope={"scene_id": SCENE_TOWN}, parameters={"rogue": 1},
            game_time=0, admin=True)
    assert exc.value.code == "parameters_invalid"

    with pytest.raises(EventError) as exc:
        world.engine.instantiate(
            command_id="e3", event_template_id="event.festival.harvest",
            source="admin", source_evidence_id=None,
            scope={"scene_id": SCENE_TOWN, "rogue": "x"},
            parameters={}, game_time=0, admin=True)
    assert exc.value.code == "scope_invalid"

    with pytest.raises(EventError) as exc:
        world.engine.instantiate(
            command_id="e4", event_template_id="event.festival.harvest",
            source="admin", source_evidence_id=None,
            scope={"scene_id": "scene.void"}, parameters={}, game_time=0, admin=True)
    assert exc.value.code == "scope_invalid"


def test_source_not_permitted_and_admin_mark():
    world, _fakes = make_world()
    # festival 不允许 player 来源
    with pytest.raises(EventError) as exc:
        world.engine.instantiate(
            command_id="s1", event_template_id="event.festival.harvest",
            source="player", source_evidence_id=None,
            scope={"scene_id": SCENE_TOWN}, parameters={}, game_time=0)
    assert exc.value.code == "source_not_permitted"
    # admin 来源必须带审计标记
    with pytest.raises(EventError) as exc:
        world.engine.instantiate(
            command_id="s2", event_template_id="event.festival.harvest",
            source="admin", source_evidence_id=None,
            scope={"scene_id": SCENE_TOWN}, parameters={}, game_time=0, admin=False)
    assert exc.value.code == "source_not_permitted"
    # 带标记的 admin 实例化在日志留下 admin_marked
    world.engine.instantiate(
        command_id="s3", event_template_id="event.festival.harvest",
        source="admin", source_evidence_id=None,
        scope={"scene_id": SCENE_TOWN}, parameters={}, game_time=0, admin=True)
    entry = next(e for e in world.event_log.entries()
                 if e["event_type"] == "world_event.instantiated")
    assert entry["payload"]["admin_marked"] is True


# -- TEST-EVENT-003：时间驱动只经 TIME + 三层防重 -------------------------------


def test_scheduled_event_waits_for_time_occurrence():
    world, _fakes = make_world()
    event = world.engine.instantiate(
        command_id="d1", event_template_id="event.festival.harvest",
        source="admin", source_evidence_id=None,
        scope={"scene_id": SCENE_TOWN}, parameters={}, game_time=0,
        scheduled_start=100, deadline=200, admin=True,
    )
    # 无逐 Tick 扫描：状态保持 scheduled 直到 occurrence 到达
    assert world.engine.get(event.world_event_id).state == "scheduled"
    result = world.on_occurrence(occ(
        "event_activate", "occ-activate-1", 100,
        payload={"world_event_id": event.world_event_id},
    ))
    assert result["result"]["status"] == "activated"
    assert world.engine.get(event.world_event_id).state == "active"


def test_scheduled_event_expires_past_deadline():
    world, _fakes = make_world()
    event = world.engine.instantiate(
        command_id="d2", event_template_id="event.festival.harvest",
        source="admin", source_evidence_id=None,
        scope={"scene_id": SCENE_TOWN}, parameters={}, game_time=0,
        scheduled_start=100, deadline=200, admin=True,
    )
    result = world.on_occurrence(occ(
        "event_activate", "occ-activate-2", 250,
        payload={"world_event_id": event.world_event_id},
    ))
    assert result["result"]["status"] == "expired"
    assert world.engine.get(event.world_event_id).state == "expired"


def test_occurrence_replay_is_idempotent():
    world, _fakes = make_world()
    event = world.engine.instantiate(
        command_id="d3", event_template_id="event.festival.harvest",
        source="admin", source_evidence_id=None,
        scope={"scene_id": SCENE_TOWN}, parameters={}, game_time=0,
        scheduled_start=100, deadline=200, admin=True,
    )
    first = world.on_occurrence(occ(
        "event_activate", "occ-activate-3", 100,
        payload={"world_event_id": event.world_event_id},
    ))
    second = world.on_occurrence(occ(
        "event_activate", "occ-activate-3", 100,
        payload={"world_event_id": event.world_event_id},
    ))
    assert first["status"] == "processed"
    assert second["status"] == "replayed"
    assert len([e for e in world.event_log.entries()
                if e["event_type"] == "world_event.active"]) == 1


def test_occurrence_key_dedup_on_instantiate():
    world, _fakes = make_world()
    kwargs = dict(
        event_template_id="event.festival.harvest", source="state",
        source_evidence_id=None, scope={"scene_id": SCENE_TOWN},
        parameters={}, game_time=0, occurrence_key="occ-trigger-x",
    )
    world.engine.instantiate(command_id="k1", **kwargs)
    with pytest.raises(EventError) as exc:
        world.engine.instantiate(command_id="k2", **kwargs)
    assert exc.value.code == "occurrence_replayed"


def test_command_idempotency_returns_same_event():
    world, _fakes = make_world()
    kwargs = dict(
        event_template_id="event.festival.harvest", source="admin",
        source_evidence_id=None, scope={"scene_id": SCENE_TOWN},
        parameters={}, game_time=0, admin=True,
    )
    first = world.engine.instantiate(command_id="cmd-same", **kwargs)
    second = world.engine.instantiate(command_id="cmd-same", **kwargs)
    assert first.world_event_id == second.world_event_id
    assert len([e for e in world.event_log.entries()
                if e["event_type"] == "world_event.instantiated"]) == 1


def test_semantic_window_dedup():
    world, _fakes = make_world()
    kwargs = dict(
        event_template_id="event.minor.rumor", source="state",
        source_evidence_id=None, scope={"scene_id": SCENE_TOWN},
        parameters={}, game_time=0,
    )
    world.engine.instantiate(command_id="w1", **kwargs)
    with pytest.raises(EventError) as exc:
        world.engine.instantiate(command_id="w2", **kwargs)
    assert exc.value.code == "duplicate_semantic_window"
    # 窗口外允许新实例
    later = dict(kwargs, game_time=61)
    world.engine.instantiate(command_id="w3", **later)
