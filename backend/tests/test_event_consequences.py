"""TEST-EVENT-013..015：后果传播与善后任务（DOC-EVENT-005）"""

import pytest

from src.events import (
    AftermathTaskSpec,
    ConsequenceError,
    ConsequenceSpec,
    EventTemplate,
    TemplateError,
)
from event_helpers import activate_event, make_world, occ, terminal_to_aftermath
from src.events.fixtures import SCENE_FOREST, SCENE_TOWN


def _festival_event(world, command_id="fc-1", game_time=0):
    return activate_event(world, command_id, game_time=game_time)


# -- TEST-EVENT-013：阶段分发、稳定 ID、上限 -------------------------------------


def test_on_active_consequences_dispatch_to_ports():
    world, fakes = make_world()
    event = _festival_event(world)
    # econ：Region Modifier 稳定 ID
    modifier_id = f"region_modifier.{event.world_event_id}.festival_mood"
    assert modifier_id in fakes.econ.region_modifiers
    assert fakes.econ.region_modifiers[modifier_id]["modifier"] == {"happiness": 1}
    # memory：认知按公开程度分发
    assert len(fakes.memory.distributions) == 1
    assert fakes.memory.distributions[0]["publicity"] == "public"
    # 分发记录完成
    for record in world.consequences.records():
        assert record.status == "completed"


def test_consequence_stable_id_no_duplicate_modifier():
    world, fakes = make_world()
    event = _festival_event(world)
    # 再次分发同阶段（重放）→ 不产生第二个 modifier
    world.consequences.dispatch_phase(event, "on_active", 1)
    modifiers = [m for m in fakes.econ.region_modifiers
                 if "festival_mood" in m]
    assert len(modifiers) == 1
    replay_logs = [e for e in world.event_log.entries()
                   if e["event_type"] == "consequence_replayed"]
    assert len(replay_logs) == 2  # festival_mood + festival_news


def test_escalated_and_terminal_phase_dispatch():
    world, fakes = make_world()
    world.event_templates.register(EventTemplate(
        event_template_id="event.test.phases", name="阶段测试",
        default_severity="moderate", allowed_sources=frozenset({"admin"}),
        max_concurrent_instances=2, dedup_window_game_minutes=0,
        consequence_plan=(
            ConsequenceSpec("c_active", "on_active", "memory", "distribute",
                            {"content": {"fact": "active"}}, publicity="scene"),
            ConsequenceSpec("c_escalated", "on_escalated", "memory", "distribute",
                            {"content": {"fact": "escalated"}}, publicity="scene"),
            ConsequenceSpec("c_terminal", "on_terminal", "memory", "distribute",
                            {"content": {"fact": "terminal"}}, publicity="scene"),
            ConsequenceSpec("c_aftermath", "on_aftermath", "memory", "distribute",
                            {"content": {"fact": "aftermath"}}, publicity="scene"),
        ),
    ))
    event = activate_event(world, "ph-1", template_id="event.test.phases")
    assert fakes.memory.distributions[-1]["content"] == {"fact": "active"}
    world.engine.transition(event.world_event_id, "escalated", 5,
                            expected_version=event.version)
    assert fakes.memory.distributions[-1]["content"] == {"fact": "escalated"}
    current = world.engine.get(event.world_event_id)
    world.engine.transition(current.world_event_id, "resolved", 6,
                            expected_version=current.version)
    assert fakes.memory.distributions[-1]["content"] == {"fact": "terminal"}
    current = world.engine.get(event.world_event_id)
    world.engine.transition(current.world_event_id, "aftermath", 7,
                            expected_version=current.version)
    assert fakes.memory.distributions[-1]["content"] == {"fact": "aftermath"}


def test_consequence_cap_32():
    with pytest.raises(TemplateError) as exc:
        EventTemplate(
            event_template_id="event.test.toomany", name="过多后果",
            default_severity="minor", allowed_sources=frozenset({"admin"}),
            max_concurrent_instances=1, dedup_window_game_minutes=0,
            consequence_plan=tuple(
                ConsequenceSpec(f"c{i}", "on_active", "memory", "distribute", {})
                for i in range(33)
            ),
        )
    assert exc.value.code == "consequence_cap_exceeded"


