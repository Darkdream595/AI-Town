"""TEST-RELEASE-025..028：配置白名单与 Secret 管理（DOC-RELEASE-007）"""
from __future__ import annotations

import json

import pytest
from release_helpers import layout, app_conn  # noqa: F401

from src.persistence import launcher, paths, settings
from src.persistence.constants import ReleaseError
from src.security.redaction import RedactionFilter
from src.security.secrets import (AuthHeaderHandle, ChainedSecretStore,
                                  MemorySecretStore, SecretService)


class TestSettingsWhitelist:  # TEST-RELEASE-025：RULE-RELEASE-048/053
    def test_whitelist_has_exactly_eight_keys(self):
        assert set(settings.SETTINGS_WHITELIST) == {
            "ui.fullscreen_hint_shown", "ui.last_world_id",
            "ui.tray_notify_on_autosave", "simulation.default_speed",
            "ai.base_url", "ai.model", "ai.request_concurrency_limit",
            "diagnostics.include_recovery_reports"}

    def test_init_defaults_writes_all_keys(self, app_conn):
        store = settings.SettingsStore(app_conn)
        store.init_defaults()
        rows = app_conn.execute(
            "SELECT COUNT(*) FROM app_settings").fetchone()[0]
        assert rows == len(settings.SETTINGS_WHITELIST)
        assert store.get("ai.model") == "deepseek-v4-flash"
        assert store.get("simulation.default_speed") == 1

    def test_set_accepts_valid_value(self, app_conn):
        store = settings.SettingsStore(app_conn)
        store.init_defaults()
        store.set("simulation.default_speed", 4)
        assert store.get("simulation.default_speed") == 4
        # 换实例重载验证持久化
        store2 = settings.SettingsStore(app_conn)
        assert store2.get("simulation.default_speed") == 4

    def test_unknown_key_rejected(self, app_conn):
        store = settings.SettingsStore(app_conn)
        with pytest.raises(ReleaseError) as exc:
            store.set("ui.theme", "dark")
        assert exc.value.reason_code == "RELEASE_SETTING_UNKNOWN_KEY"
        with pytest.raises(ReleaseError):
            store.get("ai.api_key")

    def test_invalid_value_rejected_per_key_schema(self, app_conn):
        store = settings.SettingsStore(app_conn)
        store.init_defaults()
        bad_cases = [
            ("simulation.default_speed", 3),       # 枚举外
            ("simulation.default_speed", "fast"),  # 非数值
            ("ai.request_concurrency_limit", 0),   # 越界
            ("ai.request_concurrency_limit", 3),
            ("ai.base_url", "http://insecure.example.com"),  # 必须 https
            ("ai.model", "gpt-4o"),                # 白名单模型外
            ("ui.fullscreen_hint_shown", "yes"),   # 非布尔
        ]
        for key, value in bad_cases:
            with pytest.raises(ReleaseError) as exc:
                store.set(key, value)
            assert exc.value.reason_code == "RELEASE_SETTING_INVALID"

    def test_startup_fallback_and_unknown_warn_not_refuse(self, app_conn):
        """§7：存量非法值回退默认 + 未知键忽略，均告警但不拒绝启动"""
        store = settings.SettingsStore(app_conn)
        store.init_defaults()
        app_conn.execute(
            "UPDATE app_settings SET value_json='99'"
            " WHERE key='simulation.default_speed'")
        app_conn.execute(
            "INSERT INTO app_settings(key, value_json)"
            " VALUES ('legacy.removed_key','1')")
        app_conn.commit()
        store.load()
        assert store.get("simulation.default_speed") == 1  # 回退默认
        assert "invalid_value:simulation.default_speed" in store.warnings
        assert "unknown_key:legacy.removed_key" in store.warnings

    def test_priority_closed_no_env_override(self, app_conn, monkeypatch):
        """RULE-RELEASE-053：默认值 < app_settings；无环境变量覆盖通道"""
        monkeypatch.setenv("AI_TOWN_DEFAULT_SPEED", "4")
        store = settings.SettingsStore(app_conn)
        store.init_defaults()
        assert store.get("simulation.default_speed") == 1  # 环境变量不生效
        store.set("simulation.default_speed", 2)
        store2 = settings.SettingsStore(app_conn)
        assert store2.get("simulation.default_speed") == 2  # app_settings 优先


