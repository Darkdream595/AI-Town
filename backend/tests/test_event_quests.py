"""TEST-EVENT-010..012：Quest 状态机、Matcher、Deadline 与奖励（DOC-EVENT-004）"""

import pytest

from src.events import ObjectiveSpec, QuestError, match_objective
from event_helpers import make_world, occ


def _offer(world, command_id="q1", template_id="quest.deliver.supplies",
           participants=None, game_time=0):
    return world.quests.create_offer(
        command_id=command_id, quest_template_id=template_id,
        participants=participants or {"courier": ["resident.hero"]},
        game_time=game_time,
    )


def _accept_and_begin(world, quest, game_time=1):
    world.quests.respond(f"q-accept-{quest.quest_id}", quest.quest_id, True, game_time,
                         expected_version=quest.version)
    current = world.quests.get(quest.quest_id)
    world.quests.begin(f"q-begin-{quest.quest_id}", quest.quest_id, game_time + 1,
                       expected_version=current.version)
    return world.quests.get(quest.quest_id)


def _event(event_id, event_type, payload):
    return {"event_id": event_id, "event_type": event_type, "payload": payload}


# -- TEST-EVENT-010：生命周期与上限 --------------------------------------------


def test_full_lifecycle_to_archived():
    world, _fakes = make_world()
    quest = _offer(world)
    assert quest.state == "offered"
    quest = _accept_and_begin(world, quest)
    assert quest.state == "active"
    # 完成 2 次投递
    world.quests.submit_domain_event(_event(
        "ev1", "item.delivered",
        {"resident_id": "resident.hero", "item_template_id": "item.supplies",
         "to": "resident.mayor"}), 10)
    world.quests.submit_domain_event(_event(
        "ev2", "item.delivered",
        {"resident_id": "resident.hero", "item_template_id": "item.supplies",
         "to": "resident.mayor"}), 11)
    quest = world.quests.get(quest.quest_id)
    assert quest.state == "completed"
    world.quests.archive("q-arch", quest.quest_id, 20,
                         expected_version=quest.version)
    assert world.quests.get(quest.quest_id).state == "archived"


def test_decline_and_abandon_paths():
    world, _fakes = make_world()
    quest = _offer(world, "q2")
    world.quests.respond("q2-r", quest.quest_id, False, 1,
                         expected_version=quest.version)
    quest = world.quests.get(quest.quest_id)
    assert quest.state == "declined"
    world.quests.archive("q2-a", quest.quest_id, 2,
                         expected_version=quest.version)
    assert world.quests.get(quest.quest_id).state == "archived"

    quest2 = _offer(world, "q3")
    quest2 = _accept_and_begin(world, quest2)
    world.quests.abandon("q3-ab", quest2.quest_id, 5,
                         expected_version=quest2.version)
    assert world.quests.get(quest2.quest_id).state == "abandoned"


def test_illegal_transition_and_version_stale():
    world, _fakes = make_world()
    quest = _offer(world, "q4")
    with pytest.raises(QuestError) as exc:
        world.quests.begin("q4-b", quest.quest_id, 1,
                           expected_version=quest.version)
    assert exc.value.code == "state_transition_illegal"
    with pytest.raises(QuestError) as exc:
        world.quests.respond("q4-r", quest.quest_id, True, 1,
                             expected_version=quest.version + 5)
    assert exc.value.code == "version_stale"


def test_offer_taken_on_double_respond():
    world, _fakes = make_world()
    quest = _offer(world, "q5")
    world.quests.respond("q5-r1", quest.quest_id, True, 1,
                         expected_version=quest.version)
    current = world.quests.get(quest.quest_id)
    # 同一条 quest 已被接受：第二次响应版本正确但状态不再是 offered
    with pytest.raises(QuestError) as exc:
        world.quests.respond("q5-r2", quest.quest_id, True, 2,
                             expected_version=current.version)
    assert exc.value.code == "offer_taken"


def test_participant_invalid_and_open_cap():
    world, _fakes = make_world()
    with pytest.raises(QuestError) as exc:
        world.quests.create_offer(
            command_id="q6", quest_template_id="quest.deliver.supplies",
            participants={}, game_time=0)
    assert exc.value.code == "participant_invalid"
    for index in range(64):
        _offer(world, f"cap-q-{index}")
    with pytest.raises(QuestError) as exc:
        _offer(world, "cap-q-65")
    assert exc.value.code == "quest_open_cap_exceeded"


# -- TEST-EVENT-011：Matcher 九类与去重 ------------------------------------------


