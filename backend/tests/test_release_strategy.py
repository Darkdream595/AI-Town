"""TEST-RELEASE-041..044：项目测试策略（DOC-RELEASE-011）"""
from __future__ import annotations

from src.persistence import gates


class TestLayerCompletenessAndModelPolicy:  # TEST-RELEASE-041：
    # RULE-RELEASE-079/080
    def test_eight_layers_fixed(self):
        names = [layer["layer"] for layer in gates.TEST_LAYERS]
        assert names == ["Unit", "Property", "Contract", "Integration",
                         "Simulation", "Browser E2E", "Visual QA",
                         "Packaged Release"]
        assert all(layer["trigger"] for layer in gates.TEST_LAYERS)

    def test_layer_triggers_cover_commit_nightly_rc(self):
        triggers = " ".join(layer["trigger"] for layer in gates.TEST_LAYERS)
        assert "per-commit" in triggers
        assert "nightly" in triggers
        assert "release-candidate" in triggers

    def test_real_model_default_off(self, monkeypatch):
        monkeypatch.delenv("AI_TOWN_REAL_MODEL", raising=False)
        assert gates.real_model_enabled() is False

    def test_real_model_explicit_one_only(self):
        assert gates.real_model_enabled({"AI_TOWN_REAL_MODEL": "1"}) is True
        for other in ("0", "true", "yes", "2", ""):
            assert gates.real_model_enabled(
                {"AI_TOWN_REAL_MODEL": other}) is False


class TestSim30Gate:  # TEST-RELEASE-042：RULE-RELEASE-081/082
    def _passing_metrics(self) -> dict:
        return {
            "process_rss_max_mib": 2048,
            "queue_depth_bounded": {"ai_requests": 64,
                                    "websocket_outbox": 1024,
                                    "long_actions": 256},
            "economy_conservation_violations": 0,
            "resident_stuck_max_game_hours": 6,
            "relationship_drift_abs_max": 40,
            "active_quests_max": 24,
            "world_storage_growth_max_mib": 512,
            "invariant_violations": 0,
            "unrecovered_crash_injections": 0,
        }

    def test_gate_structure_nine_checks(self):
        assert len(gates.SIM30_GATE["checks"]) == 9
        metrics = {c["metric"] for c in gates.SIM30_GATE["checks"]}
        assert metrics == set(gates.SIM30_GATE["thresholds"])
        assert gates.SIM30_GATE["seed_policy"] == "fixed_seed_fixed_fixture"

    def test_all_pass_returns_no_violations(self):
        assert gates.evaluate_sim30(self._passing_metrics()) == []

    def test_single_excess_fails(self):
        metrics = self._passing_metrics()
        metrics["process_rss_max_mib"] = 2049
        assert gates.evaluate_sim30(metrics) == ["sim30.memory"]

    def test_zero_tolerance_not_averaged(self):
        """守恒/不变量/crash 恢复任一出现即整套失败，不得以均值抵消"""
        for metric, check_id in (
                ("economy_conservation_violations", "sim30.economy"),
                ("invariant_violations", "sim30.invariants"),
                ("unrecovered_crash_injections", "sim30.crash")):
            metrics = self._passing_metrics()
            metrics[metric] = 1
            assert gates.evaluate_sim30(metrics) == [check_id]

    def test_queue_depth_dict_bounds(self):
        metrics = self._passing_metrics()
        metrics["queue_depth_bounded"] = {
            "ai_requests": 65,  # 超 64 上限
            "websocket_outbox": 10,
            "long_actions": 10,
        }
        assert gates.evaluate_sim30(metrics) == ["sim30.queues"]

    def test_missing_metric_marked(self):
        metrics = self._passing_metrics()
        del metrics["world_storage_growth_max_mib"]
        violations = gates.evaluate_sim30(metrics)
        assert violations == ["sim30.storage:missing"]

    def test_multiple_violations_all_listed(self):
        metrics = self._passing_metrics()
        metrics["process_rss_max_mib"] = 9999
        metrics["active_quests_max"] = 25
        violations = gates.evaluate_sim30(metrics)
        assert set(violations) == {"sim30.memory", "sim30.quests"}


class TestCrashMatrixAndE2E:  # TEST-RELEASE-043：RULE-RELEASE-083/084
    def test_crash_injection_points_fixed(self):
        assert gates.CRASH_INJECTION_POINTS == (
            "transaction_pre_commit",
            "transaction_post_commit",
            "snapshot_write_midway",
            "migration_between_steps",
            "branch_on_load_between_steps",
            "shutdown_sequence_stages",
        )

    def test_crash_points_cover_spec_stages(self):
        """事务提交前后、Snapshot 写入中、迁移 Step 间、branch-on-load 间、
        关闭序列各阶段——六类齐全"""
        assert len(gates.CRASH_INJECTION_POINTS) == 6
        joined = " ".join(gates.CRASH_INJECTION_POINTS)
        for stage in ("pre_commit", "post_commit", "snapshot", "migration",
                      "branch_on_load", "shutdown"):
            assert stage in joined

    def test_e2e_scenarios_exactly_fourteen(self):
        assert gates.E2E_SCENARIOS == (
            "启动进入", "创建世界", "角色移动", "碰撞阻挡", "对话交流",
            "进入室内", "地图切换", "镇长模式", "建筑建造", "回合战斗",
            "手动存档", "刷新恢复", "全屏提示与切换", "保存退出")
        assert len(gates.E2E_SCENARIOS) == 14

    def test_e2e_scenarios_unique(self):
        assert len(set(gates.E2E_SCENARIOS)) == len(gates.E2E_SCENARIOS)


class TestFailureDiscipline:  # TEST-RELEASE-044：RULE-RELEASE-085
    def test_g9_requires_full_rc_suite_green(self):
        """任何一层缺失/跳过即 RC Suite 不通过，G9 不得开始"""
        assert gates.G9_CHECKLIST["requires"] == [
            "release-candidate-suite-green"]

    def test_g9_check_ids_unique_and_numbered(self):
        ids = [c["check_id"] for c in gates.G9_CHECKLIST["checks"]]
        assert len(ids) == 18
        assert len(set(ids)) == 18
        assert ids == [f"G9-CHK-{index:03d}" for index in range(1, 19)]

    def test_g9_check_modes_registered(self):
        for check in gates.G9_CHECKLIST["checks"]:
            assert check["mode"] in ("auto", "manual")
            assert check["title"]

    def test_sim30_gate_versioned(self):
        """门槛机器可读且版本化（变更即文档变更）"""
        assert gates.SIM30_GATE["simulation_gate_version"]
        assert gates.G9_CHECKLIST["checklist_version"]

    def test_outcome_missing_is_failure_not_skip(self):
        """未执行项视同失败——不存在 skip 通过通道"""
        record = gates.build_acceptance_record(
            package_version="0.1.0", build_id="abc",
            executed_at="2026-07-28T00:00:00.000Z",
            environments=[])  # 零环境 = 全部未执行
        assert record["outcome"] == "fail"
