"""TEST-RELEASE-045..048：发布验收清单（DOC-RELEASE-012）"""
from __future__ import annotations

from src.persistence import gates, release_manifest

ALL_CHECK_IDS = [c["check_id"] for c in gates.G9_CHECKLIST["checks"]]
ALL_ENV_IDS = [e["env_id"] for e in gates.ENV_MATRIX]


def _passing_environments() -> list:
    """构造 5 环境 × 18 检查全 pass（含证据）的验收记录输入"""
    return [{
        "env_id": env_id,
        "machine": f"MACHINE-{env_id}",
        "executor": "tester",
        "results": [{"check_id": check_id, "result": "pass",
                     "evidence": f"evidence/{env_id}/{check_id}.log"}
                    for check_id in ALL_CHECK_IDS],
    } for env_id in ALL_ENV_IDS]


class TestCleanMachineAndEnvMatrix:  # TEST-RELEASE-045：
    # RULE-RELEASE-086/087
    def test_env_matrix_has_five_combos(self):
        assert ALL_ENV_IDS == ["ENV-1", "ENV-2", "ENV-3", "ENV-4", "ENV-5"]

    def test_env_matrix_covers_win10_and_win11(self):
        os_set = {e["os"] for e in gates.ENV_MATRIX}
        assert any("Windows 10" in os_name for os_name in os_set)
        assert any("Windows 11" in os_name for os_name in os_set)

    def test_env_matrix_mandatory_combinations(self):
        """强制包含：中文用户名、中文+空格路径、桌面路径"""
        chinese_user = [e for e in gates.ENV_MATRIX if e["user"] == "中文"]
        assert chinese_user, "必须有中文用户名组合"
        paths = [e["path"] for e in gates.ENV_MATRIX]
        assert any("游戏 测试" in p and "AI 小镇" in p for p in paths), \
            "必须有含中文与空格的安装路径"
        assert any("Desktop" in p for p in paths), "必须有桌面路径"

    def test_env_matrix_second_start_scenario(self):
        """ENV-5：二次启动/停止脚本/卸载场景组合"""
        env5 = gates.ENV_MATRIX[4]
        assert "二次启动" in env5["path"]
        assert "卸载" in env5["path"]

    def test_clean_machine_detects_dev_tools(self):
        polluted = gates.assert_clean_machine([
            r"C:\Windows\System32",
            r"C:\Python311\Scripts",
            r"C:\Program Files\nodejs",
            r"C:\Users\dev\AppData\Local\Programs\Git\cmd",
        ])
        assert len(polluted) == 3
        assert r"C:\Windows\System32" not in polluted

    def test_clean_machine_accepts_clean_path(self):
        assert gates.assert_clean_machine([
            r"C:\Windows\System32",
            r"C:\Windows",
            r"C:\Program Files\Common Files",
        ]) == []


class TestRecordCompletenessAndStartupBudget:  # TEST-RELEASE-046：
    # RULE-RELEASE-088/089
    def test_all_pass_record_passes(self):
        record = gates.build_acceptance_record(
            package_version="0.1.0", build_id="abc123",
            executed_at="2026-07-28T00:00:00.000Z",
            environments=_passing_environments())
        assert record["outcome"] == "pass"

    def test_missing_check_fails(self):
        envs = _passing_environments()
        envs[0]["results"] = envs[0]["results"][1:]  # 缺 G9-CHK-001
        summary = gates.summarize_outcome(
            {"environments": envs})
        assert summary["outcome"] == "fail"
        assert "ENV-1:G9-CHK-001:missing" in summary["failed"]

    def test_fail_result_fails(self):
        envs = _passing_environments()
        envs[2]["results"][4] = {"check_id": "G9-CHK-005", "result": "fail",
                                 "evidence": "ev.log"}
        summary = gates.summarize_outcome({"environments": envs})
        assert summary["outcome"] == "fail"
        assert "ENV-3:G9-CHK-005:fail" in summary["failed"]

    def test_pass_without_evidence_fails(self):
        """RULE-RELEASE-088：每条 Check 必须记录 Evidence 引用"""
        envs = _passing_environments()
        envs[1]["results"][0] = {"check_id": "G9-CHK-001", "result": "pass",
                                 "evidence": ""}
        summary = gates.summarize_outcome({"environments": envs})
        assert summary["outcome"] == "fail"
        assert "ENV-2:G9-CHK-001:pass" in summary["failed"]

    def test_absent_environment_listed(self):
        envs = _passing_environments()[:3]  # 缺 ENV-4/ENV-5
        summary = gates.summarize_outcome({"environments": envs})
        assert summary["outcome"] == "fail"
        assert "ENV-4:absent" in summary["failed"]
        assert "ENV-5:absent" in summary["failed"]

    def test_startup_budgets(self):
        """RULE-RELEASE-089：冷启动 ≤ 60 s、二次启动 ≤ 20 s"""
        assert gates.STARTUP_BUDGETS["cold_start_max_seconds"] == 60
        assert gates.STARTUP_BUDGETS["second_start_max_seconds"] == 20