class TestSecretStorageIsolation:  # TEST-RELEASE-026：RULE-RELEASE-049/050
    def test_plaintext_never_touches_sqlite(self, app_conn, tmp_path):
        """Key 配置后扫描 app.sqlite3 字节无明文"""
        store = SecretService(MemorySecretStore(), RedactionFilter(),
                              id_factory=lambda: "ref-1")
        secret = "sk-test026abcdef1234567890"
        store.set_secret("deepseek_api_key", secret)
        raw = tmp_path / "app-dump.bin"
        raw.write_bytes(app_conn.serialize())
        assert secret.encode() not in raw.read_bytes()

    def test_status_returns_masked_only(self):
        service = SecretService(MemorySecretStore(), RedactionFilter(),
                                id_factory=lambda: "ref-1")
        status = service.set_secret("deepseek_api_key", "sk-abcdefgh12345678")
        assert status["configured"] is True
        assert status["masked_suffix"] == "5678"
        assert "sk-abcdefgh12345678" not in json.dumps(status)

    def test_chained_store_fallback_and_mutual_exclusion(self):
        """主备互斥：首选失败时降级到备用，且只有一个后端被激活"""
        class FailingBackend:
            backend_name = "windows_credential_manager"

            def write(self, target, plaintext):
                raise OSError("WCM disabled")

            def read(self, target):
                return None

            def delete(self, target):
                pass

        fallback = MemorySecretStore()
        chain = ChainedSecretStore([FailingBackend(), fallback])
        service = SecretService(chain, RedactionFilter(),
                                id_factory=lambda: "ref-1")
        status = service.set_secret("deepseek_api_key", "sk-fallback-test-0001")
        assert status["storage_backend"] == "memory"  # 实际激活备用
        # 清除后备用存储也为空
        service.delete_secret("deepseek_api_key")
        assert fallback.read("AI-Town/deepseek-api-key") is None

    def test_secrets_dir_excluded_from_exports_and_diagnostics(self, layout):
        """RULE-RELEASE-050：secrets\\ 只落在用户数据布局内，
        诊断白名单与导出黑名单共同保证其不外流"""
        from src.persistence import diagnostics_pkg, release_manifest
        assert "secrets/" not in diagnostics_pkg.WHITELIST
        assert all("secrets" not in member for member
                   in diagnostics_pkg.WHITELIST)
        hits = release_manifest.scan_package_blacklist  # 打包侧
        pkg = layout.root / "pkg"
        (pkg / "secrets").mkdir(parents=True)
        (pkg / "secrets" / "deepseek-api-key.dpapi").write_bytes(b"blob")
        assert hits(pkg) == ["secrets/deepseek-api-key.dpapi"]

    def test_export_package_contains_no_secret(self, layout, app_conn,
                                               tmp_path):
        """导出世界包全文扫描不含 Key（RULE-RELEASE-049 导出介质）"""
        from src.persistence import worlds
        from release_helpers import make_ulid_factory, make_utc_factory
        registry = worlds.WorldRegistry(
            layout, app_conn, utc_now=make_utc_factory(),
            new_ulid=make_ulid_factory(), seed_fn=lambda: "cd" * 16)
        created = registry.create_world(command_id="cmd-exp-1",
                                        display_name="导出测试")
        from src.persistence import transfer
        target = tmp_path / "export.zip"
        transfer.export_world(layout, app_conn, world_id=created["world_id"],
                              target_path=target, app_package_version="0.1.0",
                              utc_now=make_utc_factory())
        assert b"sk-" not in target.read_bytes()


