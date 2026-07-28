"""
启动器支撑（DOC-RELEASE-008）

- RULE-RELEASE-057：端口/pid/started_at/package_version/shutdown_token
  原子写入 instance.json（write-temp + rename）
- RULE-RELEASE-058：健康轮询协议（500 ms 间隔、60 s 超时、ready + 版本匹配）
- RULE-RELEASE-061：陈旧实例检测（pid 不存活或 health 不可达）→ 删除残留
- RULE-RELEASE-052：shutdown_token 单次启动有效，进程退出删除文件
"""

from __future__ import annotations

import ctypes
import json
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

from .constants import INSTANCE_FORMAT_VERSION

INSTANCE_FILE = "instance.json"

#: 健康轮询参数（RULE-RELEASE-058）
HEALTH_POLL_INTERVAL_MS = 500
HEALTH_POLL_TIMEOUT_MS = 60_000
HEALTH_PROCESS_STATES = ("starting", "ready", "error")


def _default_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def generate_shutdown_token() -> str:
    """CSPRNG 一次性停止凭据（RULE-RELEASE-052/060）"""
    return secrets.token_hex(16)


def write_instance(runtime_dir: Path | str, *, pid: int, port: int,
                   package_version: str, shutdown_token: str,
                   utc_now=_default_utc) -> dict:
    """DES-RELEASE-016：原子写入（write-temp + rename）"""
    runtime_dir = Path(runtime_dir)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "instance_format_version": INSTANCE_FORMAT_VERSION,
        "pid": pid,
        "port": port,
        "url": "http://127.0.0.1:{}/".format(port),
        "package_version": package_version,
        "started_at": utc_now(),
        "shutdown_token": shutdown_token,
    }
    tmp = runtime_dir / (INSTANCE_FILE + ".tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True),
                   encoding="utf-8")
    os.replace(tmp, runtime_dir / INSTANCE_FILE)
    return record


def read_instance(runtime_dir: Path | str) -> dict | None:
    path = Path(runtime_dir) / INSTANCE_FILE
    if not path.is_file():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return None
    if record.get("instance_format_version") != INSTANCE_FORMAT_VERSION:
        return None
    return record


def delete_instance(runtime_dir: Path | str) -> bool:
    path = Path(runtime_dir) / INSTANCE_FILE
    if path.exists():
        path.unlink()
        return True
    return False


def is_pid_alive(pid: int) -> bool:
    """Windows OpenProcess 探测；无权限视为存活（避免误清正常实例）"""
    if pid <= 0:
        return False
    kernel32 = ctypes.windll.kernel32
    synchronize = 0x00100000
    handle = kernel32.OpenProcess(synchronize, False, pid)
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)) == 0:
            return False
        return code.value == 259  # STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def detect_stale_instance(runtime_dir: Path | str, pid_alive=is_pid_alive,
                          health_reachable=None) -> dict | None:
    """RULE-RELEASE-061：pid 不存活或 health 不可达 → 陈旧残留，删除并返回"""
    record = read_instance(runtime_dir)
    if record is None:
        return None
    alive = pid_alive(int(record.get("pid", -1)))
    reachable = health_reachable(record) if health_reachable else alive
    if not alive or not reachable:
        delete_instance(runtime_dir)
        return {"stale": True, "cleared": True, "pid": record.get("pid")}
    return None


class HealthPoller:
    """RULE-RELEASE-058：每 500 ms 轮询，总超时 60 s；
    ready + package_version 匹配 → 成功；error 或超时 → 失败，不无限重试"""

    def __init__(self, fetch, sleep=time.sleep, monotonic=time.monotonic,
                 interval_ms: int = HEALTH_POLL_INTERVAL_MS,
                 timeout_ms: int = HEALTH_POLL_TIMEOUT_MS) -> None:
        self._fetch = fetch
        self._sleep = sleep
        self._monotonic = monotonic
        self._interval = interval_ms / 1000.0
        self._timeout = timeout_ms / 1000.0

    def poll(self, expected_package_version: str) -> dict:
        started = self._monotonic()
        attempts = 0
        while True:
            attempts += 1
            status = self._fetch()
            elapsed = self._monotonic() - started
            if isinstance(status, dict):
                state = status.get("process_state")
                if state == "ready":
                    version = status.get("package_version",
                                         expected_package_version)
                    if version == expected_package_version:
                        return {"outcome": "ready", "attempts": attempts,
                                "elapsed_ms": int(elapsed * 1000)}
                elif state == "error":
                    return {"outcome": "error", "attempts": attempts,
                            "elapsed_ms": int(elapsed * 1000)}
            if elapsed >= self._timeout:
                return {"outcome": "timeout", "attempts": attempts,
                        "elapsed_ms": int(elapsed * 1000)}
            self._sleep(self._interval)
