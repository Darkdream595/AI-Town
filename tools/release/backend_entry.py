"""PyInstaller 入口：读取包身份，再委派正式 Windows launcher。"""
from __future__ import annotations

import json
import multiprocessing
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path


def _package_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _configure_release_environment() -> None:
    package_root = _package_root()
    os.environ.setdefault(
        "AI_TOWN_STATIC_DIR", str(package_root / "assets" / "web"))
    local_app_data = Path(
        os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    os.environ.setdefault("AI_TOWN_DATA_DIR", str(local_app_data / "AI-Town"))
    manifest_path = package_root / "release-manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        os.environ.setdefault(
            "AI_TOWN_PACKAGE_VERSION", str(manifest.get("package_version", "")))
        os.environ.setdefault(
            "AI_TOWN_BUILD_ID", str(manifest.get("build_id", "")))


def _write_crash_log(error: BaseException) -> Path:
    local_app_data = Path(
        os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    log_dir = local_app_data / "AI-Town" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "launcher-crash.log"
    timestamp = datetime.now(timezone.utc).isoformat()
    log_path.write_text(
        f"{timestamp}\n{''.join(traceback.format_exception(error))}",
        encoding="utf-8",
    )
    return log_path


def main() -> None:
    multiprocessing.freeze_support()
    try:
        _configure_release_environment()
        package_root = _package_root()
        from src.release_entry import run_launcher

        run_launcher(
            package_version=os.environ.get("AI_TOWN_PACKAGE_VERSION") or "0.1.0",
            build_id=os.environ.get("AI_TOWN_BUILD_ID") or "release-local",
            static_dir=package_root / "assets" / "web",
        )
    except BaseException as error:
        try:
            _write_crash_log(error)
        except OSError:
            pass
        raise


if __name__ == "__main__":
    main()
