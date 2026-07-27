"""
Redaction Filter（DOC-BACKEND-009 §RULE-BACKEND-053）

- 两类擦除：已注册 Secret 值的精确匹配、`sk-[A-Za-z0-9]{8,}` 模式匹配
- 命中一律替换为 [REDACTED]；fail closed——擦除异常时调用方必须丢弃该条输出
- 只有 security/ 包可注册明文值；指纹（SHA-256 前 12 hex）用于审计
"""

from __future__ import annotations

import hashlib
import re
from typing import Callable, List, Tuple

SECRET_PATTERN = re.compile(r"sk-[A-Za-z0-9]{8,}")
REDACTED = "[REDACTED]"
MAX_REGISTERED_VALUES = 8


def fingerprint_of(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()[:12]


class RedactionFilter:
    def __init__(self) -> None:
        self._values: List[str] = []

    def register_secret_value(self, plaintext: str) -> str:
        """注册需精确擦除的值（set_secret 时自动调用）；返回审计指纹"""
        if plaintext and plaintext not in self._values:
            if len(self._values) >= MAX_REGISTERED_VALUES:
                # 超出上限仍保留最早的（旧 Key 指纹保留至进程重启）
                self._values.pop(0)
            self._values.append(plaintext)
        return fingerprint_of(plaintext)

    def redact(self, text: str) -> str:
        """返回擦除后的文本；任何内部异常向外抛出（调用方 fail closed 丢条）"""
        redacted = text
        for value in self._values:
            if value:
                redacted = redacted.replace(value, REDACTED)
        return SECRET_PATTERN.sub(REDACTED, redacted)

    def redact_object(self, obj: object) -> object:
        """递归擦除 dict/list/str 结构"""
        if isinstance(obj, str):
            return self.redact(obj)
        if isinstance(obj, dict):
            return {key: self.redact_object(value) for key, value in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self.redact_object(item) for item in obj]
        return obj

    def contains_secret(self, text: str) -> bool:
        if any(value and value in text for value in self._values):
            return True
        return SECRET_PATTERN.search(text) is not None


def make_redaction_filter() -> Tuple[RedactionFilter, Callable[[str], str]]:
    """装配用：返回 (filter, redact callable)——diagnostics 只拿到 callable port"""
    redaction = RedactionFilter()
    return redaction, redaction.redact
