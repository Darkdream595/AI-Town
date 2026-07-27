"""
结构化日志（DOC-BACKEND-012 RULE-BACKEND-066/067）

- JSON lines：固定字段 timestamp/level/logger/event_code/world_id/ids/
  reason_code/duration_ms；正文禁止插值——只许注册过 Log Policy 的字段
- 轮转：单文件 10 MiB、保留 5 个，全部位于用户数据目录 logs/
- 日志目录不可写：降级为内存环形缓冲 1000 条，health 标注 logging_degraded
- 写失败静默丢条并递增 log_write_failure 计数；Redaction 异常 fail closed 丢条
"""

from __future__ import annotations

import json
import os
from collections import deque
from typing import Callable, Deque, Dict, Optional

LOG_MAX_BYTES = 10 * 1024 * 1024
LOG_KEEP_FILES = 5
MEMORY_RING_CAPACITY = 1000

LOG_LEVELS = frozenset({"debug", "info", "warning", "error"})

#: 敏感字段日志策略主表（DOC-BACKEND-012 §5 master）；未归类字段默认 never
LOG_FIELD_POLICIES: Dict[str, str] = {
    # never：Redaction 兜底
    "api_key": "never",
    "authorization": "never",
    "session_cookie_value": "never",
    "session_secret": "never",
    "csrf_token": "never",
    "ws_ticket": "never",
    "confirmation_token": "never",
    "dialogue_text": "never",
    "notice_text": "never",
    "prompt_text": "never",
    "completion_text": "never",
    "reasoning_content": "never",
    "belief_content": "never",
    "resident_secret": "never",
    # masked
    "fs_path": "masked",
    "origin": "masked",
    "host": "masked",
    # id-only
    "world_id": "id-only",
    "command_id": "id-only",
    "event_id": "id-only",
    "session_id": "id-only",
    "job_id": "id-only",
    "quest_id": "id-only",
    "building_id": "id-only",
    "resident_id": "id-only",
    "ticket_fingerprint": "id-only",
    "challenge_id": "id-only",
    "credential_ref": "id-only",
    # allowed
    "masked_suffix": "allowed",
    "key_fingerprint": "allowed",
    "amount": "allowed",
    "count": "allowed",
    "revision": "allowed",
    "game_time": "allowed",
    "error_code": "allowed",
    "reason_code": "allowed",
    "duration_ms": "allowed",
    "route_class": "allowed",
    "queue": "allowed",
    "result": "allowed",
    "action": "allowed",
    "position": "allowed",
    "bytes": "allowed",
}

#: ids 映射中允许出现的键（全部 id-only）
ALLOWED_ID_KEYS = frozenset(
    key for key, policy in LOG_FIELD_POLICIES.items() if policy in ("id-only", "allowed")
)


class LogPolicyError(Exception):
    def __init__(self, field: str) -> None:
        super().__init__(field)
        self.field = field


def check_fields_policy(ids: Optional[dict]) -> None:
    """ids 映射只允许注册过且非 never/masked 的字段；未归类默认 never → 拒绝"""
    for key in (ids or {}):
        policy = LOG_FIELD_POLICIES.get(key, "never")
        if policy in ("never", "masked"):
            raise LogPolicyError(key)


class StructuredLogger:
    def __init__(self, name: str, log_dir: Optional[str],
                 utc_now: Callable[[], str],
                 redact: Optional[Callable[[str], str]] = None,
                 mirror: Optional[Callable[[dict], None]] = None) -> None:
        self._name = name
        self._log_dir = log_dir
        self._utc_now = utc_now
        self._redact = redact or (lambda text: text)
        self._mirror = mirror
        self._file = None
        self._file_path: Optional[str] = None
        self.degraded = False
        self._ring: Deque[dict] = deque(maxlen=MEMORY_RING_CAPACITY)
        self.write_failure_count = 0
        if log_dir is not None:
            try:
                os.makedirs(log_dir, exist_ok=True)
                self._file_path = os.path.join(log_dir, f"{name}.log")
                self._file = open(self._file_path, "a", encoding="utf-8")
            except OSError:
                self.degraded = True
                self._file = None

    # -- 写入 ----------------------------------------------------------------

    def log(self, level: str, event_code: str, world_id: Optional[str] = None,
            ids: Optional[dict] = None, reason_code: Optional[str] = None,
            duration_ms: Optional[int] = None) -> None:
        if level not in LOG_LEVELS:
            level = "info"
        try:
            check_fields_policy(ids)
            # 自由文本字段在入环/入文件前统一脱敏：内存环与文件一致零泄漏
            if isinstance(reason_code, str):
                reason_code = self._redact(reason_code)
            record = {
                "timestamp": self._utc_now(),
                "level": level,
                "logger": self._name,
                "event_code": event_code,
                "world_id": world_id,
                "ids": dict(ids) if ids else None,
                "reason_code": reason_code,
                "duration_ms": duration_ms,
            }
            line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
            line = self._redact(line)  # 兜底：序列化后整行再过一次 Redaction
        except Exception:
            # fail closed：策略违规或 Redaction 异常 → 丢条，不明文写出
            self.write_failure_count += 1
            return
        if self._mirror is not None:
            try:
                self._mirror(record)
            except Exception:
                pass
        if self._file is None:
            self._ring.append(record)
            return
        try:
            self._file.write(line + "\n")
            self._file.flush()
            self._maybe_rotate()
        except OSError:
            self.write_failure_count += 1
            self._ring.append(record)

    def debug(self, event_code: str, **kwargs) -> None:
        self.log("debug", event_code, **kwargs)

    def info(self, event_code: str, **kwargs) -> None:
        self.log("info", event_code, **kwargs)

    def warning(self, event_code: str, **kwargs) -> None:
        self.log("warning", event_code, **kwargs)

    def error(self, event_code: str, **kwargs) -> None:
        self.log("error", event_code, **kwargs)

    # -- 轮转 ----------------------------------------------------------------

    def _maybe_rotate(self) -> None:
        if self._file is None or self._file_path is None:
            return
        try:
            if self._file.tell() < LOG_MAX_BYTES:
                return
            self._file.close()
            for index in range(LOG_KEEP_FILES - 1, 0, -1):
                older = f"{self._file_path}.{index}"
                newer = f"{self._file_path}.{index + 1}"
                if os.path.exists(older):
                    if index + 1 > LOG_KEEP_FILES:
                        os.remove(older)
                    else:
                        os.replace(older, newer)
            os.replace(self._file_path, f"{self._file_path}.1")
            self._file = open(self._file_path, "a", encoding="utf-8")
        except OSError:
            self.degraded = True
            self._file = None

    def ring_records(self) -> list:
        return list(self._ring)

    def close(self) -> None:
        if self._file is not None:
            try:
                self._file.close()
            except OSError:
                pass
            self._file = None
