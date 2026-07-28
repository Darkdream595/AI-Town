"""TEST-RELEASE-029..032：双击启动器（DOC-RELEASE-008）"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from release_helpers import make_utc_factory  # noqa: F401

from src.persistence import launcher, release_manifest

SKELETON_DIR = (Path(__file__).resolve().parents[2]
                / "release" / "package_skeleton")


class TestBatchDelegationAndSingleInstance:  # TEST-RELEASE-029：
    # RULE-RELEASE-055/056/057
    def test_skeleton_bat_files_exist(self):
        assert (SKELETON_DIR / "启动AI小镇.bat").is_file()
        assert (SKELETON_DIR / "停止AI小镇.bat").is_file()
        assert (SKELETON_DIR / "runtime" / "stop-ai-town.ps1").is_file()

    def test_start_bat_delegates_only(self):
        """RULE-RELEASE-055：chcp + %~dp0 委派，无注册表/管理员/参数解析"""
        result = release_manifest.check_bat_content(
            SKELETON_DIR / "启动AI小镇.bat")
        assert result["ok"] is True
        assert result["has_chcp"] is True
        assert result["delegates_with_dp0"] is True
        text = (SKELETON_DIR / "启动AI小镇.bat").read_text(encoding="utf-8")
        lowered = text.lower()
        assert "reg add" not in lowered and "regedit" not in lowered
        assert "runas" not in lowered and "net session" not in lowered
        # 委派目标为包内 Launcher
        assert 'start "" "%~dp0runtime\\backend\\AI-Town.exe"' in text

    def test_instance_record_fields_and_atomic_write(self, tmp_path):
        """RULE-RELEASE-057：端口/pid/started_at/package_version/
        shutdown_token 原子写入"""
        token = launcher.generate_shutdown_token()
        record = launcher.write_instance(
            tmp_path, pid=4321, port=51234, package_version="0.1.0",
            shutdown_token=token, utc_now=make_utc_factory())
        assert record["pid"] == 4321
        assert record["port"] == 51234
        assert record["url"] == "http://127.0.0.1:51234/"
        assert record["package_version"] == "0.1.0"
        assert record["shutdown_token"] == token
        assert record["started_at"].endswith("Z")
        assert not (tmp_path / "instance.json.tmp").exists()  # temp 已 rename
        # 本地回环 + OS 分配端口语义：URL 只含 127.0.0.1，无 0.0.0.0
        assert "0.0.0.0" not in json.dumps(record)

    def test_read_instance_rejects_format_mismatch(self, tmp_path):
        launcher.write_instance(tmp_path, pid=1, port=2,
                                package_version="0.1.0", shutdown_token="t" * 32)
        path = tmp_path / "instance.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["instance_format_version"] = 999
        path.write_text(json.dumps(record), encoding="utf-8")
        assert launcher.read_instance(tmp_path) is None

    def test_shutdown_token_is_csprng_hex_unique(self):
        tokens = {launcher.generate_shutdown_token() for _ in range(100)}
        assert len(tokens) == 100  # 每次启动独立生成
        assert all(len(t) == 32 for t in tokens)


class TestHealthPollingAndBrowserPolicy:  # TEST-RELEASE-030：
    # RULE-RELEASE-058/062
    def _poller(self, fetch, ticks):
        """假时钟：每次 monotonic 调用推进一步（毫秒）"""
        state = {"now": 0.0}

        def monotonic():
            return state["now"]

        def sleep(seconds):
            state["now"] += seconds
            ticks.append(seconds)

        return launcher.HealthPoller(fetch, sleep=sleep, monotonic=monotonic)

    def test_ready_with_matching_version_succeeds(self):
        responses = iter([
            {"process_state": "starting"},
            {"process_state": "ready", "package_version": "0.1.0"},
        ])
        ticks = []
        poller = self._poller(lambda: next(responses), ticks)
        result = poller.poll("0.1.0")
        assert result["outcome"] == "ready"
        assert result["attempts"] == 2
        assert ticks == [0.5]  # 500 ms 轮询间隔

    def test_error_state_stops_without_retry(self):
        ticks = []
        poller = self._poller(lambda: {"process_state": "error"}, ticks)
        result = poller.poll("0.1.0")
        assert result["outcome"] == "error"
        assert result["attempts"] == 1  # 不无限重试
        assert ticks == []

    def test_version_mismatch_keeps_polling_until_timeout(self):
        fetch = lambda: {"process_state": "ready",  # noqa: E731
                         "package_version": "0.0.9"}
        ticks = []
        poller = self._poller(fetch, ticks)
        result = poller.poll("0.1.0")
        assert result["outcome"] == "timeout"  # 版本不匹配不算 ready

    def test_ready_without_package_version_never_false_passes(self):
        """缺失版本字段不是兼容成功，避免启动器打开错误构建。"""
        ticks = []
        poller = self._poller(
            lambda: {"process_state": "ready"}, ticks)
        result = poller.poll("0.1.0")
        assert result["outcome"] == "timeout"

    def test_timeout_at_60_seconds(self):
        ticks = []
        poller = self._poller(lambda: None, ticks)
        result = poller.poll("0.1.0")
        assert result["outcome"] == "timeout"
        assert result["elapsed_ms"] >= 60_000
        assert all(t == 0.5 for t in ticks)

    def test_browser_url_is_loopback_root(self, tmp_path):
        """RULE-RELEASE-062：只打开默认浏览器指向 127.0.0.1 根路径"""
        record = launcher.write_instance(tmp_path, pid=1, port=45678,
                                         package_version="0.1.0",
                                         shutdown_token="t" * 32)
        assert record["url"] == "http://127.0.0.1:45678/"


class TestTrayExitAndStopScript:  # TEST-RELEASE-031：
    # RULE-RELEASE-059/060
    def test_stop_bat_delegates_to_ps1_without_taskkill(self):
        result = release_manifest.check_bat_content(
            SKELETON_DIR / "停止AI小镇.bat")
        assert result["ok"] is True
        assert result["no_taskkill"] is True
        text = (SKELETON_DIR / "停止AI小镇.bat").read_text(encoding="utf-8")
        assert "stop-ai-town.ps1" in text
        assert "%~dp0" in text

    def test_ps1_posts_shutdown_with_token_and_never_taskkill(self):
        text = (SKELETON_DIR / "runtime" / "stop-ai-town.ps1").read_text(
            encoding="utf-8")
        assert "/api/v1/shutdown" in text
        assert "shutdown_token" in text
        assert "instance.json" in text
        assert "15" in text  # 15 秒等待窗口
        lowered = text.lower()
        assert "taskkill" not in lowered
        assert "stop-process" not in lowered  # 绝不强杀
        assert "kill" not in lowered.replace("skill", "")

    def test_ps1_cleans_stale_instance_on_unreachable(self):
        """连接失败按陈旧实例清理（脚本注释与分支）"""
        text = (SKELETON_DIR / "runtime" / "stop-ai-town.ps1").read_text(
            encoding="utf-8")
        assert "Remove-Item $instancePath" in text
        assert "catch" in text

    def test_instance_lifecycle_write_read_delete(self, tmp_path):
        """RULE-RELEASE-059：正常退出删除 instance.json"""
        launcher.write_instance(tmp_path, pid=999, port=10000,
                                package_version="0.1.0",
                                shutdown_token=launcher.generate_shutdown_token())
        assert launcher.read_instance(tmp_path)["pid"] == 999
        assert launcher.delete_instance(tmp_path) is True
        assert launcher.read_instance(tmp_path) is None
        assert launcher.delete_instance(tmp_path) is False


class TestStaleInstanceCleanup:  # TEST-RELEASE-032：RULE-RELEASE-061
    def test_dead_pid_is_cleared(self, tmp_path):
        launcher.write_instance(tmp_path, pid=4242, port=10001,
                                package_version="0.1.0", shutdown_token="t" * 32)
        result = launcher.detect_stale_instance(tmp_path,
                                                pid_alive=lambda pid: False)
        assert result == {"stale": True, "cleared": True, "pid": 4242}
        assert launcher.read_instance(tmp_path) is None  # 残留已删除

    def test_unreachable_health_is_cleared(self, tmp_path):
        launcher.write_instance(tmp_path, pid=4242, port=10001,
                                package_version="0.1.0", shutdown_token="t" * 32)
        result = launcher.detect_stale_instance(
            tmp_path, pid_alive=lambda pid: True,
            health_reachable=lambda record: False)
        assert result["cleared"] is True
        assert launcher.read_instance(tmp_path) is None

    def test_live_instance_kept(self, tmp_path):
        launcher.write_instance(tmp_path, pid=4242, port=10001,
                                package_version="0.1.0", shutdown_token="t" * 32)
        result = launcher.detect_stale_instance(tmp_path,
                                                pid_alive=lambda pid: True)
        assert result is None
        assert launcher.read_instance(tmp_path)["pid"] == 4242

    def test_no_instance_file_is_clean(self, tmp_path):
        assert launcher.detect_stale_instance(tmp_path,
                                              pid_alive=lambda pid: False) is None

    def test_is_pid_alive_rejects_nonpositive(self):
        assert launcher.is_pid_alive(0) is False
        assert launcher.is_pid_alive(-1) is False
