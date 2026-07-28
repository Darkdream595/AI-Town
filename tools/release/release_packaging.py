"""Windows one-folder 发布包的确定性组装与离线校验工具。

该工具只消费已经构建好的 frontend、PyInstaller bundle 和经人工确认的
licenses；它不会下载或安装任何依赖。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

MANIFEST_NAME = "release-manifest.json"
MAX_RELATIVE_PATH = 120
MAX_ZIP_BYTES = 800 * 1024 * 1024
TEXT_EXTENSIONS = frozenset({
    ".bat", ".cfg", ".css", ".html", ".ini", ".js", ".json", ".md",
    ".ps1", ".py", ".toml", ".txt", ".xml", ".yaml", ".yml",
})
REQUIRED_PATHS = (
    "AI-Town.exe",
    "_internal/python311.dll",
    "关闭AI-Town.bat",
    "README-开始游戏.txt",
    "runtime/stop-ai-town.ps1",
    "assets/web/index.html",
    "licenses/THIRD-PARTY-NOTICES.txt",
)
BLACKLIST_PATTERNS = (
    re.compile(r"(^|/)\.env($|/)"),
    re.compile(r"\.sqlite3(?:-wal|-shm)?$", re.IGNORECASE),
    re.compile(r"(^|/)(logs|diagnostics|node_modules|tests?|fixtures?)(/|$)",
               re.IGNORECASE),
    re.compile(r"(^|/)\.git(/|$)", re.IGNORECASE),
    re.compile(r"(^|/)old-dont-look[^/]*(/|$)", re.IGNORECASE),
    re.compile(r"\.(map|ts|tsx)$", re.IGNORECASE),
)
SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(
        r"(?i)(?:api[_-]?key|authorization|password|secret|token)"
        r"[\"'\s]*[:=][\"'\s]*(?!\*+|\[redacted\])[\w+/.-]{8,}"
    ),
)


class ReleasePackagingError(RuntimeError):
    """Fail-closed 的打包错误。"""


def _default_runner(command: list[str], **kwargs):
    return subprocess.run(command, **kwargs)


def require_pyinstaller(
    python_executable: str,
    *,
    runner: Callable = _default_runner,
) -> str:
    """只探测 PyInstaller；缺失时明确失败，绝不隐式安装。"""
    command = [python_executable, "-m", "PyInstaller", "--version"]
    try:
        completed = runner(
            command, check=False, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
    except OSError as error:
        raise ReleasePackagingError(
            f"无法执行 Python：{python_executable}（{error}）"
        ) from error
    if completed.returncode != 0:
        raise ReleasePackagingError(
            "PyInstaller 未安装或不可用；请在隔离的构建环境中显式安装"
            "经锁定版本后重试。工具不会自动执行 pip install。"
        )
    return completed.stdout.strip()


def _require_directory(path: Path, description: str) -> None:
    if not path.is_dir():
        raise ReleasePackagingError(f"{description}目录不存在：{path}")


def _copy_tree(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination, dirs_exist_ok=True, copy_function=shutil.copy2)


def _find_file_path_conflicts(
    skeleton: Path,
    backend_bundle: Path,
) -> list[str]:
    conflicts: list[str] = []
    for backend_path in backend_bundle.rglob("*"):
        relative = backend_path.relative_to(backend_bundle)
        skeleton_path = skeleton / relative
        if skeleton_path.exists() and (
            not skeleton_path.is_dir() or not backend_path.is_dir()
        ):
            conflicts.append(relative.as_posix())
    return sorted(conflicts)


def _validate_assembly_inputs(
    skeleton: Path,
    backend_bundle: Path,
    frontend_dist: Path,
    licenses: Path,
) -> None:
    for path, description in (
        (skeleton, "package skeleton"),
        (backend_bundle, "PyInstaller one-folder"),
        (frontend_dist, "frontend dist"),
        (licenses, "licenses"),
    ):
        _require_directory(path, description)
    for relative in ("AI-Town.exe", "_internal/python311.dll"):
        if not (backend_bundle / Path(relative)).is_file():
            raise ReleasePackagingError(
                f"PyInstaller bundle 缺少 {relative}：{backend_bundle}")
    conflicts = _find_file_path_conflicts(skeleton, backend_bundle)
    if conflicts:
        raise ReleasePackagingError(
            "package skeleton 与 PyInstaller bundle 路径冲突："
            + ", ".join(conflicts)
        )
    if not (frontend_dist / "index.html").is_file():
        raise ReleasePackagingError(
            f"frontend dist 缺少 index.html：{frontend_dist}")
    sourcemaps = sorted(
        path.relative_to(frontend_dist).as_posix()
        for path in frontend_dist.rglob("*.map")
    )
    if sourcemaps:
        raise ReleasePackagingError(
            "frontend dist 含禁止入包的 sourcemap：" + ", ".join(sourcemaps))
    notices = licenses / "THIRD-PARTY-NOTICES.txt"
    if not notices.is_file():
        raise ReleasePackagingError(
            f"licenses 缺少 THIRD-PARTY-NOTICES.txt：{licenses}")
    license_texts = [
        path for path in licenses.rglob("*")
        if path.is_file() and path.name.upper().startswith("LICENSE")
    ]
    if not license_texts:
        raise ReleasePackagingError("licenses 未包含任何依赖许可证文本")


def assemble_package(
    *,
    package_dir: Path | str,
    skeleton: Path | str,
    backend_bundle: Path | str,
    frontend_dist: Path | str,
    licenses: Path | str,
) -> Path:
    """原子组装固定 layout；失败时不留下半成品。"""
    package_dir = Path(package_dir).resolve()
    skeleton = Path(skeleton).resolve()
    backend_bundle = Path(backend_bundle).resolve()
    frontend_dist = Path(frontend_dist).resolve()
    licenses = Path(licenses).resolve()
    _validate_assembly_inputs(skeleton, backend_bundle, frontend_dist, licenses)

    package_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(
        prefix=f".{package_dir.name}-assembling-", dir=package_dir.parent))
    try:
        _copy_tree(skeleton, staging)
        _copy_tree(backend_bundle, staging)
        _copy_tree(frontend_dist, staging / "assets" / "web")
        _copy_tree(licenses, staging / "licenses")
        missing = [
            relative for relative in REQUIRED_PATHS
            if not (staging / Path(relative)).is_file()
        ]
        if missing:
            raise ReleasePackagingError(
                "组装结果缺少固定 layout 文件：" + ", ".join(missing))
        _publish_staging_directory(staging, package_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return package_dir


def _replace_directory_with_retry(
    source: Path,
    destination: Path,
    *,
    attempts: int = 10,
    delay_seconds: float = 0.2,
) -> None:
    """容忍 Windows 杀毒软件在复制完成后短暂持有目录句柄。"""
    for attempt in range(attempts):
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay_seconds)


def _publish_staging_directory(staging: Path, package_dir: Path) -> None:
    """原子切换发布目录；切换失败时恢复上一个有效包。"""
    backup = package_dir.with_name(
        f".{package_dir.name}-previous-{uuid.uuid4().hex}"
    )
    previous_moved = False
    try:
        if package_dir.exists():
            _replace_directory_with_retry(package_dir, backup)
            previous_moved = True
        _replace_directory_with_retry(staging, package_dir)
    except Exception:
        if previous_moved and backup.exists() and not package_dir.exists():
            _replace_directory_with_retry(backup, package_dir)
        raise
    if backup.exists():
        shutil.rmtree(backup, ignore_errors=True)


def _iter_package_files(package_dir: Path) -> list[Path]:
    return sorted(
        (
            path for path in package_dir.rglob("*")
            if path.is_file() and path.name != MANIFEST_NAME
        ),
        key=lambda path: path.relative_to(package_dir).as_posix(),
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(
        timespec="milliseconds").replace("+00:00", "Z")


def generate_manifest(
    package_dir: Path | str,
    *,
    package_version: str,
    build_id: str,
    migration_current: dict,
    build_time: str | None = None,
    enforce_path_budget: bool = True,
) -> dict:
    """生成覆盖 manifest 自身之外全部文件的有序 SHA-256 清单。"""
    package_dir = Path(package_dir).resolve()
    files = []
    longest = 0
    for path in _iter_package_files(package_dir):
        relative = path.relative_to(package_dir).as_posix()
        longest = max(longest, len(relative))
        files.append({
            "path": relative,
            "sha256": _sha256_file(path),
            "size_bytes": path.stat().st_size,
        })
    if enforce_path_budget and longest > MAX_RELATIVE_PATH:
        raise ReleasePackagingError(
            f"包内最长相对路径 {longest} > {MAX_RELATIVE_PATH}")
    return {
        "manifest_format_version": 1,
        "product": "AI-Town",
        "package_version": package_version,
        "build_id": build_id,
        "build_time": build_time or _utc_now(),
        "target": "windows-x64",
        "migration_manifest_current": migration_current,
        "files": files,
    }


def write_manifest(package_dir: Path | str, manifest: dict) -> Path:
    path = Path(package_dir) / MANIFEST_NAME
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n",
    )
    return path


def _manifest_report(package_dir: Path, manifest: dict) -> dict:
    expected = {
        entry["path"]: entry for entry in manifest.get("files", [])
        if isinstance(entry, dict) and isinstance(entry.get("path"), str)
    }
    actual = {
        path.relative_to(package_dir).as_posix(): path
        for path in _iter_package_files(package_dir)
    }
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    mismatches = []
    for relative in sorted(set(expected) & set(actual)):
        entry = expected[relative]
        path = actual[relative]
        if (
            entry.get("sha256") != _sha256_file(path)
            or entry.get("size_bytes") != path.stat().st_size
        ):
            mismatches.append(relative)
    return {
        "ok": not missing and not extra and not mismatches,
        "missing": missing,
        "extra": extra,
        "mismatches": mismatches,
    }


def _blacklist_hits(package_dir: Path) -> list[str]:
    hits = []
    for path in _iter_package_files(package_dir):
        relative = path.relative_to(package_dir).as_posix()
        if any(pattern.search(relative) for pattern in BLACKLIST_PATTERNS):
            hits.append(relative)
    return sorted(hits)


def _scan_secrets(package_dir: Path) -> list[dict[str, str]]:
    hits = []
    for path in _iter_package_files(package_dir):
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        relative = path.relative_to(package_dir).as_posix()
        text = path.read_text(encoding="utf-8", errors="ignore")
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            hits.append({"path": relative, "rule": "secret_shape"})
    return hits


def verify_package(package_dir: Path | str) -> dict:
    """不启动程序的离线结构、内容、Secret 与 manifest 复核。"""
    package_dir = Path(package_dir).resolve()
    missing_required = sorted(
        relative for relative in REQUIRED_PATHS
        if not (package_dir / Path(relative)).is_file()
    )
    all_files = [
        path for path in package_dir.rglob("*") if path.is_file()
    ] if package_dir.is_dir() else []
    longest = max(
        (len(path.relative_to(package_dir).as_posix()) for path in all_files),
        default=0,
    )
    manifest_path = package_dir / MANIFEST_NAME
    manifest_error = None
    manifest_report = {
        "ok": False, "missing": [], "extra": [], "mismatches": [],
    }
    if not manifest_path.is_file():
        manifest_error = "release-manifest.json missing"
    else:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest_report = _manifest_report(package_dir, manifest)
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, KeyError) as error:
            manifest_error = f"release-manifest.json invalid: {error}"
    blacklist_hits = _blacklist_hits(package_dir) if package_dir.is_dir() else []
    secret_hits = _scan_secrets(package_dir) if package_dir.is_dir() else []
    notices_present = (
        package_dir / "licenses" / "THIRD-PARTY-NOTICES.txt"
    ).is_file()
    license_texts = sorted(
        path.relative_to(package_dir).as_posix()
        for path in (package_dir / "licenses").rglob("*")
        if path.is_file() and path.name.upper().startswith("LICENSE")
    ) if (package_dir / "licenses").is_dir() else []
    top_files = sorted(
        (
            {"path": path.relative_to(package_dir).as_posix(),
             "size_bytes": path.stat().st_size}
            for path in all_files
        ),
        key=lambda entry: (-entry["size_bytes"], entry["path"]),
    )[:10]
    ok = (
        not missing_required
        and longest <= MAX_RELATIVE_PATH
        and manifest_error is None
        and manifest_report["ok"]
        and not blacklist_hits
        and not secret_hits
        and notices_present
        and bool(license_texts)
    )
    return {
        "ok": ok,
        "package_dir": str(package_dir),
        "missing_required": missing_required,
        "longest_relative_path": longest,
        "path_budget": MAX_RELATIVE_PATH,
        "manifest_error": manifest_error,
        "manifest": manifest_report,
        "blacklist_hits": blacklist_hits,
        "secret_hits": secret_hits,
        "licenses": {
            "notices_present": notices_present,
            "license_files": license_texts,
        },
        "total_size_bytes": sum(path.stat().st_size for path in all_files),
        "top_10_files": top_files,
    }


def create_reproducible_zip(
    package_dir: Path | str,
    output_path: Path | str,
) -> Path:
    """按路径排序并固定 ZIP 时间戳，避免构建机器时间污染归档。"""
    package_dir = Path(package_dir).resolve()
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    if temporary.exists():
        temporary.unlink()
    with zipfile.ZipFile(
        temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for path in sorted(
            (item for item in package_dir.rglob("*") if item.is_file()),
            key=lambda item: item.relative_to(package_dir).as_posix(),
        ):
            relative = Path(package_dir.name) / path.relative_to(package_dir)
            info = zipfile.ZipInfo(relative.as_posix(), (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes(), compresslevel=9)
    archive_size = temporary.stat().st_size
    if archive_size > MAX_ZIP_BYTES:
        temporary.unlink()
        raise ReleasePackagingError(
            f"发布 ZIP 超过 800 MiB：{archive_size}")
    os.replace(temporary, output_path)
    return output_path


def _parse_json_object(value: str, option_name: str) -> dict:
    if value.startswith("@"):
        source = Path(value[1:])
        try:
            value = source.read_text(encoding="utf-8-sig")
        except OSError as error:
            raise ReleasePackagingError(
                f"{option_name} JSON 文件不可读：{source}（{error}）"
            ) from error
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise ReleasePackagingError(
            f"{option_name} 不是合法 JSON：{error}") from error
    if not isinstance(parsed, dict):
        raise ReleasePackagingError(f"{option_name} 必须是 JSON object")
    return parsed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--python", required=True)

    assemble = subparsers.add_parser("assemble")
    assemble.add_argument("--package-dir", required=True)
    assemble.add_argument("--skeleton", required=True)
    assemble.add_argument("--backend-bundle", required=True)
    assemble.add_argument("--frontend-dist", required=True)
    assemble.add_argument("--licenses", required=True)

    manifest = subparsers.add_parser("manifest")
    manifest.add_argument("package_dir")
    manifest.add_argument("--package-version", required=True)
    manifest.add_argument("--build-id", required=True)
    manifest.add_argument("--build-time", required=True)
    manifest.add_argument("--migration-current", required=True)

    verify = subparsers.add_parser("verify")
    verify.add_argument("package_dir")
    verify.add_argument("--report")

    archive = subparsers.add_parser("archive")
    archive.add_argument("package_dir")
    archive.add_argument("output_path")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "preflight":
            print(json.dumps(
                {"ok": True, "pyinstaller_version":
                 require_pyinstaller(args.python)},
                ensure_ascii=False,
            ))
        elif args.command == "assemble":
            path = assemble_package(
                package_dir=args.package_dir,
                skeleton=args.skeleton,
                backend_bundle=args.backend_bundle,
                frontend_dist=args.frontend_dist,
                licenses=args.licenses,
            )
            print(json.dumps({"ok": True, "package_dir": str(path)},
                             ensure_ascii=False))
        elif args.command == "manifest":
            manifest = generate_manifest(
                args.package_dir,
                package_version=args.package_version,
                build_id=args.build_id,
                build_time=args.build_time,
                migration_current=_parse_json_object(
                    args.migration_current, "--migration-current"),
            )
            path = write_manifest(args.package_dir, manifest)
            print(json.dumps({"ok": True, "manifest": str(path)},
                             ensure_ascii=False))
        elif args.command == "verify":
            report = verify_package(args.package_dir)
            serialized = json.dumps(report, ensure_ascii=False, indent=2)
            if args.report:
                Path(args.report).write_text(
                    serialized + "\n", encoding="utf-8", newline="\n")
            print(serialized)
            return 0 if report["ok"] else 1
        elif args.command == "archive":
            path = create_reproducible_zip(args.package_dir, args.output_path)
            print(json.dumps({"ok": True, "archive": str(path)},
                             ensure_ascii=False))
    except ReleasePackagingError as error:
        print(json.dumps({"ok": False, "error": str(error)},
                         ensure_ascii=False), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
