"""EVENT 测试共享夹具（tests 目录无 __init__.py，用绝对导入）"""

from src.events import make_event_world
from src.events.fixtures import SCENE_FOREST, SCENE_TOWN

SEED = "8f3a1c2b9d4e5f60718293a4b5c6d7e8"

PHASES = [
    ("planning", "architect", 60),
    ("clearing", "laborer", 120),
    ("foundation_work", "mason", 240),
    ("structure_work", "carpenter", 480),
    ("fitting", "carpenter", 120),
    ("acceptance", "architect", 30),
]

COTTAGE_MATERIALS = {"item.stone": 10, "item.timber": 20, "item.nail": 5}


def make_world(seed_hex: str = SEED, register_content: bool = True):
    return make_event_world(seed_hex=seed_hex, register_content=register_content)


def occ(kind, key, game_time, payload=None, **extra):
    occurrence = {
        "occurrence_key": key,
        "kind": kind,
        "game_time": game_time,
        "payload": payload or {},
    }
    occurrence.update(extra)
    return occurrence


def place_cottage(world, fakes, command_id="place-1", parcel_id="parcel.town.1",
                  requester="resident.mayor", game_time=0, x=4, y=4, orientation=0,
                  template_id="building.cottage"):
    fakes.econ.grant_build_right(requester, parcel_id)
    scene_id = world.parcels.get(parcel_id).scene_id
    revision = fakes.map_port.current_revision(scene_id)
    return world.placement.submit_build(
        command_id=command_id, parcel_id=parcel_id, building_template_id=template_id,
        orientation=orientation, footprint_xy=(x, y), budget_source="treasury",
        expected_revision=revision, requester_id=requester, game_time=game_time,
    )


def work_all_phases(world, building_id, command_prefix="ws", game_time=0):
    for index, (phase, profession, minutes) in enumerate(PHASES):
        building = world.buildings.get(building_id)
        world.construction.submit_work_session(
            command_id=f"{command_prefix}-{index}",
            building_id=building_id,
            profession=profession,
            labor_game_minutes=minutes,
            efficiency_bps=10_000,
            game_time=game_time + index,
            expected_phase=phase,
            expected_version=building.version,
        )


def build_cottage_full(world, fakes, command_id="place-full", parcel_id="parcel.town.1",
                       game_time=0, template_id="building.cottage"):
    building = place_cottage(world, fakes, command_id=command_id,
                             parcel_id=parcel_id, game_time=game_time,
                             template_id=template_id)
    world.construction.deliver_materials(
        f"{command_id}-mats", building.building_id, dict(COTTAGE_MATERIALS), game_time,
    )
    work_all_phases(world, building.building_id,
                    command_prefix=f"{command_id}-ws", game_time=game_time)
    return world.buildings.get(building.building_id)


def activate_event(world, command_id, template_id="event.festival.harvest",
                   source="admin", scope=None, parameters=None, game_time=0,
                   admin=True, severity=None):
    event = world.engine.instantiate(
        command_id=command_id, event_template_id=template_id, source=source,
        source_evidence_id=None, scope=scope or {"scene_id": SCENE_TOWN},
        parameters=parameters or {}, game_time=game_time, admin=admin,
        severity=severity,
    )
    world.engine.transition(event.world_event_id, "active", game_time,
                            expected_version=event.version, reason="test",
                            admin=admin)
    return world.engine.get(event.world_event_id)


def terminal_to_aftermath(world, event, target="resolved", game_time=10):
    current = world.engine.get(event.world_event_id)
    world.engine.transition(current.world_event_id, target, game_time,
                            expected_version=current.version, reason="test")
    current = world.engine.get(event.world_event_id)
    world.engine.transition(current.world_event_id, "aftermath", game_time + 1,
                            expected_version=current.version, reason="test")
    return world.engine.get(event.world_event_id)


