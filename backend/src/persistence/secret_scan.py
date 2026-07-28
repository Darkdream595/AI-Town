"""
共享 Secret Scanner（DOC-RELEASE-010 RULE-RELEASE-075）

判定规则集固定并版本化（SCANNER_RULESET_VERSION 随规则更新升版）：
(a) key 形态正则：sk- 前缀、32+ 位十六进制、40+ 位 Base64 连续串
(b) 凭据关键词邻接值：api_key/authorization/token/password/secret/credential
    后随非掩码值
(c) Secret Canary 精确匹配（测试环境注入的已知假凭据）
(d) 用户目录越界路径：允许根之外的绝对路径

扫描器由诊断包、世界导出、打包流水线共用。命中报告只含规则与位置，
绝不回显命中内容本身。
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from .constants import SCANNER_RULESET_VERSION

_RULE_A_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"\b[0-9a-fA-F]{32,}\b"),
    re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b"),
)

_RULE_B_PATTERN = re.compile(
    r"(?i)(api[_-]?key|authorization|token|password|secret|credential)"
    r"[\"'\s]*[:=][\"'\s]*([^\s\"',}]{4,})")

_MASKED = re.compile(r"^\*+$|^sk-\*+|^\[redacted\]$", re.IGNORECASE)

_WINDOWS_ABS = re.compile(r"\b[A-Za-z]:\\[^\s\"'<>:|?*]+")
#: 前邻冒号（如 https://）视为 URL 组成部分，不计越界路径
_UNIX_ABS = re.compile(r"(?<![\w/.:])(/[^\s\"'<>:|?*]+)+")
#: UNC 绝对路径（\\host\share）；一律越界（RULE-RELEASE-075(d)）
_UNC_ABS = re.compile(r"\\\\[^\s\"'<>:|?*]+")

#: 测试注入的已知假凭据（RULE-RELEASE-075(c)）
_CANARIES: set[str] = set()


def register_canary(value: str) -> None:
    _CANARIES.add(value)


def clear_canaries() -> None:
    _CANARIES.clear()


def _normalized_roots(allowed_roots: tuple) -> list[str]:
    roots = []
    for root in allowed_roots:
        roots.append(str(Path(root).resolve()).lower().replace("/", "\\"))
    return roots


def _path_allowed(path_text: str, roots: list[str]) -> bool:
    candidate = path_text.lower().replace("/", "\\")
    if candidate.startswith("\\\\"):
        return False  # UNC 路径一律越界
    return any(candidate == root or candidate.startswith(root + "\\")
               for root in roots)


def scan_text(text: str, allowed_roots: tuple = (),
              binary: bool = False,
              excluded_values: tuple = ()) -> dict:
    """对文本执行规则集 (a)-(d)；返回命中清单（规则 + 位置，不含内容）

    binary=True（SQLite 等二进制介质）：跳过十六进制/Base64 长串与越界
    路径规则——自有数据库合法存储 sha256 十六进制（file_sha256 等），
    且原始字节中的路径形态噪声不构成文本介质的路径泄漏面；
    sk- 前缀、关键词邻接、Canary 对二进制同样生效。

    excluded_values：调用方已知的结构性哈希值（如 manifest 的 sha256 字段、
    seed_hex），扫描前以等长占位替换，避免自有字段误命中 key 形态规则。
    """
    for value in excluded_values:
        if isinstance(value, str) and len(value) >= 8:
            text = text.replace(value, "\x00" * len(value))
    hits: list[dict] = []
    patterns = _RULE_A_PATTERNS[:1] if binary else _RULE_A_PATTERNS
    for pattern in patterns:
        for match in pattern.finditer(text):
            hits.append({"rule": "a_key_shape", "index": match.start()})
    for match in _RULE_B_PATTERN.finditer(text):
        value = match.group(2)
        if not _MASKED.match(value):
            hits.append({"rule": "b_credential_adjacency",
                         "index": match.start()})
    for canary in _CANARIES:
        start = text.find(canary)
        while start != -1:
            hits.append({"rule": "c_canary", "index": start})
            start = text.find(canary, start + 1)
    roots = _normalized_roots(allowed_roots)
    if not binary:
        for pattern in (_WINDOWS_ABS, _UNIX_ABS, _UNC_ABS):
            for match in pattern.finditer(text):
                candidate = match.group(0).rstrip("\\/")
                if not _path_allowed(candidate, roots):
                    hits.append({"rule": "d_path_out_of_bounds",
                                 "index": match.start()})
    hits.sort(key=lambda h: h["index"])
    return {"clean": not hits, "hits": hits,
            "scanner_ruleset_version": SCANNER_RULESET_VERSION}


def scan_bytes(data: bytes, allowed_roots: tuple = (),
               excluded_values: tuple = ()) -> dict:
    """字节入口：UTF-8 容错解码后按文本扫描；二进制自动识别"""
    binary = b"\x00" in data[:8192]
    text = data.decode("utf-8", errors="ignore")
    return scan_text(text, allowed_roots, binary=binary,
                     excluded_values=excluded_values)


def scan_paths(paths, allowed_roots: tuple = ()) -> dict:
    """多文件汇总扫描：hits 附带 path 字段（相对名，POSIX）"""
    combined: list[dict] = []
    roots = tuple(str(Path(r)) for r in allowed_roots)
    for path in paths:
        path = Path(path)
        report = scan_bytes(path.read_bytes(), roots)
        for hit in report["hits"]:
            combined.append({**hit, "path": PurePosixPath(path.name).as_posix()})
    return {"clean": not combined, "hits": combined,
            "scanner_ruleset_version": SCANNER_RULESET_VERSION}
