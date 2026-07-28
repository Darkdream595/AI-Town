"""TEST-RELEASE-037..040：日志与诊断包（DOC-RELEASE-010）"""
from __future__ import annotations

import io
import json
import os
import re
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from release_helpers import (layout, app_conn, make_utc_factory)  # noqa: F401

from src.diagnostics import logging as diag_logging
from src.persistence import diagnostics_pkg, secret_scan
from src.persistence.constants import (SCANNER_RULESET_VERSION, ReleaseError)

SRC_DIR = Path(__file__).resolve().parents[1] / "src"


class TestZeroTelemetryAndLogBoundaries:  # TEST-RELEASE-037：
    # RULE-RELEASE-071/072/073
    def test_no_outbound_network_imports(self):
        """RULE-RELEASE-071：持久化与日志包无任何网络出站能力"""
        banned = re.compile(
            r"^\s*(import|from)\s+(requests|httpx|aiohttp|urllib|socket"
            r"|http\.client|ftplib|smtplib|websocket)", re.MULTILINE)
        offenders = []
        for package in ("persistence", "diagnostics"):
            for path in (SRC_DIR / package).glob("*.py"):
                if banned.search(path.read_text(encoding="utf-8")):
                    offenders.append(path.name)
        assert offenders == []

    def test_log_field_policy_blocks_never_fields(self):
        """RULE-RELEASE-072：Prompt/对话/reasoning/Secret 字段一律拒绝"""
        for field in ("prompt_text", "completion_text", "dialogue_text",
                      "reasoning_content", "api_key", "session_secret",
                      "belief_content"):
            with pytest.raises(diag_logging.LogPolicyError):
                diag_logging.check_fields_policy({field: "x"})

    def test_unregistered_field_defaults_never(self):
        with pytest.raises(diag_logging.LogPolicyError):
            diag_logging.check_fields_policy({"some_new_field": "x"})

    def test_id_only_and_allowed_fields_pass(self):
        diag_logging.check_fields_policy(
            {"world_id": "01ABC", "command_id": "cmd-1", "revision": 3,
             "masked_suffix": "5678", "duration_ms": 12})

    def test_logger_fail_closed_on_policy_violation(self, tmp_path):
        """策略违规丢条不明文写出（fail closed）"""
        logger = diag_logging.StructuredLogger(
            "app", str(tmp_path), utc_now=make_utc_factory())
        logger.info("test.event", ids={"prompt_text": "系统提示原文"})
        assert logger.write_failure_count == 1
        log_file = tmp_path / "app.log"
        content = log_file.read_text(encoding="utf-8") \
            if log_file.exists() else ""
        assert "系统提示原文" not in content

    def test_logger_writes_only_local_logs_dir(self, tmp_path):
        logger = diag_logging.StructuredLogger(
            "app", str(tmp_path), utc_now=make_utc_factory())
        logger.info("test.event", ids={"world_id": "01ABC"})
        line = (tmp_path / "app.log").read_text(encoding="utf-8").strip()
        record = json.loads(line)
        assert record["event_code"] == "test.event"
        assert record["ids"] == {"world_id": "01ABC"}
        # 记录仅含注册 Schema 字段
        assert set(record) == {"timestamp", "level", "logger", "event_code",
                               "world_id", "ids", "reason_code", "duration_ms"}


class TestLogRotationAndRetention:  # TEST-RELEASE-038：RULE-RELEASE-074
    def test_rotation_at_size_cap(self, tmp_path, monkeypatch):
        monkeypatch.setattr(diag_logging, "LOG_MAX_BYTES", 200)
        logger = diag_logging.StructuredLogger(
            "app", str(tmp_path), utc_now=make_utc_factory())
        for index in range(20):
            logger.info("test.rotate", ids={"count": index})
        rotated = sorted(p.name for p in tmp_path.glob("app.log.*"))
        assert rotated  # 单文件到容量滚动 .1..n
        assert (tmp_path / "app.log").is_file()

    def test_retention_removes_files_older_than_14_days(self, tmp_path):
        old = tmp_path / "app-20260701.log"
        old.write_text("old", encoding="utf-8")
        old_time = (datetime.now(timezone.utc) - timedelta(days=15)).timestamp()
        os.utime(old, (old_time, old_time))
        recent = tmp_path / "app-20260728.log"
        recent.write_text("recent", encoding="utf-8")
        result = diagnostics_pkg.enforce_log_retention(tmp_path)
        assert "app-20260701.log" in result["removed"]
        assert recent.is_file()

    def test_total_cap_deletes_oldest_first(self, tmp_path, monkeypatch):
        monkeypatch.setattr(diagnostics_pkg, "LOG_TOTAL_MAX_BYTES", 150)
        base = datetime.now(timezone.utc) - timedelta(days=3)
        names = []
        for index in range(3):
            path = tmp_path / f"app-2026072{index}.log"
            path.write_bytes(b"x" * 100)
            moment = (base + timedelta(days=index)).timestamp()
            os.utime(path, (moment, moment))
            names.append(path.name)
        result = diagnostics_pkg.enforce_log_retention(tmp_path)
        assert result["total_bytes"] <= 150
        assert result["removed"] == [names[0], names[1]]  # 最旧先删
        assert (tmp_path / names[2]).is_file()

    def test_disk_full_degrades_to_memory_ring(self, tmp_path):
        """磁盘满/目录不可写：丢日志可接受，不阻塞世界数据"""
        blocker = tmp_path / "blocked"
        blocker.write_text("x", encoding="utf-8")  # 文件占位使 mkdir 失败
        logger = diag_logging.StructuredLogger(
            "app", str(blocker), utc_now=make_utc_factory())
        logger.info("test.degraded", ids={"count": 1})
        assert logger.degraded is True
        assert logger.ring_records()  # 记录入内存环而非崩溃


