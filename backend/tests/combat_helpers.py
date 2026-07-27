"""COMBAT 测试共享夹具：fixture 启动、脚本驱动与通用断言"""

from typing import Dict, Optional, Tuple

from src.combat import (
    CombatEngine,
    CombatEngineError,
    EncounterState,
    Side,
)
from src.combat.decisions import CombatDecisionService
from src.combat.fixtures import (
    FIXTURE_REGISTRY,
    FakeModelProvider,
    FakePorts,
    fixture_duel_2v2,
    run_encounter_to_end,
)


def start_fixture(builder=fixture_duel_2v2, command_id: str = "cmd.start") -> Tuple[CombatEngine, str, FakePorts]:
    """构建 fixture 并启动遭遇；返回 (engine, encounter_id, ports)"""
    engine, payload, ports = builder()
    result = engine.start_encounter(command_id, payload)
    return engine, result["encounter_id"], ports


def attack_first_script(eng: CombatEngine, eid: str) -> None:
    """玩家脚本：优先 attack 第一个合法目标，否则 defend，再否则 pass"""
    enc = eng._require(eid)
    options = enc.options_cache[enc.turn_index]
    for option in options:
        if option.kind.value == "attack" and option.legal_target_sets:
            eng.submit_combat_action(
                f"player:{enc.turn_index}", eid, enc.turn_index,
                option.option_id, [option.legal_target_sets[0].combatant_ids[0]],
            )
            return
    for option in options:
        if option.kind.value == "defend":
            eng.submit_combat_action(f"player:{enc.turn_index}", eid, enc.turn_index, option.option_id, [])
            return
    option = options[0]
    targets = []
    if option.legal_target_sets:
        targets = [option.legal_target_sets[0].combatant_ids[0]]
    eng.submit_combat_action(f"player:{enc.turn_index}", eid, enc.turn_index, option.option_id, targets)


def pass_script(eng: CombatEngine, eid: str) -> None:
    """玩家脚本：永远 pass（round_cap fixture 用）"""
    enc = eng._require(eid)
    eng.submit_combat_action(
        f"player:{enc.turn_index}", eid, enc.turn_index, "combat_option.pass", []
    )


class PassProvider:
    """AI 决策 provider：永远选择 pass（round_cap fixture 用）"""

    def complete(self, *, model_id, prompt_id, context, deadline_ms) -> str:
        import json

        return json.dumps({
            "encounter_id": context["encounter_id"],
            "turn_index": context["turn_index"],
            "action_option_id": "combat_option.pass",
            "target_combatant_ids": [],
            "negotiation_term_id": None,
        })


def run_full(
    engine: CombatEngine,
    eid: str,
    provider_mode: str = "fixed",
    player_script=attack_first_script,
) -> Dict:
    """以指定 provider 模式跑完整场并 Resolve"""
    service = CombatDecisionService(engine, FakeModelProvider(provider_mode))
    return run_encounter_to_end(engine, eid, service, player_script=player_script)


def enemy_ids(engine: CombatEngine, eid: str, side: Side) -> list:
    enc = engine._require(eid)
    return [c.combatant_id for c in enc.members_of(side)]


def assert_error_code(exc_info, code: str) -> None:
    assert isinstance(exc_info.value, CombatEngineError)
    assert exc_info.value.code == code