# ---------------------------------------------------------------------------
# Scenario Fixture 固定命令脚本（DOC-EVENT-012；注册表见 fixtures.SCENARIO_FIXTURES）
# ---------------------------------------------------------------------------

MANOR_MATERIALS = {"item.stone": 20, "item.timber": 40, "item.nail": 10}

MANOR_PHASES = [
    ("planning", "architect", 120),
    ("clearing", "laborer", 240),
    ("foundation_work", "mason", 480),
    ("structure_work", "carpenter", 960),
    ("fitting", "carpenter", 240),
    ("acceptance", "architect", 60),
]

FIRE_AIM_POINT = {"scene_id": SCENE_FOREST, "x": 4, "y": 4}


def run_scenario_forest_fire(world, fakes):
    """TEST-EVENT-039 森林火灾全链：触发→封路→焚毁→营救→赔偿→清瓦砾→重开→归档"""
    clock = world.test_clock
    out = {}
    clock["now"] = 0

    # 1) 森林地块完整建房（六阶段 → intact）
    building = build_cottage_full(world, fakes, command_id="s39-place",
                                  parcel_id="parcel.forest.1", game_time=0)
    building_id = building.building_id
    out["building_id"] = building_id

    # 2) 易燃点绑定建筑；干旱投影触发森林火灾（trigger.drought_fire，chance=1.0）
    world.environment.register_flammable_point(
        SCENE_FOREST, SCENE_FOREST, dict(FIRE_AIM_POINT), building_id=building_id)
    clock["now"] = 10
    result = world.on_occurrence(occ(
        "trigger_eval", "s39-trig-1", 10,
        projection={"scene_id": SCENE_FOREST, "public": {"drought_days": 3}},
        source="state"))
    fired = result["result"]["fired"]
    assert len(fired) == 1 and fired[0]["trigger_id"] == "trigger.drought_fire"
    fire_event_id = fired[0]["world_event_id"]
    out["fire_event_id"] = fire_event_id

    # 3) 火灾封路（NavigationPatch + WorldDiff environment_blockade）
    clock["now"] = 20
    blockade_entry_id = world.environment.apply_blockade(
        SCENE_FOREST, "blockade.fire.1",
        {"object_template_id": "collision.fire_line",
         "value": {"shape_type": "polygon",
                   "outer_ring_wu": [[0, 0], [64, 0], [64, 2], [0, 2]],
                   "obstacle_tag": "fire_line"}},
        game_time=20,
        source={"command_id": "s39-blockade", "world_event_id": fire_event_id})
    out["blockade_entry_id"] = blockade_entry_id

    # 4) 点火 + 16 次火焰 tick（5 点/tick × 16 = 80 → ruins）
    fire_id = world.environment.ignite(dict(FIRE_AIM_POINT),
                                       source_event_id=fire_event_id)
    out["fire_id"] = fire_id
    for tick in range(16):
        clock["now"] = 80 + tick * 60
        world.environment.fire_tick(clock["now"])
    assert world.buildings.get(building_id).physical_state == "ruins"

    # 5) 营救 Quest：offer → accept → begin → reach → win_encounter → completed
    clock["now"] = 1100
    quest = world.quests.create_offer(
        "s39-quest-offer", "quest.rescue.villager",
        {"rescuer": ["resident.hero"]}, game_time=1100,
        source_world_event_id=fire_event_id)
    world.quests.respond("s39-quest-accept", quest.quest_id, True, 1101,
                         expected_version=quest.version)
    quest = world.quests.get(quest.quest_id)
    world.quests.begin("s39-quest-begin", quest.quest_id, 1102,
                       expected_version=quest.version)
    world.quests.submit_domain_event(
        {"event_id": "s39-ev-reach", "event_type": "movement.arrived",
         "payload": {"location_id": "loc.forest_edge",
                     "resident_id": "resident.hero"}}, 1103)
    world.quests.submit_domain_event(
        {"event_id": "s39-ev-win", "event_type": "combat.encounter_resolved",
         "payload": {"winning_side": "residents",
                     "resident_id": "resident.hero"}}, 1104)
    quest = world.quests.get(quest.quest_id)
    assert quest.state == "completed" and quest.rewards_granted
    out["quest_id"] = quest.quest_id

    # 6) 灭火
    world.environment.extinguish(dict(FIRE_AIM_POINT), source_event_id=fire_event_id)

    # 7) 事件 terminal → aftermath（模板 aftermath_plan 生成赔偿+重建任务）
    clock["now"] = 1200
    terminal_to_aftermath(world, world.engine.get(fire_event_id),
                          target="resolved", game_time=1200)

    # 8) 瓦砾排他领取 + 清理（parcel 恢复可建）
    rubble = world.buildings.rubble_of(building_id)
    world.buildings.claim_rubble("s39-claim", rubble.rubble_id, "resident.hero", 1210)
    world.buildings.cleanup_rubble("s39-cleanup", rubble.rubble_id, 1211)
    out["rubble_id"] = rubble.rubble_id

    # 9) Reverse Entry 重开道路
    world.environment.lift_blockade(
        blockade_entry_id, fakes.map_port.base_layers(SCENE_FOREST), 1220,
        source={"command_id": "s39-lift", "world_event_id": fire_event_id})

    # 10) aftermath 任务全部完成 → archived
    for task in world.aftermath.all():
        if task.world_event_id != fire_event_id:
            continue
        world.aftermath.start(task.task_id, 1230, expected_version=task.version)
        task = world.aftermath.get(task.task_id)
        world.aftermath.complete(task.task_id, 1231, expected_version=task.version)
    event = world.engine.get(fire_event_id)
    world.engine.transition(fire_event_id, "archived", 1240,
                            expected_version=event.version, reason="scenario done")
    return out