class TestScannerRulesAndAbort:  # TEST-RELEASE-039：RULE-RELEASE-075/076
    def setup_method(self):
        secret_scan.clear_canaries()

    def teardown_method(self):
        secret_scan.clear_canaries()

    def test_rule_a_key_shapes(self):
        report = secret_scan.scan_text("key=sk-abcdefgh12345678 和其他")
        assert any(h["rule"] == "a_key_shape" for h in report["hits"])
        report = secret_scan.scan_text("f" * 32)
        assert any(h["rule"] == "a_key_shape" for h in report["hits"])
        report = secret_scan.scan_text("A" * 40 + "==")
        assert any(h["rule"] == "a_key_shape" for h in report["hits"])

    def test_rule_b_credential_adjacency(self):
        report = secret_scan.scan_text('api_key: "real-secret-value-123"')
        assert any(h["rule"] == "b_credential_adjacency"
                   for h in report["hits"])
        # 掩码值不命中
        report = secret_scan.scan_text('api_key: "********"')
        assert not any(h["rule"] == "b_credential_adjacency"
                       for h in report["hits"])

    def test_rule_c_canary_exact_match(self):
        secret_scan.register_canary("sk-canary-测试假凭据-0001")
        report = secret_scan.scan_text("前缀 sk-canary-测试假凭据-0001 后缀")
        assert [h["rule"] for h in report["hits"]] == ["c_canary"]
        report = secret_scan.scan_text("sk-canary-测试假凭据-0002")
        assert report["clean"] is True

    def test_rule_d_path_out_of_bounds(self, tmp_path):
        allowed = (tmp_path,)
        report = secret_scan.scan_text(r"写到 C:\Other\place\file.txt",
                                       allowed)
        assert any(h["rule"] == "d_path_out_of_bounds" for h in report["hits"])
        # 允许根内路径不命中
        inside = str(tmp_path / "logs" / "app.log")
        report = secret_scan.scan_text(f"日志位于 {inside}", allowed)
        assert not any(h["rule"] == "d_path_out_of_bounds"
                       for h in report["hits"])
        # UNC 一律越界
        report = secret_scan.scan_text(r"\\NAS\share\x", allowed)
        assert any(h["rule"] == "d_path_out_of_bounds" for h in report["hits"])

    def test_url_not_counted_as_path(self):
        report = secret_scan.scan_text("base_url=https://api.deepseek.com/v1")
        assert not any(h["rule"] == "d_path_out_of_bounds"
                       for h in report["hits"])

    def test_binary_mode_skips_hex_and_paths(self):
        """SQLite 二进制合法存储 sha256 十六进制，不误命中"""
        blob = b"\x00\x01" + b"sha256:" + b"f" * 64 + b"\x00"
        report = secret_scan.scan_bytes(blob)
        assert report["clean"] is True
        # sk- 前缀对二进制仍生效
        blob = b"\x00sk-abcdefgh12345678\x00"
        report = secret_scan.scan_bytes(blob)
        assert any(h["rule"] == "a_key_shape" for h in report["hits"])

    def test_excluded_values_masked_before_scan(self):
        structural = "f" * 64  # 自有 manifest 哈希字段
        report = secret_scan.scan_text(f"file_sha256={structural}",
                                       excluded_values=(structural,))
        assert report["clean"] is True

    def test_ruleset_version_in_report(self):
        report = secret_scan.scan_text("clean text")
        assert report["scanner_ruleset_version"] == SCANNER_RULESET_VERSION
        assert report["clean"] is True

    def test_diagnostics_package_aborts_on_hit(self, layout, app_conn):
        """RULE-RELEASE-076：任一命中即中止，绝不产出部分脱敏的包"""
        with pytest.raises(ReleaseError) as exc:
            diagnostics_pkg.build_diagnostics_package(
                layout, app_conn=app_conn, package_version="0.1.0",
                build_id="abc",
                settings={"ai.base_url": "https://api.deepseek.com",
                          "leaked": "sk-abcdefgh12345678"},
                key_masked_status="configured ****5678",
                worlds_summary=[], utc_now=make_utc_factory())
        assert exc.value.reason_code == "RELEASE_SECRET_SCAN_HIT"
        # 无 zip 产出
        assert list(layout.diagnostics_dir.glob("*.zip")) == []