# -- TEST-EVENT-014：noop / transient 重试 / terminal 留 pending ------------------


def test_target_missing_completed_noop():
    world, _fakes = make_world()
    world.event_templates.register(EventTemplate(
        event_template_id="event.test.noop", name="noop 测试",
        default_severity="minor", allowed_sources=frozenset({"admin"}),
        max_concurrent_instances=1, dedup_window_game_minutes=0,
        consequence_plan=(
            ConsequenceSpec("c_map", "on_active", "map", "patch",
                            {"blockade_id": "road.x"}),
        ),
    ))

    from src.events.consequences import TargetMissing

    def missing_handler(_event, _params, _game_time):
        raise TargetMissing("road.x gone")

    world.consequences._map_handler = missing_handler
    activate_event(world, "noop-1", template_id="event.test.noop")
    record = world.consequences.record_of(
        world.engine.all()[0].world_event_id, "c_map")
    assert record.status == "completed_noop"


def test_owner_unavailable_transient_retry():
    world, fakes = make_world()
    world.event_templates.register(EventTemplate(
        event_template_id="event.test.retry", name="重试测试",
        default_severity="minor", allowed_sources=frozenset({"admin"}),
        max_concurrent_instances=1, dedup_window_game_minutes=0,
        consequence_plan=(
            ConsequenceSpec("c_notify", "on_active", "resident", "notify",
                            {"resident_id": "resident.mayor",
                             "content": {"alert": "x"}}),
        ),
    ))
    fakes.resident.unavailable = True
    event = activate_event(world, "rt-1", template_id="event.test.retry")
    record = world.consequences.record_of(event.world_event_id, "c_notify")
    assert record.status == "pending_transient"
    # 恢复后重试成功
    fakes.resident.unavailable = False
    world.on_occurrence(occ("consequence_retry", "retry-1", 10))
    record = world.consequences.record_of(event.world_event_id, "c_notify")
    assert record.status == "completed"
    assert record.attempts == 2


def test_port_rejected_terminal_stays_pending():
    world, fakes = make_world()
    fakes.econ.fail_reward = False
    world.event_templates.register(EventTemplate(
        event_template_id="event.test.terminal", name="terminal 测试",
        default_severity="minor", allowed_sources=frozenset({"admin"}),
        max_concurrent_instances=1, dedup_window_game_minutes=0,
        consequence_plan=(
            ConsequenceSpec("c_secret", "on_active", "memory", "distribute",
                            {"content": {"note": "this mentions secret data"}}),
        ),
    ))
    event = activate_event(world, "tm-1", template_id="event.test.terminal")
    record = world.consequences.record_of(event.world_event_id, "c_secret")
    assert record.status == "pending_terminal"
    assert record.last_error == "memory_secret_forbidden"
    # 重试不改变 terminal 状态（consequence_replayed 记录）
    world.on_occurrence(occ("consequence_retry", "retry-2", 10))
    record = world.consequences.record_of(event.world_event_id, "c_secret")
    assert record.status == "pending_terminal"
    assert record.attempts == 1


# -- TEST-EVENT-015：Aftermath Task 与认知公开程度 ---------------------------------


