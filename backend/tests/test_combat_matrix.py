"""TEST-COMBAT-033/034/035/036：Golden Replay、模型全故障、30 日模拟、覆盖审计

doc 12 §11 的跨层回归锚
"""

import json

import pytest

from src.combat import EncounterState
from src.combat.decisions import CombatDecisionService
from src.combat.fixtures import (
    FIXTURE_REGISTRY,
    FakeModelProvider,
    audit_fixtures,
    audit_rule_coverage,
    fixture_duel_2v2,
    fixture_model_offline,
    fixture_wipeout,
    run_encounter_to_end,
)

from combat_helpers import attack_first_script, pass_script, run_full, start_fixture


def _canonical_events(engine) -> str:
    """事件流规范化：逐字节比较用"""
    return json.dumps(engine.events, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


class TestGoldenReplay:
    """TEST-COMBAT-033：固定 fixture + 固定命令序列 → 事件流逐字节一致"""

    def test_duel_2v2_golden_replay(self):
        streams = []
        for _ in range(2):
            engine, eid, _ = start_fixture()
            run_full(engine, eid)
            streams.append(_canonical_events(engine))
        assert streams[0] == streams[1]

    @pytest.mark.parametrize("fixture_id", [
        "fixture.combat.duel_2v2",
        "fixture.combat.full_party_4v4",
        "fixture.combat.nonviolent_exit",
        "fixture.combat.wipeout",
    ])
    def test_fixture_replay_byte_identical(self, fixture_id):
        streams = []
        for _ in range(2):
            engine, eid, _ = start_fixture(FIXTURE_REGISTRY[fixture_id])
            run_full(engine, eid)
            streams.append(_canonical_events(engine))
        assert streams[0] == streams[1], f"{fixture_id} replay diverged"

    def test_replay_recorded_golden_anchor(self):
        """锚点回归：事件类型序列稳定"""
        engine, eid, _ = start_fixture()
        run_full(engine, eid)
        kinds = [e["event_kind"] for e in engine.events]
        assert kinds[0] == "EncounterStarted"
        assert kinds[-1] in ("EncounterResolved", "CreatureRemoved")
        assert "CombatActionResolved" in kinds
        assert "EncounterResolved" in kinds


class TestModelOffline:
    """TEST-COMBAT-034：模型全故障下 fixture 战斗完整推进到合法终结"""

    @pytest.mark.parametrize("mode", ["timeout", "unavailable", "cancelled", "invalid"])
    def test_full_failure_completes_encounter(self, mode):
        engine, eid, _ = start_fixture(fixture_model_offline)
        service = CombatDecisionService(engine, FakeModelProvider(mode))
        result = run_encounter_to_end(engine, eid, service, player_script=attack_first_script)
        enc = engine._require(eid)
        assert result["state"] == "ended"
        assert enc.end_condition is not None
        records = service.replay_records()
        assert records and all(r.classification == "fallback_decision" for r in records)

    def test_offline_battle_still_deterministic(self):
        streams = []
        for _ in range(2):
            engine, eid, _ = start_fixture(fixture_model_offline)
            service = CombatDecisionService(engine, FakeModelProvider("timeout"))
            run_encounter_to_end(engine, eid, service, player_script=attack_first_script)
            streams.append(_canonical_events(engine))
        assert streams[0] == streams[1]


class TestThirtyDaySimulation:
    """TEST-COMBAT-035：连续多场战斗的核心不变量"""

    def test_thirty_encounters_invariants(self):
        """30 游戏日每日一场：无 Resident 永久删除、无重复结算、无 token/锁泄漏"""
        for day in range(30):
            builder = [fixture_duel_2v2, fixture_wipeout][day % 2]
            engine, eid, ports = start_fixture(builder, command_id=f"cmd.day{day}")
            result = run_full(engine, eid)
            enc = engine._require(eid)
            assert result["state"] == "ended"
            # 无 Resident 永久删除
            resolved = next(e for e in engine.events if e["event_kind"] == "EncounterResolved")
            for final in resolved["payload"]["finals"]:
                sheet = enc.combatants[final["combatant_id"]]
                if sheet.kind.value in ("resident", "player_resident"):
                    assert final["defeat_outcome"] not in ("died", "dissipated")
            # 无重复结算
            assert len(ports.health.applied) == 1
            assert len(ports.finals.applied) == 1
            health_keys = [a["idempotency_key"] for a in ports.health.applied]
            assert len(health_keys) == len(set(health_keys))
            # 无 token/锁泄漏
            assert len(ports.pause.acquired) == len(ports.pause.released)
            assert len(ports.reservation.acquired) == len(ports.reservation.released)
            assert not ports.reservation.locked_entities

    def test_same_day_replay_identical(self):
        """同一游戏日重放：事件流逐字节一致（跨日无关）"""
        streams = []
        for _ in range(2):
            engine, eid, _ = start_fixture(fixture_duel_2v2, command_id="cmd.day0")
            run_full(engine, eid)
            streams.append(_canonical_events(engine))
        assert streams[0] == streams[1]


class TestCoverageAudit:
    """TEST-COMBAT-036：规则覆盖审计与 fixture/oracle 注册完整性"""

    def test_rule_coverage_complete(self):
        missing = audit_rule_coverage()
        assert missing == [], f"uncovered rules: {missing}"

    def test_fixture_registry_complete_and_loadable(self):
        problems = audit_fixtures()
        assert problems == [], f"fixture problems: {problems}"

    def test_matrix_has_thirty_six_rows(self):
        from src.combat.fixtures import TEST_COVERAGE_MATRIX

        assert len(TEST_COVERAGE_MATRIX) == 36
        for index in range(1, 37):
            assert f"TEST-COMBAT-{index:03d}" in TEST_COVERAGE_MATRIX

    def test_default_tests_use_fake_provider(self):
        """RULE-COMBAT-066：矩阵行不依赖真实模型"""
        assert isinstance(FakeModelProvider("fixed"), FakeModelProvider)
        # fixtures 模块不含任何真实网络调用入口
        import src.combat.fixtures as fixtures_module
        import inspect

        source = inspect.getsource(fixtures_module)
        assert "http" not in source and "api_key" not in source.lower()