def test_matcher_nine_kinds():
    participants = ["resident.hero"]
    cases = [
        (ObjectiveSpec("o", "reach_location", {"location_id": "loc.x"}),
         _event("e", "movement.arrived",
                {"resident_id": "resident.hero", "location_id": "loc.x"}), True),
        (ObjectiveSpec("o", "reach_location", {"location_id": "loc.x"}),
         _event("e", "movement.arrived",
                {"resident_id": "resident.other", "location_id": "loc.x"}), False),
        (ObjectiveSpec("o", "deliver_item", {"item_template_id": "i1", "to": "r2"}),
         _event("e", "item.delivered",
                {"item_template_id": "i1", "to": "r2"}), True),
        (ObjectiveSpec("o", "deliver_item", {"item_template_id": "i1", "to": "r2"}),
         _event("e", "item.delivered",
                {"item_template_id": "i1", "to": "r3"}), False),
        (ObjectiveSpec("o", "talk_to", {"target_resident_id": "r2"}),
         _event("e", "dialogue.completed",
                {"resident_id": "resident.hero", "target_resident_id": "r2"}), True),
        (ObjectiveSpec("o", "craft_item", {"item_template_id": "i9"}),
         _event("e", "item.crafted",
                {"resident_id": "resident.hero", "item_template_id": "i9"}), True),
        (ObjectiveSpec("o", "investigate", {"clue_tag": "ash"}),
         _event("e", "clue.discovered",
                {"resident_id": "resident.hero", "clue_tag": "ash"}), True),
        (ObjectiveSpec("o", "win_encounter", {"winning_side": "residents"}),
         _event("e", "combat.encounter_resolved",
                {"encounter_id": "enc1", "winning_side": "residents",
                 "end_condition": "enemy_routed"}), True),
        (ObjectiveSpec("o", "win_encounter", {"winning_side": "residents",
                                              "end_conditions": ["enemy_routed"]}),
         _event("e", "combat.encounter_resolved",
                {"encounter_id": "enc1", "winning_side": "residents",
                 "end_condition": "timeout"}), False),
        (ObjectiveSpec("o", "repair_structure", {"building_id": "b1"}),
         _event("e", "building.repaired", {"building_id": "b1"}), True),
        (ObjectiveSpec("o", "protect_target", {"target_id": "t1"}),
         _event("e", "movement.arrived",
                {"resident_id": "resident.hero", "location_id": "loc.x"}), False),
        (ObjectiveSpec("o", "maintain_condition", {"stat": "x"}),
         _event("e", "item.crafted",
                {"resident_id": "resident.hero", "item_template_id": "i9"}), False),
    ]
    for spec, event, expected in cases:
        assert match_objective(spec, event, participants) == expected, spec.kind


def test_event_dedup_per_objective():
    world, _fakes = make_world()
    quest = _accept_and_begin(world, _offer(world, "q7"))
    event = _event("ev-dup", "item.delivered",
                   {"resident_id": "resident.hero",
                    "item_template_id": "item.supplies", "to": "resident.mayor"})
    world.quests.submit_domain_event(event, 10)
    world.quests.submit_domain_event(event, 11)  # 重放同一事件
    progress = world.quests.get(quest.quest_id).objective_progress["deliver"]
    assert progress.count == 1


def test_same_event_advances_multiple_quests():
    world, _fakes = make_world()
    quest_a = _accept_and_begin(world, _offer(world, "q8a"))
    quest_b = _accept_and_begin(world, _offer(world, "q8b",
                                              participants={"courier": ["resident.hero"]}))
    event = _event("ev-both", "item.delivered",
                   {"resident_id": "resident.hero",
                    "item_template_id": "item.supplies", "to": "resident.mayor"})
    progressed = world.quests.submit_domain_event(event, 10)
    assert set(progressed) == {quest_a.quest_id, quest_b.quest_id}


def test_sequential_ordering():
    world, _fakes = make_world()
    quest = _accept_and_begin(world, _offer(
        world, "q9", template_id="quest.rescue.villager",
        participants={"rescuer": ["resident.hero"]}))
    # 先到达战斗事件：defeat 是第二个 objective，顺序阻塞
    world.quests.submit_domain_event(_event(
        "ev-fight", "combat.encounter_resolved",
        {"encounter_id": "enc1", "winning_side": "residents",
         "end_condition": "enemy_routed"}), 10)
    quest = world.quests.get(quest.quest_id)
    assert not quest.objective_progress["defeat"].done
    # 完成 reach 后，重投战斗事件才推进 defeat
    world.quests.submit_domain_event(_event(
        "ev-reach", "movement.arrived",
        {"resident_id": "resident.hero", "location_id": "loc.forest_edge"}), 11)
    world.quests.submit_domain_event(_event(
        "ev-fight2", "combat.encounter_resolved",
        {"encounter_id": "enc1", "winning_side": "residents",
         "end_condition": "enemy_routed"}), 12)
    quest = world.quests.get(quest.quest_id)
    assert quest.objective_progress["reach"].done
    assert quest.objective_progress["defeat"].done
    assert quest.state == "completed"


# -- TEST-EVENT-012：Deadline、奖励与善后 ----------------------------------------