class TestDiagnosticsWhitelistAndHashing:  # TEST-RELEASE-040：
    # RULE-RELEASE-077/078
    def test_whitelist_exact_members(self):
        assert diagnostics_pkg.WHITELIST == (
            "manifest.json", "system.json", "package.json", "settings.json",
            "worlds-summary.json", "recovery/", "logs/")

    def _build_package(self, layout, app_conn):
        return diagnostics_pkg.build_diagnostics_package(
            layout, app_conn=app_conn, package_version="0.1.0",
            build_id="abc123",
            settings={"ai.base_url": "https://api.deepseek.com",
                      "ai.model": "deepseek-v4-flash"},
            key_masked_status="configured ****5678",
            worlds_summary=[{"world_id": "01JTEST",
                             "display_name": "我的小镇"}],  # 例外允许明文
            utc_now=make_utc_factory())

    def test_package_members_all_whitelisted(self, layout, app_conn):
        result = self._build_package(layout, app_conn)
        with zipfile.ZipFile(result["target"]) as zf:
            names = zf.namelist()
        assert set(names) == set(result["members"])
        for name in names:
            top = name if "/" not in name else name.split("/")[0] + "/"
            assert top in diagnostics_pkg.WHITELIST
        # RULE-RELEASE-077：无任何数据库/存档/快照/导出包
        assert not any(n.endswith((".sqlite3", ".sqlite3-wal", ".snapshot",
                                   ".zip")) for n in names)

    def test_manifest_fields(self, layout, app_conn):
        result = self._build_package(layout, app_conn)
        with zipfile.ZipFile(result["target"]) as zf:
            manifest = json.loads(zf.read("manifest.json"))
        assert manifest["scanner_ruleset_version"] == SCANNER_RULESET_VERSION
        assert manifest["scan_result"] == "clean"
        assert manifest["package_version"] == "0.1.0"
        assert manifest["build_id"] == "abc123"
        assert set(manifest["included"]) <= set(diagnostics_pkg.WHITELIST)

    def test_settings_member_contains_masked_status_only(self, layout,
                                                         app_conn):
        result = self._build_package(layout, app_conn)
        with zipfile.ZipFile(result["target"]) as zf:
            settings = json.loads(zf.read("settings.json"))
        assert settings["deepseek_key_status"] == "configured ****5678"
        assert "sk-" not in json.dumps(settings)

    def test_content_hash_format(self):
        hashed = diagnostics_pkg.content_hash("玩家自由输入文本")
        prefix, _, length = hashed.partition("+")
        assert prefix.startswith("sha256:")
        assert re.fullmatch(r"[0-9a-f]{64}", prefix[7:])
        assert int(length) == len("玩家自由输入文本".encode("utf-8"))

    def test_summarize_world_is_summary_only(self, layout, app_conn):
        """RULE-RELEASE-077：数据库仅以摘要出现（行数/完整性/大小）"""
        from release_helpers import (make_ulid_factory, append_tick)
        from src.persistence import database, worlds
        registry = worlds.WorldRegistry(
            layout, app_conn, utc_now=make_utc_factory(),
            new_ulid=make_ulid_factory(), seed_fn=lambda: "cd" * 16)
        created = registry.create_world(command_id="cmd-sum-1",
                                        display_name="摘要测试世界")
        world_id = created["world_id"]
        db_path = layout.world_db_path(world_id)
        conn = database.open_write_connection(db_path)
        append_tick(conn, world_id, game_time=5)
        database.close_write_connection(db_path, conn)
        summary = diagnostics_pkg.summarize_world(db_path)
        assert summary["file"] == "world.sqlite3"
        assert summary["integrity"] == "ok"
        assert summary["size_bytes"] > 0
        assert summary["revision"] == 1
        assert summary["tables"]["event_log"] == 1
        # 摘要不携带任何自由文本字段
        assert "display_name" not in summary
