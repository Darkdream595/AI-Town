"""
RELEASE 产品常量与 reason_code 注册表

常量的取值均以 docs/15-persistence-release-quality 各文档规则为唯一来源；
reason_code 为注册枚举（DOC-RELEASE-006 §9：不携带自由文本用户内容）。
"""

from __future__ import annotations

# --- DOC-RELEASE-004：存档槽位产品常量（RULE-RELEASE-025，不可配置） ---
AUTO_SAVE_COUNT = 5
MANUAL_SLOT_COUNT = 3
MANUAL_SLOTS = ("slot_1", "slot_2", "slot_3")
SAVE_TRASH_DAYS = 7

# --- DOC-RELEASE-003：Snapshot 触发与保留（RULE-RELEASE-022） ---
SNAPSHOT_REVISION_INTERVAL = 2000
SNAPSHOT_KEEP_MIN = 2
SNAPSHOT_TRIGGERS = ("clean_shutdown", "revision_interval", "manual_save", "auto_save")

# --- DOC-RELEASE-004：自动恢复点触发（RULE-RELEASE-026） ---
AUTO_SAVE_REVISION_INTERVAL = 500
AUTO_SAVE_GAME_MINUTES = 10

# --- DOC-RELEASE-005：可恢复删除（RULE-RELEASE-034） ---
TRASH_RETENTION_DAYS = 30

# --- DOC-RELEASE-006：备份保留（RULE-RELEASE-046） ---
PRE_MIGRATION_BACKUP_KEEP = 3

# --- DOC-RELEASE-001：WAL 主动 checkpoint 阈值（§7） ---
WAL_ACTIVE_CHECKPOINT_BYTES = 64 * 1024 * 1024

# --- DOC-RELEASE-006：磁盘预检倍率（RULE-RELEASE-042） ---
DISK_PREFLIGHT_MULTIPLIER = 2

# --- Snapshot 文件 ---
SNAPSHOT_FORMAT_VERSION = 1
SNAPSHOT_FILE_SUFFIX = ".snap.zst"

# --- 导出包 ---
PACKAGE_FORMAT_VERSION = 1
PACKAGE_KIND = "aitown-world-export"
PACKAGE_FILE_SUFFIX = ".aitown-world.zip"

# --- 诊断包 ---
DIAG_FORMAT_VERSION = 1

# --- RecoveryReport ---
RECOVERY_REPORT_FORMAT_VERSION = 1

# --- instance.json ---
INSTANCE_FORMAT_VERSION = 1

# --- release-manifest ---
MANIFEST_FORMAT_VERSION = 1

# --- 扫描器规则集版本（RULE-RELEASE-075：规则更新必须同步升版） ---
SCANNER_RULESET_VERSION = 1

# --- 模拟门槛 / G9 清单版本 ---
SIMULATION_GATE_VERSION = 1
CHECKLIST_VERSION = 1

# ---------------------------------------------------------------------------
# RELEASE reason_code 注册表（DOC-RELEASE-006 §9：注册枚举，不含自由文本）
# ---------------------------------------------------------------------------
REASON_CODES = frozenset({
    # 数据库与完整性
    "RELEASE_DB_OPEN_FAILED",
    "RELEASE_DB_PRAGMA_FAILED",
    "RELEASE_DB_INTEGRITY_FAILED",
    "RELEASE_DB_FK_VIOLATION",
    "RELEASE_DB_LOCKED",
    "RELEASE_DB_CORRUPT_METADATA",
    # 迁移
    "RELEASE_MIGRATION_REFUSED_TOO_NEW",
    "RELEASE_MIGRATION_REFUSED_TOO_OLD",
    "RELEASE_MIGRATION_BACKUP_FAILED",
    "RELEASE_MIGRATION_STEP_FAILED",
    "RELEASE_MIGRATION_AUDIT_FAILED",
    "RELEASE_MIGRATION_EVENT_LOG_TOUCHED",
    # 事件与快照
    "RELEASE_EVENT_GAP_DETECTED",
    "RELEASE_EVENT_ENVELOPE_INVALID",
    "RELEASE_EVENT_CONTENT_FORBIDDEN",
    "RELEASE_SNAPSHOT_HASH_MISMATCH",
    "RELEASE_SNAPSHOT_INVALID",
    "RELEASE_SNAPSHOT_UNAVAILABLE",
    "RELEASE_REPLAY_UNKNOWN_EVENT",
    "RELEASE_REPLAY_UPCAST_FAILED",
    # 存档
    "RELEASE_SAVE_NOT_FOUND",
    "RELEASE_SAVE_BROKEN",
    "RELEASE_SAVE_SLOT_INVALID",
    "RELEASE_SAVE_CONFIRM_REQUIRED",
    "RELEASE_SAVE_TRASH_EXPIRED",
    "RELEASE_BRANCH_INCOMPLETE",
    # 世界管理
    "RELEASE_WORLD_NOT_FOUND",
    "RELEASE_WORLD_ALREADY_OPEN",
    "RELEASE_WORLD_OPEN_FAILED",
    "RELEASE_WORLD_NEEDS_ATTENTION",
    "RELEASE_WORLD_UNRECOVERABLE",
    "RELEASE_IMPORT_INVALID",
    "RELEASE_IMPORT_TOO_OLD",
    "RELEASE_IMPORT_TOO_NEW",
    "RELEASE_EXPORT_BLOCKED",
    # 资源
    "RELEASE_DISK_SPACE_INSUFFICIENT",
    "RELEASE_DISK_FULL",
    "RELEASE_IO_ERROR",
    # 恢复链
    "RELEASE_WAL_RECOVER_FAILED",
    "RELEASE_RECOVERY_SNAPSHOT_FAILED",
    "RELEASE_RECOVERY_RESERVATION_FAILED",
    "RELEASE_RECOVERY_INFLIGHT_FAILED",
    "RELEASE_RECOVERY_AUDIT_FAILED",
    "RELEASE_RECOVERY_UNRECOVERABLE",
    # 配置与扫描
    "RELEASE_SETTING_UNKNOWN_KEY",
    "RELEASE_SETTING_INVALID",
    "RELEASE_SECRET_SCAN_HIT",
    # 打包
    "RELEASE_PACKAGE_BLACKLIST_HIT",
    "RELEASE_PACKAGE_MANIFEST_MISMATCH",
    "RELEASE_PACKAGE_LICENSE_INCOMPLETE",
})


class ReleaseError(Exception):
    """RELEASE 域内部异常：携带注册 reason_code，不含自由文本用户内容"""

    def __init__(self, reason_code: str, details: dict | None = None) -> None:
        if reason_code not in REASON_CODES:
            raise ValueError(f"未注册的 RELEASE reason_code: {reason_code}")
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.details = dict(details) if details else None