class TestVersionTripletAndPostSessionScan:  # TEST-RELEASE-047：
    # RULE-RELEASE-090/091
    def test_version_triplet_match(self):
        manifest = {"package_version": "1.0.0", "build_id": "c0ffee"}
        runtime = {"package_version": "1.0.0", "build_id": "c0ffee"}
        result = release_manifest.verify_version_triplet(
            manifest, runtime, "c0ffee")
        assert result["ok"] is True
        assert result["package_version_match"] is True
        assert result["build_id_match"] is True

    def test_version_triplet_manifest_runtime_mismatch(self):
        result = release_manifest.verify_version_triplet(
            {"package_version": "1.0.0", "build_id": "c0ffee"},
            {"package_version": "1.0.1", "build_id": "c0ffee"}, "c0ffee")
        assert result["ok"] is False
        assert result["package_version_match"] is False

    def test_version_triplet_source_commit_mismatch(self):
        """构建源 commit 不符即 fail（防发布包非最新代码）"""
        result = release_manifest.verify_version_triplet(
            {"package_version": "1.0.0", "build_id": "c0ffee"},
            {"package_version": "1.0.0", "build_id": "c0ffee"}, "other-commit")
        assert result["ok"] is False
        assert result["build_id_match"] is False

    def test_post_session_scan_check_registered(self):
        """RULE-RELEASE-091：会话后 Canary 扫描为强制 Check"""
        check = next(c for c in gates.G9_CHECKLIST["checks"]
                     if c["check_id"] == "G9-CHK-011")
        assert "Canary" in check["title"] or "canary" in check["title"].lower()
        assert "Secret 扫描" in check["title"]


class TestAcceptanceRecordArchival:  # TEST-RELEASE-048：RULE-RELEASE-092
    def test_record_format_and_fields(self):
        record = gates.build_acceptance_record(
            package_version="1.0.0", build_id="abc123",
            executed_at="2026-07-28T12:00:00.000Z",
            environments=_passing_environments())
        assert record["record_format_version"] == 1
        assert record["gate"] == "G9"
        assert record["package_version"] == "1.0.0"
        assert record["build_id"] == "abc123"
        assert record["executed_at"] == "2026-07-28T12:00:00.000Z"
        assert len(record["environments"]) == 5
        assert record["outcome"] == "pass"

    def test_rerun_preserves_trace(self):
        """重跑生成新 Record 并保留旧 Record 引用与原因，不覆盖历史"""
        first = gates.build_acceptance_record(
            package_version="1.0.0", build_id="abc123",
            executed_at="2026-07-27T09:00:00.000Z",
            environments=_passing_environments()[:4])
        assert first["outcome"] == "fail"
        second = gates.build_acceptance_record(
            package_version="1.0.0", build_id="abc123",
            executed_at="2026-07-28T09:00:00.000Z",
            environments=_passing_environments(),
            rerun_of="record-20260727", rerun_reason="ENV-5 缺席，补测")
        assert second["rerun_of"] == "record-20260727"
        assert second["rerun_reason"] == "ENV-5 缺席，补测"
        assert second["outcome"] == "pass"
        # 首跑记录字段未被修改
        assert first["rerun_of"] is None

    def test_partial_environment_failure_summary(self):
        """任一环境 fail 即整体 fail 并列出全部失败项"""
        envs = _passing_environments()
        envs[4]["results"][13] = {"check_id": "G9-CHK-014",
                                  "result": "fail", "evidence": "ev.log"}
        record = gates.build_acceptance_record(
            package_version="1.0.0", build_id="abc123",
            executed_at="2026-07-28T12:00:00.000Z", environments=envs)
        assert record["outcome"] == "fail"
        summary = gates.summarize_outcome(record)
        assert summary["failed"] == ["ENV-5:G9-CHK-014:fail"]
