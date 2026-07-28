"""DOC-RELEASE-009：离线发布打包工具链测试。"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = PROJECT_ROOT / "tools" / "release" / "release_packaging.py"
ENTRY_PATH = PROJECT_ROOT / "tools" / "release" / "backend_entry.py"
SPEC_PATH = PROJECT_ROOT / "release" / "AI-Town.spec"
BUILD_SCRIPT_PATH = PROJECT_ROOT / "release" / "build-release.ps1"


def _load_tool():
    spec = importlib.util.spec_from_file_location("release_packaging", TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_entry():
    spec = importlib.util.spec_from_file_location("backend_entry", ENTRY_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_sources(root: Path) -> dict[str, Path]:
    skeleton = root / "skeleton"
    (skeleton / "runtime").mkdir(parents=True)
    (skeleton / "关闭AI-Town.bat").write_text(
        "@echo off\nchcp 65001 >nul\n", encoding="utf-8")
    (skeleton / "README-开始游戏.txt").write_bytes(
        b"\xef\xbb\xbf" + "开始游戏".encode("utf-8"))
    (skeleton / "runtime" / "stop-ai-town.ps1").write_text(
        "Write-Host stop", encoding="utf-8")

    backend_bundle = root / "backend-bundle"
    (backend_bundle / "_internal").mkdir(parents=True)
    (backend_bundle / "AI-Town.exe").write_bytes(b"MZ-test")
    (backend_bundle / "_internal" / "python311.dll").write_bytes(b"dll")

    frontend_dist = root / "frontend-dist"
    (frontend_dist / "assets").mkdir(parents=True)
    (frontend_dist / "index.html").write_text("<main>AI Town</main>",
                                               encoding="utf-8")
    (frontend_dist / "assets" / "app.js").write_text("console.log('ok')",
                                                      encoding="utf-8")

    licenses = root / "licenses"
    (licenses / "python").mkdir(parents=True)
    (licenses / "THIRD-PARTY-NOTICES.txt").write_text(
        "python 3.11", encoding="utf-8")
    (licenses / "python" / "LICENSE.txt").write_text("PSF", encoding="utf-8")
    return {
        "skeleton": skeleton,
        "backend_bundle": backend_bundle,
        "frontend_dist": frontend_dist,
        "licenses": licenses,
    }


def test_pyinstaller_preflight_never_installs_missing_dependency():
    tool = _load_tool()
    calls: list[list[str]] = []

    def missing_runner(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 1, "", "No module named PyInstaller")

    with pytest.raises(tool.ReleasePackagingError,
                       match="PyInstaller.*未安装"):
        tool.require_pyinstaller("python.exe", runner=missing_runner)

    assert calls == [["python.exe", "-m", "PyInstaller", "--version"]]
    assert all("pip" not in part.lower() for part in calls[0])


def test_assemble_package_replaces_stale_output_and_has_fixed_layout(tmp_path):
    tool = _load_tool()
    sources = _make_sources(tmp_path)
    package_dir = tmp_path / "out" / "AI-Town"
    package_dir.mkdir(parents=True)
    (package_dir / "stale.txt").write_text("old", encoding="utf-8")

    tool.assemble_package(package_dir=package_dir, **sources)

    assert not (package_dir / "stale.txt").exists()
    assert (package_dir / "AI-Town.exe").is_file()
    assert (package_dir / "_internal" / "python311.dll").is_file()
    assert not (package_dir / "runtime" / "backend").exists()
    assert (package_dir / "assets" / "web" / "index.html").is_file()
    assert (package_dir / "licenses" / "python" / "LICENSE.txt").is_file()
    assert (package_dir / "关闭AI-Town.bat").is_file()
    assert not (package_dir / "启动AI小镇.bat").exists()


def test_replace_directory_retries_transient_windows_lock(tmp_path, monkeypatch):
    tool = _load_tool()
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    calls = []
    real_replace = tool.os.replace

    def transient_replace(current_source, current_destination):
        calls.append((current_source, current_destination))
        if len(calls) < 3:
            raise PermissionError("temporarily locked")
        real_replace(current_source, current_destination)

    monkeypatch.setattr(tool.os, "replace", transient_replace)
    monkeypatch.setattr(tool.time, "sleep", lambda _seconds: None)

    tool._replace_directory_with_retry(source, destination)

    assert len(calls) == 3
    assert destination.is_dir()


def test_publish_staging_restores_previous_package_on_swap_failure(
    tmp_path, monkeypatch
):
    tool = _load_tool()
    staging = tmp_path / "staging"
    destination = tmp_path / "AI-Town"
    staging.mkdir()
    destination.mkdir()
    (staging / "new.txt").write_text("new", encoding="utf-8")
    (destination / "old.txt").write_text("old", encoding="utf-8")
    real_replace = tool.os.replace

    def fail_new_package(source, target):
        if Path(source) == staging and Path(target) == destination:
            raise PermissionError("staging is temporarily locked")
        real_replace(source, target)

    monkeypatch.setattr(tool.os, "replace", fail_new_package)
    monkeypatch.setattr(tool.time, "sleep", lambda _seconds: None)

    with pytest.raises(PermissionError, match="temporarily locked"):
        tool._publish_staging_directory(staging, destination)

    assert (destination / "old.txt").read_text(encoding="utf-8") == "old"
    assert (staging / "new.txt").read_text(encoding="utf-8") == "new"


def test_assemble_rejects_frontend_sourcemaps_and_missing_notices(tmp_path):
    tool = _load_tool()
    sources = _make_sources(tmp_path)
    (sources["frontend_dist"] / "assets" / "app.js.map").write_text(
        "{}", encoding="utf-8")
    with pytest.raises(tool.ReleasePackagingError, match="sourcemap"):
        tool.assemble_package(package_dir=tmp_path / "package", **sources)

    (sources["frontend_dist"] / "assets" / "app.js.map").unlink()
    (sources["licenses"] / "THIRD-PARTY-NOTICES.txt").unlink()
    with pytest.raises(tool.ReleasePackagingError,
                       match="THIRD-PARTY-NOTICES"):
        tool.assemble_package(package_dir=tmp_path / "package", **sources)


def test_manifest_is_sorted_complete_and_hashes_every_file(tmp_path):
    tool = _load_tool()
    sources = _make_sources(tmp_path)
    package_dir = tmp_path / "AI-Town"
    tool.assemble_package(package_dir=package_dir, **sources)

    manifest = tool.generate_manifest(
        package_dir,
        package_version="1.2.3",
        build_id="abc1234",
        build_time="2026-07-28T12:00:00.000Z",
        migration_current={"app": 1, "world": 1},
    )

    paths = [entry["path"] for entry in manifest["files"]]
    assert paths == sorted(paths)
    assert "release-manifest.json" not in paths
    assert paths == sorted(
        path.relative_to(package_dir).as_posix()
        for path in package_dir.rglob("*")
        if path.is_file() and path.name != "release-manifest.json"
    )
    exe = next(entry for entry in manifest["files"]
               if entry["path"] == "AI-Town.exe")
    assert exe["sha256"] == hashlib.sha256(b"MZ-test").hexdigest()
    assert manifest["package_version"] == "1.2.3"
    assert manifest["build_id"] == "abc1234"


def test_json_object_argument_can_be_loaded_from_utf8_file(tmp_path):
    tool = _load_tool()
    source = tmp_path / "migration.json"
    source.write_text('{"app":1,"world":1}', encoding="utf-8")

    assert tool._parse_json_object(
        f"@{source}", "--migration-current"
    ) == {"app": 1, "world": 1}


def test_verify_package_detects_tampering_extra_blacklist_and_secret(tmp_path):
    tool = _load_tool()
    sources = _make_sources(tmp_path)
    package_dir = tmp_path / "AI-Town"
    tool.assemble_package(package_dir=package_dir, **sources)
    manifest = tool.generate_manifest(
        package_dir,
        package_version="1.0.0",
        build_id="abc1234",
        build_time="2026-07-28T12:00:00.000Z",
        migration_current={"app": 1, "world": 1},
    )
    tool.write_manifest(package_dir, manifest)
    assert tool.verify_package(package_dir)["ok"] is True

    (package_dir / "assets" / "web" / "index.html").write_text(
        "tampered", encoding="utf-8")
    (package_dir / "logs").mkdir()
    (package_dir / "logs" / "app.log").write_text("x", encoding="utf-8")
    (package_dir / "assets" / "web" / "extra.txt").write_text(
        "token=sk-abcdefghijklmnopqrstuvwxyz123456", encoding="utf-8")

    report = tool.verify_package(package_dir)
    assert report["ok"] is False
    assert report["manifest"]["mismatches"] == ["assets/web/index.html"]
    assert "assets/web/extra.txt" in report["manifest"]["extra"]
    assert "logs/app.log" in report["blacklist_hits"]
    assert report["secret_hits"] == [
        {"path": "assets/web/extra.txt", "rule": "secret_shape"}
    ]


def test_verify_package_requires_exact_layout_and_path_budget(tmp_path):
    tool = _load_tool()
    sources = _make_sources(tmp_path)
    package_dir = tmp_path / "AI-Town"
    tool.assemble_package(package_dir=package_dir, **sources)
    (package_dir / "AI-Town.exe").unlink()
    long_dir = package_dir / "assets" / "web" / ("长目录" * 40)
    long_dir.mkdir()
    (long_dir / "x.js").write_text("x", encoding="utf-8")
    manifest = tool.generate_manifest(
        package_dir,
        package_version="1.0.0",
        build_id="abc1234",
        build_time="2026-07-28T12:00:00.000Z",
        migration_current={"app": 1, "world": 1},
        enforce_path_budget=False,
    )
    tool.write_manifest(package_dir, manifest)

    report = tool.verify_package(package_dir)
    assert report["ok"] is False
    assert "AI-Town.exe" in report["missing_required"]
    assert report["longest_relative_path"] > 120


def test_cli_verify_emits_machine_readable_report(tmp_path):
    tool = _load_tool()
    sources = _make_sources(tmp_path)
    package_dir = tmp_path / "AI-Town"
    tool.assemble_package(package_dir=package_dir, **sources)
    manifest = tool.generate_manifest(
        package_dir,
        package_version="1.0.0",
        build_id="abc1234",
        build_time="2026-07-28T12:00:00.000Z",
        migration_current={"app": 1, "world": 1},
    )
    tool.write_manifest(package_dir, manifest)

    completed = subprocess.run(
        [sys.executable, str(TOOL_PATH), "verify", str(package_dir)],
        check=False, capture_output=True, text=True, encoding="utf-8")

    assert completed.returncode == 0
    assert json.loads(completed.stdout)["ok"] is True


def test_archive_is_reproducible_and_contains_single_package_root(tmp_path):
    tool = _load_tool()
    sources = _make_sources(tmp_path)
    package_dir = tmp_path / "AI-Town"
    tool.assemble_package(package_dir=package_dir, **sources)
    manifest = tool.generate_manifest(
        package_dir,
        package_version="1.0.0",
        build_id="abc1234",
        build_time="2026-07-28T12:00:00.000Z",
        migration_current={"app": 1, "world": 1},
    )
    tool.write_manifest(package_dir, manifest)
    first = tool.create_reproducible_zip(package_dir, tmp_path / "first.zip")
    second = tool.create_reproducible_zip(package_dir, tmp_path / "second.zip")

    assert hashlib.sha256(first.read_bytes()).digest() == hashlib.sha256(
        second.read_bytes()).digest()
    with zipfile.ZipFile(first) as archive:
        assert all(name.startswith("AI-Town/") for name in archive.namelist())
        assert all(info.date_time == (1980, 1, 1, 0, 0, 0)
                   for info in archive.infolist())


def test_crash_log_failure_does_not_mask_launcher_error(monkeypatch):
    entry = _load_entry()
    original_error = RuntimeError("launcher failed")
    monkeypatch.setattr(entry.multiprocessing, "freeze_support", lambda: None)
    monkeypatch.setattr(
        entry, "_configure_release_environment",
        lambda: (_ for _ in ()).throw(original_error),
    )
    monkeypatch.setattr(
        entry, "_write_crash_log",
        lambda _error: (_ for _ in ()).throw(OSError("disk full")),
    )

    with pytest.raises(RuntimeError, match="launcher failed") as captured:
        entry.main()

    assert captured.value is original_error


def test_frozen_backend_entry_package_root_is_executable_directory(
    monkeypatch, tmp_path
):
    entry = _load_entry()
    executable = tmp_path / "AI-Town.exe"
    monkeypatch.setattr(entry.sys, "frozen", True, raising=False)
    monkeypatch.setattr(entry.sys, "executable", str(executable))

    assert entry._package_root() == executable.resolve().parent


def test_spec_and_build_script_encode_offline_onefolder_pipeline():
    spec_text = SPEC_PATH.read_text(encoding="utf-8")
    entry_text = (PROJECT_ROOT / "tools" / "release" / "backend_entry.py").read_text(
        encoding="utf-8"
    )
    assert "tools/release/backend_entry.py" in spec_text.replace("\\", "/")
    assert "console=False" in spec_text
    assert "COLLECT(" in spec_text
    assert "name=\"AI-Town\"" in spec_text
    assert "from src.release_entry import run_launcher" in entry_text
    assert "from src.main import main" not in entry_text
    assert 'package_root / "assets" / "web"' in entry_text
    assert "launcher-crash.log" in entry_text

    script = BUILD_SCRIPT_PATH.read_text(encoding="utf-8")
    assert "$PSScriptRoot" in script
    assert "-m PyInstaller --version" in script
    assert "-m PyInstaller" in script
    assert "npm ci" in script
    assert "SkipNpmCi" in script
    assert "$SkipNpmCi -and -not $AllowDirty" in script
    assert "npm run build" in script
    assert "release_packaging.py" in script
    assert "pip install" not in script.lower()