def test_offered_expires_on_deadline():
    world, _fakes = make_world()
    quest = _offer(world, "q10", template_id="quest.rescue.villager",
                   participants={"rescuer": ["resident.hero"]}, game_time=0)
    result = world.on_occurrence(occ(
        "quest_deadline", "qd-1", 1441, payload={"quest_id": quest.quest_id},
    ))
    assert result["result"]["status"] == "expired"
    assert world.quests.get(quest.quest_id).state == "expired"


def test_active_deadline_failure_policy():
    world, _fakes = make_world()
    quest = _offer(world, "q11", template_id="quest.rescue.villager",
                   participants={"rescuer": ["resident.hero"]})
    quest = _accept_and_begin(world, quest)
    result = world.on_occurrence(occ(
        "quest_deadline", "qd-2", 1441, payload={"quest_id": quest.quest_id},
    ))
    assert result["result"]["status"] == "failed"


def test_deadline_skipped_after_completion():
    world, _fakes = make_world()
    quest = _accept_and_begin(world, _offer(world, "q12"))
    for index in range(2):
        world.quests.submit_domain_event(_event(
            f"ev-c{index}", "item.delivered",
            {"resident_id": "resident.hero",
             "item_template_id": "item.supplies", "to": "resident.mayor"}), 10 + index)
    assert world.quests.get(quest.quest_id).state == "completed"
    # 完成事件 Revision 在先 → deadline 到达时跳过
    result = world.on_occurrence(occ(
        "quest_deadline", "qd-3", 99999, payload={"quest_id": quest.quest_id},
    ))
    assert result["result"]["status"] == "skipped"
    assert world.quests.get(quest.quest_id).state == "completed"


def test_rewards_granted_via_econ_only():
    world, fakes = make_world()
    quest = _accept_and_begin(world, _offer(world, "q13"))
    for index in range(2):
        world.quests.submit_domain_event(_event(
            f"ev-r{index}", "item.delivered",
            {"resident_id": "resident.hero",
             "item_template_id": "item.supplies", "to": "resident.mayor"}), 10 + index)
    assert len(fakes.econ.rewards) == 1
    reward = fakes.econ.rewards[0]
    assert reward["resident_id"] == "resident.hero"
    assert reward["reward_kind"] == "currency"
    assert reward["parameters"] == {"amount": 20}


def test_reward_failure_keeps_terminal_and_registers_aftermath():
    world, fakes = make_world()
    fakes.econ.fail_reward = True
    quest = _accept_and_begin(world, _offer(world, "q14"))
    for index in range(2):
        world.quests.submit_domain_event(_event(
            f"ev-f{index}", "item.delivered",
            {"resident_id": "resident.hero",
             "item_template_id": "item.supplies", "to": "resident.mayor"}), 10 + index)
    quest = world.quests.get(quest.quest_id)
    # 终态不回滚；善后任务登记
    assert quest.state == "completed"
    assert quest.rewards_granted is False
    tasks = world.aftermath.all()
    assert len(tasks) == 1
    assert tasks[0].task_kind == "compensation"
    assert tasks[0].parameters["quest_id"] == quest.quest_id


def test_protect_target_objective():
    world, _fakes = make_world()
    world.quest_templates.register(type(world.quest_templates.get(
        "quest.deliver.supplies"))(
        quest_template_id="quest.test.protect",
        name="守护测试",
        objectives=(
            ObjectiveSpec("escort", "reach_location", {"location_id": "loc.safe"}),
            ObjectiveSpec("guard", "protect_target", {"target_id": "npc.vip"}),
        ),
        objective_ordering="parallel",
        participant_roles={},
    ))
    world.quests.protect_target_alive = lambda target: target == "npc.vip"
    quest = _accept_and_begin(world, _offer(
        world, "q15", template_id="quest.test.protect", participants={}))
    world.quests.submit_domain_event(_event(
        "ev-escort", "movement.arrived",
        {"resident_id": "resident.hero", "location_id": "loc.safe"}), 10)
    quest = world.quests.get(quest.quest_id)
    assert quest.objective_progress["escort"].done
    assert quest.objective_progress["guard"].done  # 目标存活 → 守护判定完成
    assert quest.state == "completed"


def test_maintain_condition_objective():
    world, _fakes = make_world()
    world.quest_templates.register(type(world.quest_templates.get(
        "quest.deliver.supplies"))(
        quest_template_id="quest.test.maintain",
        name="维持测试",
        objectives=(
            ObjectiveSpec("setup", "reach_location", {"location_id": "loc.post"}),
            ObjectiveSpec("hold", "maintain_condition",
                          {"projection_path": "public.order", "at_least": 1}),
        ),
        participant_roles={},
    ))
    world.quests.maintain_condition_holds = lambda params: True
    quest = _accept_and_begin(world, _offer(
        world, "q16", template_id="quest.test.maintain", participants={}))
    world.quests.submit_domain_event(_event(
        "ev-setup", "movement.arrived",
        {"resident_id": "resident.hero", "location_id": "loc.post"}), 10)
    assert world.quests.get(quest.quest_id).state == "completed"
