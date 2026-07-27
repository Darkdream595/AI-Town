"""
TEST-MAGIC-017..018：玩家施法（DOC-MAGIC-008）

- TEST-MAGIC-017：玩家/AI 同管线等价；镇长/Admin/自由文本旁路反例
- TEST-MAGIC-018：拒绝反馈映射完整性与幂等重发
"""

import pytest

from src.magic import (
    CAST_REASON_CODES,
    CastingError,
    PlayerCastingError,
    PlayerCastingService,
    PlayerCastSpellCommand,
    feedback_coverage_complete,
    feedback_for,
)

from magic_helpers import command, learn, make_engine


def _player_command(env, **overrides):
    payload = {
        "command_id": "pcmd.1",
        "world_id": "world.test",
        "expected_revision": env.engine.revision,
        "actor_resident_id": "r.a",
        "spell_id": "spell.restoration.minor_mend",
        "scene_id": "scene.town",
        "game_time": 0,
        "game_day": 0,
        "target_refs": ("r.b",),
        "authorization_event_ids": ("evt.consent",),
        "client_context": {
            "ui_source": "spell_panel",
            "client_predicted_legal": True,
            "declared_purpose": "healing",
        },
    }
    payload.update(overrides)
    return PlayerCastSpellCommand(**payload)


def test_magic_017_player_ai_verdict_equivalence():
    targets = {"r.b": {"scene_id": "scene.town", "position": {"x_wu": 10.0, "y_wu": 0.0}}}
    # 同一世界状态克隆两份，一份走玩家入口，一份走 AI 入口
    env_player = make_engine(targets=targets)
    env_ai = make_engine(targets=targets)
    for env in (env_player, env_ai):
        learn(env, "r.a", "spell.restoration.minor_mend")
        env.resident_port.set_hp("r.b", 40, 100)
    service = PlayerCastingService(env_player.engine)
    player_committed = service.cast(_player_command(env_player))
    ai_committed = env_ai.engine.commit_spell_cast(command(
        env_ai, "r.a", "spell.restoration.minor_mend", declared_purpose="healing",
        target_refs=("r.b",), authorization_event_ids=("evt.consent",),
    ))
    # REQ-MAGIC-015：同 verdict、同法律判定、同效果结算
    assert player_committed.legality is ai_committed.legality
    assert player_committed.effect_results == ai_committed.effect_results
    assert env_player.mana.get("r.a").mana_current == env_ai.mana.get("r.a").mana_current
    # 拒绝等价：双方都缺同意时得到同一 reason code
    denied_player = PlayerCastingService(env_player.engine)
    with pytest.raises(CastingError) as exc_player:
        denied_player.cast(_player_command(
            env_player, command_id="pcmd.2", authorization_event_ids=(),
        ))
    verdict_ai = env_ai.engine.validate_spell_cast(command(
        env_ai, "r.a", "spell.restoration.minor_mend", declared_purpose="healing",
        target_refs=("r.b",),
    ))
    assert exc_player.value.code == verdict_ai.reason_code == "MAGIC_CONSENT_MISSING"


def test_magic_017_bypass_counterexamples():
    env = make_engine()
    learn(env, "r.a", "spell.arcane.glowlight")
    service = PlayerCastingService(env.engine)
    pcmd = _player_command(env, spell_id="spell.arcane.glowlight", target_refs=(),
                           authorization_event_ids=())
    # RULE-MAGIC-041：镇长模式无 CasterState
    with pytest.raises(PlayerCastingError) as exc:
        service.cast_in_mayor_mode(pcmd)
    assert exc.value.code == "MAGIC_CASTER_UNKNOWN"
    # AdminCommand 不得代放法术
    with pytest.raises(PlayerCastingError) as exc2:
        service.cast_via_admin_command(pcmd)
    assert exc2.value.code == "magic_admin_bypass_forbidden"
    # RULE-MAGIC-042：自由文本本身不触发效果
    with pytest.raises(PlayerCastingError) as exc3:
        service.cast_via_freeform_text("对那个商人施放发光术")
    assert exc3.value.code == "magic_freeform_bypass_forbidden"
    # 三条旁路均无状态变化
    assert env.engine.revision == 0
    assert env.mana.get("r.a").mana_current == env.mana.get("r.a").mana_max


def test_magic_017_client_context_not_part_of_validation():
    env = make_engine()
    normalized = _player_command(
        env,
        client_context={"client_predicted_legal": False, "declared_purpose": "utility"},
    ).to_spell_cast_command()
    # client_context 只作遥测：归一化后不存在该字段
    assert not hasattr(normalized, "client_context")
    assert normalized.declared_purpose == "utility"


def test_magic_018_feedback_mapping_complete():
    # RULE-MAGIC-044：封闭 reason_code 全覆盖，不允许静默失败
    assert feedback_coverage_complete()
    for code in CAST_REASON_CODES:
        feedback = feedback_for(code)
        assert feedback["message_zh"]
        assert feedback["suggestion_zh"]
        assert feedback["reason_code"] == code
    # 成功与未知码的退化路径
    assert feedback_for(None)["message_zh"] == "施法成功。"
    unknown = feedback_for("magic_some_future_code")
    assert unknown["message_zh"] == "magic_some_future_code"


def test_magic_018_idempotent_resend_after_reconnect():
    targets = {"r.b": {"scene_id": "scene.town", "position": {"x_wu": 10.0, "y_wu": 0.0}}}
    env = make_engine(targets=targets)
    learn(env, "r.a", "spell.restoration.minor_mend")
    env.resident_port.set_hp("r.b", 40, 100)
    service = PlayerCastingService(env.engine)
    # 断线重连安全重发：同 command_id 不重复生效
    first = service.cast(_player_command(env))
    second = service.cast(_player_command(env))
    assert first is second
    hp_after = env.resident_port.hp[ "r.b"][0]
    assert hp_after == 40 + first.effect_results[0]["hp_delta"]
