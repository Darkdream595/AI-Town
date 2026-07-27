"""TEST-EVENT-007..009：AI Director（DOC-EVENT-003）"""

import pytest

from src.events import (
    DIRECTOR_MODEL,
    DIRECTOR_PROMPT_ID,
    DirectorError,
    validate_proposal,
)
from src.events.director import WorldSummaryProjectionBuilder
from event_helpers import activate_event, make_world, occ
from src.events.fixtures import SCENE_TOWN


def _projection(game_time=0):
    return {"scene_id": SCENE_TOWN, "game_time": game_time,
            "public": {"harvest_stock": 150}}


def _review(world, key, game_time, projection=None):
    return world.on_occurrence(occ(
        "director_review", key, game_time,
        projection=projection or _projection(game_time),
    ))


def _valid_proposal(template_id="event.festival.harvest", parameters=None):
    return {
        "proposal_kind": "world_event",
        "event_template_id": template_id,
        "parameters": parameters if parameters is not None else {},
        "narrative_reason": "丰收在望，镇民期待庆典",
    }


# -- TEST-EVENT-007：投影白名单与提案管线 --------------------------------------


def test_empty_whitelist_skips_without_model_call():
    world, fakes = make_world()
    world.director_whitelist = type(world.director_whitelist)()  # 清空
    world.director._whitelist = world.director_whitelist
    result = _review(world, "dr-1", 0)
    assert result["result"]["status"] == "skipped"
    assert result["result"]["reason"] == "whitelist_empty"
    assert fakes.director_model.calls == []


def test_valid_proposal_instantiates_event():
    world, fakes = make_world()
    fakes.director_model.push(_valid_proposal())
    result = _review(world, "dr-2", 0)
    assert result["result"]["status"] == "accepted"
    event = world.engine.get(result["result"]["world_event_id"])
    assert event.source == "director"
    assert event.state == "active"
    assert event.source_evidence_id == "dr-2"


def test_model_call_meta_prompt_model_thinking_effort():
    world, fakes = make_world()
    fakes.director_model.push(None)
    _review(world, "dr-3", 0)
    assert len(fakes.director_model.calls) == 1
    call = fakes.director_model.calls[0]
    assert call["prompt_id"] == DIRECTOR_PROMPT_ID == "event-director/v1"
    assert call["model"] == DIRECTOR_MODEL == "deepseek-v4-flash"
    assert call["thinking"] is True
    assert call["reasoning_effort"] == "high"


def test_model_none_proposal_is_success_no_event():
    world, fakes = make_world()
    fakes.director_model.push(None)
    result = _review(world, "dr-4", 0)
    assert result["result"]["status"] == "no_proposal"
    assert world.engine.all() == []


def test_model_unavailable_counts_failure():
    world, fakes = make_world()
    fakes.director_model.unavailable = True
    result = _review(world, "dr-5", 0)
    assert result["result"]["status"] == "failed"
    assert result["result"]["code"] == "model_unavailable"
    assert world.director._consecutive_failures == 1


def test_projection_builder_rejects_non_public_fields():
    builder = WorldSummaryProjectionBuilder()
    with pytest.raises(DirectorError) as exc:
        builder.register_field("memory.private_thoughts", lambda: "x")
    assert exc.value.code == "projection_field_forbidden"
    builder.register_field("public.harvest_stock", lambda: 150)
    projection = builder.build(42)
    assert projection["public"]["harvest_stock"] == 150
    assert projection["game_time"] == 42


def test_projection_stale_rejected():
    world, fakes = make_world()
    fakes.director_model.push(_valid_proposal())
    result = _review(world, "dr-6", 1000,
                     projection=_projection(game_time=100))
    assert result["result"]["status"] == "failed"
    assert result["result"]["code"] == "projection_stale"
    assert fakes.director_model.calls == []  # 陈旧投影不调模型


# -- TEST-EVENT-008：Schema 严格校验与白名单 ------------------------------------


def test_proposal_schema_validator():
    assert validate_proposal(_valid_proposal()) == []
    assert validate_proposal({"proposal_kind": "world_event"}) != []
    assert validate_proposal(_valid_proposal("bad_id")) != []
    assert validate_proposal({
        "proposal_kind": "resident_mind_control",
        "event_template_id": "event.festival.harvest",
        "parameters": {}, "narrative_reason": "x",
    }) != []
    assert validate_proposal({
        "proposal_kind": "world_event",
        "event_template_id": "event.festival.harvest",
        "parameters": {}, "narrative_reason": "x" * 501,
    }) != []
    assert validate_proposal({
        "proposal_kind": "world_event",
        "event_template_id": "event.festival.harvest",
        "parameters": [], "narrative_reason": "ok",
    }) != []


