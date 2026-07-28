"""
发布包清单与内容校验（DOC-RELEASE-009）

- RULE-RELEASE-066：release-manifest.json = Version Triplet + 逐文件 SHA-256
- RULE-RELEASE-068：包内容黑名单（.env / *.sqlite3* / logs / diagnostics /
  测试 fixture / .git / old-dont-look* / Secret）
- RULE-RELEASE-069：licenses\\ 必须覆盖全部运行时依赖
- RULE-RELEASE-070：README UTF-8 BOM；Batch UTF-8 + chcp 65001
- §7：包内最长相对路径 ≤ 120 字符
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .constants import MANIFEST_FORMAT_VERSION

MANIFEST_NAME = "release-manifest.json"
MAX_RELATIVE_PATH = 120

#: RULE-RELEASE-068 黑名单（相对路径，POSIX 形态）
_BLACKLIST_PATTERNS = (
    re.compile(r"(^|/)\.env$"),
    re.compile(r"\.sqlite3(-wal|-shm)?$"),
    re.compile(r"(^|/)logs(/|$)"),
    re.compile(r"(^|/)diagnostics(/|$)"),
    re.compile(r"(^|/)\.git(/|$)"),
    re.compile(r"(^|/)old-dont-look[^/]*(/|$)"),
    re.compile(r"(^|/)secrets(/|$)"),
    re.compile(r"(^|/)node_modules(/|$)"),
    re.compile(r"\.map$"),
    re.compile(r"(^|/)tests?(/|$)"),
)


def _default_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iter_package_files(package_dir: Path) -> list[Path]:
    return sorted(p for p in package_dir.rglob("*")
                  if p.is_file() and p.name != MANIFEST_NAME)


def build_manifest(package_dir: Path | str, *, package_version: str,
                   build_id: str, migration_current: dict,
                   utc_now=_default_utc) -> dict:
    """DES-RELEASE-019 generate_manifest：覆盖包内除清单外全部文件"""
    package_dir = Path(package_dir)
    files = []
    longest = 0
    for path in _iter_package_files(package_dir):
        relative = path.relative_to(package_dir).as_posix()
        longest = max(longest, len(relative))
        files.append({"path": relative, "sha256": _sha256_file(path),
                      "size_bytes": path.stat().st_size})
    if longest > MAX_RELATIVE_PATH:
        raise ValueError(f"包内最长相对路径 {longest} > {MAX_RELATIVE_PATH}")
    return {
        "manifest_format_version": MANIFEST_FORMAT_VERSION,
        "product": "AI-Town",
        "package_version": package_version,
        "build_id": build_id,
        "build_time": utc_now(),
        "target": "windows-x64",
        "migration_manifest_current": dict(migration_current),
        "files": files,
    }


def verify_manifest(package_dir: Path | str, manifest: dict) -> dict:
    """RULE-RELEASE-066：逐文件哈希复算；缺失/多余/不符全部列出"""
    package_dir = Path(package_dir)
    expected = {entry["path"]: entry for entry in manifest.get("files", [])}
    actual = {p.relative_to(package_dir).as_posix(): p
              for p in _iter_package_files(package_dir)}
    mismatches, missing = [], []
    for relative, entry in expected.items():
        path = actual.get(relative)
        if path is None:
            missing.append(relative)
            continue
        if _sha256_file(path) != entry["sha256"] \
                or path.stat().st_size != entry["size_bytes"]:
            mismatches.append(relative)
    extra = sorted(set(actual) - set(expected))
    ok = not mismatches and not missing and not extra
    return {"ok": ok, "mismatches": sorted(mismatches),
            "missing": sorted(missing), "extra": extra}


def scan_package_blacklist(package_dir: Path | str) -> list[str]:
    """RULE-RELEASE-068：命中即打包失败"""
    package_dir = Path(package_dir)
    hits = []
    for path in _iter_package_files(package_dir):
        relative = path.relative_to(package_dir).as_posix()
        if any(p.search(relative) for p in _BLACKLIST_PATTERNS):
            hits.append(relative)
    return sorted(hits)


def verify_licenses(package_dir: Path | str, dependencies: list[str]) -> dict:
    """RULE-RELEASE-069：licenses\\ 覆盖率 100% 依赖清单"""
    package_dir = Path(package_dir)
    licenses_dir = package_dir / "licenses"
    notices = licenses_dir / "THIRD-PARTY-NOTICES.txt"
    missing = []
    for dependency in dependencies:
        license_file = licenses_dir / dependency / "LICENSE.txt"
        if not license_file.is_file():
            missing.append(dependency)
    return {"ok": not missing and notices.is_file(),
            "missing_dependencies": sorted(missing),
            "notices_present": notices.is_file()}


def check_readme_encoding(path: Path | str) -> bool:
    """RULE-RELEASE-070：玩家可读文件使用 UTF-8 with BOM"""
    data = Path(path).read_bytes()
    if not data.startswith(b"\xef\xbb\xbf"):
        return False
    try:
        data.decode("utf-8")
    except ValueError:
        return False
    return True


_BAT_REQUIRED = ("chcp 65001", "%~dp0")


def check_bat_content(path: Path | str) -> dict:
    """RULE-RELEASE-055/060/070：Batch 只做委派；绝不 taskkill 强杀

    taskkill 判定剥离 rem 注释与 echo 文本，只检查可执行行。
    """
    text = Path(path).read_text(encoding="utf-8")
    executable_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.lower().startswith(("rem ", "::", "echo ")):
            continue
        executable_lines.append(stripped.lower())
    executable = "\n".join(executable_lines)
    has_taskkill = "taskkill" in executable
    return {
        "has_chcp": "chcp 65001" in text,
        "delegates_with_dp0": "%~dp0" in text,
        "no_taskkill": not has_taskkill,
        "ok": all(required in text for required in _BAT_REQUIRED)
        and not has_taskkill,
    }


def verify_version_triplet(manifest: dict, runtime_meta: dict,
                           source_commit: str) -> dict:
    """RULE-RELEASE-066/090：manifest、运行进程、构建源 commit 三方一致"""
    checks = {
        "package_version_match":
            manifest.get("package_version") == runtime_meta.get("package_version"),
        "build_id_match":
            manifest.get("build_id") == runtime_meta.get("build_id")
            == source_commit,
    }
    checks["ok"] = all(checks.values())
    return checks