def run_scenario_construction(world, fakes):
    """TEST-EVENT-040 建造全链：放置→六阶段→升级 manor→风暴损毁→评估→修复"""
    clock = world.test_clock
    out = {}
    clock["now"] = 0

    # 1) 城镇地块放置小屋 + 六阶段 → intact
    building = build_cottage_full(world, fakes, command_id="s40-place",
                                  parcel_id="parcel.town.1", game_time=0)
    building_id = building.building_id
    out["building_id"] = building_id

    # 2) 升级 manor：start_upgrade → 交材(scale=2) → 六阶段 → intact(manor)
    clock["now"] = 100
    building = world.buildings.get(building_id)
    world.construction.start_upgrade("s40-upgrade", building_id, "building.manor",
                                     100, expected_version=building.version)
    world.construction.deliver_materials("s40-mats", building_id,
                                         dict(MANOR_MATERIALS), 101)
    for index, (phase, profession, minutes) in enumerate(MANOR_PHASES):
        current = world.buildings.get(building_id)
        world.construction.submit_work_session(
            f"s40-ws-{index}", building_id, profession, minutes, 10_000, 102 + index,
            expected_phase=phase, expected_version=current.version)
    building = world.buildings.get(building_id)
    assert building.building_template_id == "building.manor"
    assert building.physical_state == "intact" and building.construction_phase is None

    # 3) 风暴损毁 45 点 → severely_damaged
    clock["now"] = 200
    world.buildings.apply_damage("s40-storm", building_id, "storm", 45, 200,
                                 evidence_id="storm.season.1")
    assert world.buildings.get(building_id).physical_state == "severely_damaged"

    # 4) 评估 → 修复 45 点（450 工时）→ intact
    assessment = world.buildings.assess_damage("s40-assess", building_id, 210)
    world.buildings.repair("s40-repair", building_id, labor_game_minutes=450,
                           materials={"item.timber": 5}, game_time=220,
                           assessment_id=assessment.assessment_id)
    building = world.buildings.get(building_id)
    assert building.physical_state == "intact" and building.damage_points == 0
    out["assessment_id"] = assessment.assessment_id
    return out
