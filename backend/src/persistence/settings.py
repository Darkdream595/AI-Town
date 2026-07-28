"""
非敏感配置白名单（DOC-RELEASE-007）

- RULE-RELEASE-048：app_settings 只接受注册白名单键；未知键/非法值一律拒绝
- RULE-RELEASE-053：优先级固定封闭：内置默认值 < app_settings；无环境变量覆盖
- §7：存量非法值按内置默认回退并告警；未知存量键忽略并告警，不拒绝启动
"""

from __future__ import annotations

import json
import re
import sqlite3

from src.foundation.id_generator import is_valid_ulid

from .constants import ReleaseError

_HTTPS_URL = re.compile(r"^https://[^\s/$.?#].[^\s]*$")


def _is_bool(value) -> bool:
    return isinstance(value, bool)


def _is_speed(value) -> bool:
    return value in (0.5, 1, 2, 4)


def _is_base_url(value) -> bool:
    return isinstance(value, str) and bool(_HTTPS_URL.match(value))


def _is_model(value) -> bool:
    return value == "deepseek-v4-flash"


def _is_concurrency(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) \
        and 1 <= value <= 2


def _is_world_ref(value) -> bool:
    return value is None or (isinstance(value, str) and is_valid_ulid(value))


#: DES-RELEASE-014：首版全部合法键（值均为 JSON）
SETTINGS_WHITELIST: dict[str, dict] = {
    "ui.fullscreen_hint_shown": {"validate": _is_bool, "default": False},
    "ui.last_world_id": {"validate": _is_world_ref, "default": None},
    "ui.tray_notify_on_autosave": {"validate": _is_bool, "default": False},
    "simulation.default_speed": {"validate": _is_speed, "default": 1},
    "ai.base_url": {"validate": _is_base_url,
                    "default": "https://api.deepseek.com"},
    "ai.model": {"validate": _is_model, "default": "deepseek-v4-flash"},
    "ai.request_concurrency_limit": {"validate": _is_concurrency, "default": 2},
    "diagnostics.include_recovery_reports": {"validate": _is_bool,
                                             "default": True},
}


class SettingsStore:
    """app_settings 的唯一读写入口；内存缓存，变更时失效重载（§9）"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self._cache: dict[str, object] = {}
        #: 启动回退/忽略告警（§7）
        self.warnings: list[str] = []

    def init_defaults(self) -> None:
        """首启写入全部默认键（§6.1）"""
        for key, spec in SETTINGS_WHITELIST.items():
            self.conn.execute(
                "INSERT OR IGNORE INTO app_settings(key, value_json)"
                " VALUES (?,?)",
                (key, json.dumps(spec["default"], ensure_ascii=False)))
        self.conn.commit()
        self._cache.clear()

    def load(self) -> None:
        """启动加载：未知键忽略并告警；非法值回退默认并告警；不拒绝启动"""
        self._cache.clear()
        self.warnings.clear()
        for row in self.conn.execute("SELECT key, value_json"
                                     " FROM app_settings").fetchall():
            key, text = row["key"], row["value_json"]
            spec = SETTINGS_WHITELIST.get(key)
            if spec is None:
                self.warnings.append(f"unknown_key:{key}")
                continue
            try:
                value = json.loads(text)
            except ValueError:
                value = None
            if value is None or not spec["validate"](value):
                self.warnings.append(f"invalid_value:{key}")
                value = spec["default"]
            self._cache[key] = value
        for key, spec in SETTINGS_WHITELIST.items():
            self._cache.setdefault(key, spec["default"])

    def get(self, key: str):
        if key not in SETTINGS_WHITELIST:
            raise ReleaseError("RELEASE_SETTING_UNKNOWN_KEY", {"key": key})
        if not self._cache:
            self.load()
        return self._cache[key]

    def set(self, key: str, value) -> None:
        """白名单校验 → 单行 UPSERT → 立即生效（§6.4）"""
        spec = SETTINGS_WHITELIST.get(key)
        if spec is None:
            raise ReleaseError("RELEASE_SETTING_UNKNOWN_KEY", {"key": key})
        if not spec["validate"](value):
            raise ReleaseError("RELEASE_SETTING_INVALID", {"key": key})
        self.conn.execute(
            "INSERT INTO app_settings(key, value_json) VALUES (?,?)"
            " ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json",
            (key, json.dumps(value, ensure_ascii=False)))
        self.conn.commit()
        self._cache[key] = value

    def as_dict(self) -> dict:
        if not self._cache:
            self.load()
        return dict(self._cache)