class TestInMemoryHandles:  # TEST-RELEASE-027：RULE-RELEASE-051/052
    def test_credential_ref_is_opaque(self):
        service = SecretService(MemorySecretStore(), RedactionFilter(),
                                id_factory=lambda: "ref-opaque-1")
        service.set_secret("deepseek_api_key", "sk-opaque-test-123456")
        ref = service.get_credential_ref("deepseek_api_key")
        assert ref is not None
        assert "sk-opaque-test-123456" not in json.dumps(
            {"ref_id": ref.ref_id, "kind": ref.kind,
             "generation": ref.generation})

    def test_auth_header_handle_single_use(self):
        service = SecretService(MemorySecretStore(), RedactionFilter(),
                                id_factory=lambda: "ref-1")
        service.set_secret("deepseek_api_key", "sk-single-use-123456")
        ref = service.get_credential_ref("deepseek_api_key")
        handle = service.resolve_for_request(ref)
        header = handle.header()
        assert header["Authorization"] == "Bearer sk-single-use-123456"
        with pytest.raises(Exception):
            handle.header()  # 一次性：第二次调用即失效

    def test_delete_invalidates_all_refs(self):
        service = SecretService(MemorySecretStore(), RedactionFilter(),
                                id_factory=lambda: "ref-1")
        service.set_secret("deepseek_api_key", "sk-invalidate-123456")
        ref = service.get_credential_ref("deepseek_api_key")
        service.delete_secret("deepseek_api_key")
        with pytest.raises(Exception):
            service.resolve_for_request(ref)

    def test_instance_json_only_process_credential_is_shutdown_token(
            self, tmp_path):
        """RULE-RELEASE-052：instance.json 无 API Key 字段，仅 shutdown_token"""
        token = launcher.generate_shutdown_token()
        assert len(token) == 32 and all(c in "0123456789abcdef" for c in token)
        record = launcher.write_instance(
            tmp_path, pid=1234, port=56789, package_version="0.1.0",
            shutdown_token=token)
        text = (tmp_path / "instance.json").read_text(encoding="utf-8")
        assert "api_key" not in text and "deepseek" not in text.lower()
        assert record["shutdown_token"] == token
        launcher.delete_instance(tmp_path)
        assert launcher.read_instance(tmp_path) is None  # 随进程退出删除


class TestPathNotRewritable:  # TEST-RELEASE-028：RULE-RELEASE-054
    def test_default_root_from_localappdata(self, monkeypatch):
        monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\测试 用户\AppData\Local")
        root = paths.default_user_data_root()
        assert root == paths.Path(
            r"C:\Users\测试 用户\AppData\Local") / "AI-Town"

    def test_default_root_fallback_without_env(self, monkeypatch):
        monkeypatch.delenv("LOCALAPPDATA", raising=False)
        root = paths.default_user_data_root()
        assert root.name == "AI-Town"  # 非 Windows 回退仍同目录名

    def test_layout_derives_everything_from_root(self):
        ly = paths.UserDataLayout(r"D:\任意 位置\AI-Town")
        assert ly.app_db_path.parent == ly.root
        assert ly.worlds_dir.parent == ly.root
        assert ly.trash_dir.parent == ly.root
        # 无 set_root / 无外部改写入口
        assert not hasattr(ly, "set_root")

    def test_world_dir_rejects_display_name(self):
        ly = paths.UserDataLayout("root")
        with pytest.raises(ValueError):
            ly.world_dir("我的 世界")  # 目录名永远只用 ULID

    def test_sanitize_ascii_filename(self):
        assert paths.sanitize_ascii_filename("我的 世界（新）") == "world"
        assert paths.sanitize_ascii_filename("My World!") == "My-World"
        assert paths.sanitize_ascii_filename("中文 English混合") == "English"
