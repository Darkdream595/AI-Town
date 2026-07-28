"""
用户数据根目录与布局（DOC-RELEASE-001 §5.1）

- RULE-RELEASE-001：程序安装目录只读；一切运行期可变数据写入
  %LOCALAPPDATA%\\AI-Town，Unicode 全路径，支持中文与空格目录名
- RULE-RELEASE-054：用户数据根路径由后端进程解析，前端/REST/配置不可改写
- 路径一律经 pathlib，禁止字节拼接
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from src.foundation.id_generator import is_valid_ulid

#: 用户数据根目录名（RULE-RELEASE-001）
APP_DIR_NAME = "AI-Town"

#: §5.1 布局的固定子目录
ROOT_SUBDIRS = ("worlds", "trash", "secrets", "runtime", "logs", "diagnostics")
WORLD_SUBDIRS = ("timelines", "snapshots", "saves", "backups")


def default_user_data_root() -> Path:
    """后端进程解析用户数据根（RULE-RELEASE-054）；不接受任何外部传入"""
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / APP_DIR_NAME
    # 非 Windows 开发/测试环境回退（发布目标仅 Windows，DOC-RELEASE-009）
    return Path.home() / ".local" / "share" / APP_DIR_NAME


class UserDataLayout:
    """用户数据目录布局的唯一入口；构造时 root 由调用方（后端启动装配）确定"""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    # --- 根级 ---
    @property
    def app_db_path(self) -> Path:
        return self.root / "app.sqlite3"

    def subdir(self, name: str) -> Path:
        if name not in ROOT_SUBDIRS:
            raise ValueError(f"未知根子目录: {name}")
        return self.root / name

    @property
    def worlds_dir(self) -> Path:
        return self.root / "worlds"

    @property
    def trash_dir(self) -> Path:
        return self.root / "trash"

    @property
    def secrets_dir(self) -> Path:
        return self.root / "secrets"

    @property
    def runtime_dir(self) -> Path:
        return self.root / "runtime"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    @property
    def diagnostics_dir(self) -> Path:
        return self.root / "diagnostics"

    # --- 世界级 ---
    def world_dir(self, world_id: str) -> Path:
        _require_ulid(world_id)
        return self.worlds_dir / world_id

    def world_db_path(self, world_id: str) -> Path:
        return self.world_dir(world_id) / "world.sqlite3"

    def world_subdir(self, world_id: str, name: str) -> Path:
        if name not in WORLD_SUBDIRS:
            raise ValueError(f"未知世界子目录: {name}")
        return self.world_dir(world_id) / name

    def trash_world_dir(self, world_id: str) -> Path:
        _require_ulid(world_id)
        return self.trash_dir / world_id

    # --- 创建 ---
    def ensure_root_layout(self) -> None:
        """首启创建 5.1 布局（§10 验收：新机器首启后布局完全一致）"""
        self.root.mkdir(parents=True, exist_ok=True)
        for name in ROOT_SUBDIRS:
            (self.root / name).mkdir(exist_ok=True)

    def ensure_world_layout(self, world_id: str) -> Path:
        world = self.world_dir(world_id)
        world.mkdir(parents=True, exist_ok=True)
        for name in WORLD_SUBDIRS:
            (world / name).mkdir(exist_ok=True)
        return world

    # --- 扫描 ---
    def iter_world_dirs(self) -> list[Path]:
        if not self.worlds_dir.is_dir():
            return []
        return sorted(p for p in self.worlds_dir.iterdir() if p.is_dir())

    def iter_trash_dirs(self) -> list[Path]:
        if not self.trash_dir.is_dir():
            return []
        return sorted(p for p in self.trash_dir.iterdir() if p.is_dir())


def _require_ulid(value: str) -> None:
    """目录名永远只用 world_id（RULE-RELEASE-037），拒绝显示名混入路径"""
    if not is_valid_ulid(value):
        raise ValueError(f"目录名必须是 ULID: {value!r}")


def force_rmtree(path: Path) -> None:
    """删除目录树前清除只读属性（branch 归档置 0o444，Windows rmtree 不能删）"""
    import os
    import shutil
    path = Path(path)
    if not path.exists():
        return
    for entry in path.rglob("*"):
        if entry.is_file() or entry.is_symlink():
            try:
                os.chmod(entry, 0o666)
            except OSError:
                pass
    try:
        os.chmod(path, 0o777)
    except OSError:
        pass
    shutil.rmtree(path, ignore_errors=True)


_ASCII_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_ascii_filename(display_name: str, fallback: str = "world") -> str:
    """导出包文件名的 display_name 清洗（DOC-RELEASE-005 DES-RELEASE-011）"""
    cleaned = _ASCII_SAFE.sub("-", display_name).strip("-.")
    return cleaned or fallback