def test_extra_field_repaired_once_then_accepted():
    world, fakes = make_world()
    proposal = _valid_proposal()
    proposal["rogue_field"] = "inject"
    fakes.director_model.push(proposal)
    result = _review(world, "dr-7", 0)
    assert result["result"]["status"] == "accepted"


def test_unrepairable_schema_fails():
    world, fakes = make_world()
    proposal = _valid_proposal("not.an.id")
    fakes.director_model.push(proposal)
    result = _review(world, "dr-8", 0)
    assert result["result"]["status"] == "failed"
    assert result["result"]["code"] == "proposal_schema_invalid"


def test_template_not_whitelisted():
    world, fakes = make_world()
    # dragon 已注册但不在 Director 白名单
    fakes.director_model.push(_valid_proposal("event.crisis.dragon"))
    result = _review(world, "dr-9", 0)
    assert result["result"]["status"] == "failed"
    assert result["result"]["code"] == "template_not_whitelisted"


def test_template_parameters_invalid():
    world, fakes = make_world()
    fakes.director_model.push(_valid_proposal(parameters={"rogue": 1}))
    result = _review(world, "dr-10", 0)
    assert result["result"]["status"] == "failed"
    assert result["result"]["code"] == "template_parameters_invalid"


# -- TEST-EVENT-009：同权、频率上限、退避 ----------------------------------------


def test_director_has_no_privilege_budget():
    world, fakes = make_world()
    # 预算占满 12：crisis 8 + major 4
    activate_event(world, "p1", template_id="event.crisis.dragon",
                   source="admin", admin=True)
    activate_event(world, "p2", template_id="event.disaster.forest_fire",
                   source="environment", admin=False, parameters={"origin": "x"},
                   scope={"scene_id": "region.twilight_whisper_forest"})
    fakes.director_model.push(_valid_proposal())
    result = _review(world, "dr-11", 0)
    assert result["result"]["status"] == "failed"
    assert result["result"]["code"] == "budget_exceeded"


def test_interval_enforcement():
    world, fakes = make_world()
    fakes.director_model.push(None)
    _review(world, "dr-12", 0)
    result = _review(world, "dr-13", 100)  # < 360 间隔
    assert result["result"]["status"] == "skipped"
    assert result["result"]["reason"] == "interval_not_due"


def test_daily_cap_four_proposals():
    world, fakes = make_world()
    for index in range(4):
        fakes.director_model.push(_valid_proposal())
        result = _review(world, f"dr-day-{index}", index * 360)
        assert result["result"]["status"] == "accepted", index
        # 归档释放并发/预算，隔离出纯每日上限约束
        event = world.engine.get(result["result"]["world_event_id"])
        world.engine.transition(event.world_event_id, "resolved", index * 360 + 1,
                                expected_version=event.version)
        event = world.engine.get(event.world_event_id)
        world.engine.transition(event.world_event_id, "aftermath", index * 360 + 2,
                                expected_version=event.version)
        event = world.engine.get(event.world_event_id)
        world.engine.transition(event.world_event_id, "archived", index * 360 + 3,
                                expected_version=event.version)
    # 同日第 5 次（白盒对齐间隔）：每日 Director 来源上限 4
    world.director._last_review_time = 1000
    fakes.director_model.push(_valid_proposal())
    result = _review(world, "dr-day-5", 1360)
    assert result["result"]["status"] == "skipped"
    assert result["result"]["reason"] == "daily_cap_reached"
    assert fakes.director_model.queue != []  # 未消费提案


def test_consecutive_failures_extend_interval():
    world, fakes = make_world()
    fakes.director_model.unavailable = True
    for index in range(3):
        result = _review(world, f"dr-fail-{index}", index * 360)
        assert result["result"]["code"] == "model_unavailable"
    assert world.director._interval == 1440
    # 退避期内跳过
    fakes.director_model.unavailable = False
    fakes.director_model.push(None)
    result = _review(world, "dr-fail-4", 3 * 360 + 100)
    assert result["result"]["status"] == "skipped"
    # 1440 后恢复评审；成功一次 → 间隔回到 360
    result = _review(world, "dr-fail-5", 3 * 360 + 1440)
    assert result["result"]["status"] == "no_proposal"
    assert world.director._interval == 360


def test_review_idempotent_by_occurrence_key():
    world, fakes = make_world()
    fakes.director_model.push(_valid_proposal())
    first = _review(world, "dr-14", 0)
    second = _review(world, "dr-14", 0)
    assert first["status"] == "processed"
    assert second["status"] == "replayed"
    assert len(world.engine.all()) == 1