def test_aftermath_tasks_created_and_block_archive():
    world, _fakes = make_world()
    event = activate_event(
        world, "am-1", template_id="event.disaster.forest_fire",
        source="environment", admin=False, parameters={"origin": "x"},
        scope={"scene_id": SCENE_FOREST})
    event = terminal_to_aftermath(world, event)
    tasks = [world.aftermath.get(tid) for tid in event.aftermath_task_ids]
    assert {t.task_kind for t in tasks} == {"compensation", "reconstruction"}
    assert all(t.state == "pending" for t in tasks)
    from src.events import EventError
    with pytest.raises(EventError) as exc:
        world.engine.transition(event.world_event_id, "archived", 50,
                                expected_version=event.version)
    assert exc.value.code == "state_transition_illegal"
    # 完成全部任务后可归档
    for task in tasks:
        world.aftermath.start(task.task_id, 51, expected_version=task.version)
        current = world.aftermath.get(task.task_id)
        world.aftermath.complete(current.task_id, 52,
                                 expected_version=current.version)
    current = world.engine.get(event.world_event_id)
    world.engine.transition(current.world_event_id, "archived", 53,
                            expected_version=current.version)
    assert world.engine.get(event.world_event_id).state == "archived"


def test_mayor_cancel_releases_archive_with_mark():
    world, _fakes = make_world()
    event = activate_event(
        world, "am-2", template_id="event.disaster.forest_fire",
        source="environment", admin=False, parameters={"origin": "x"},
        scope={"scene_id": SCENE_FOREST})
    event = terminal_to_aftermath(world, event)
    task = world.aftermath.get(event.aftermath_task_ids[0])
    # 非镇长取消被拒
    with pytest.raises(ConsequenceError) as exc:
        world.aftermath.cancel(task.task_id, 51, expected_version=task.version)
    assert exc.value.code == "aftermath_cancel_forbidden"
    # 镇长取消放行，带审计标记
    world.aftermath.cancel(task.task_id, 51, expected_version=task.version,
                           mayor=True)
    cancel_log = next(e for e in world.event_log.entries()
                      if e["event_type"] == "aftermath_task.cancelled")
    assert cancel_log["payload"]["mayor_marked"] is True
    other = world.aftermath.get(event.aftermath_task_ids[1])
    world.aftermath.cancel(other.task_id, 51,
                           expected_version=other.version, mayor=True)
    current = world.engine.get(event.world_event_id)
    world.engine.transition(current.world_event_id, "archived", 52,
                            expected_version=current.version)
    assert world.engine.get(event.world_event_id).state == "archived"


def test_map_consequence_goes_through_committer():
    world, fakes = make_world()
    world.event_templates.register(EventTemplate(
        event_template_id="event.test.mapcons", name="地图后果测试",
        default_severity="major", allowed_sources=frozenset({"admin"}),
        max_concurrent_instances=1, dedup_window_game_minutes=0,
        consequence_plan=(
            ConsequenceSpec("c_blockade", "on_active", "map", "patch",
                            {"blockade_id": "hazard.flood.1",
                             "object_template_id": "collision.hazard.flood",
                             "value": {"shape_type": "polygon",
                                       "outer_ring_wu": [[0, 0], [8, 0], [8, 8], [0, 8]],
                                       "obstacle_tag": "hazard.flood"}}),
        ),
    ))

    def map_handler(event, params, game_time):
        world.environment.apply_blockade(
            SCENE_TOWN, params["blockade_id"],
            {"object_template_id": params["object_template_id"],
             "value": params["value"]},
            game_time,
            source={"command_id": None, "world_event_id": event.world_event_id},
        )

    world.consequences._map_handler = map_handler
    activate_event(world, "mc-1", template_id="event.test.mapcons")
    # 四件套：patch + diff entry + 两个事件（blockade + patch_committed）
    assert len(fakes.map_port.patches) == 1
    entries = world.diff_log.entries(SCENE_TOWN)
    assert len(entries) == 1
    assert entries[0].diff_kind == "environment_blockade"
    event_types = [e["event_type"] for e in world.event_log.entries()]
    assert "environment.blockade_applied" in event_types
    assert "navigation.patch_committed" in event_types


def test_memory_distribution_respects_publicity_and_no_secret():
    world, fakes = make_world()
    _festival_event(world, "pub-1")
    distribution = fakes.memory.distributions[0]
    assert distribution["publicity"] == "public"
    # 含 secret 的内容被 memory 端口拒绝（terminal pending，见 test_port_rejected）
    assert "secret" not in str(distribution["content"]).lower()
