"""TEST-RELEASE-033..036：发布包布局与清单（DOC-RELEASE-009）"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from release_helpers import make_utc_factory  # noqa: F401

from src.persistence import release_manifest
from src.persistence.constants import MANIFEST_FORMAT_VERSION

SKELETON_DIR = (Path(__file__).resolve().parents[2]
                / "release" / "package_skeleton")

MIGRATION_CURRENT = {"app": {"current": 1, "min_supported": 1},
                     "world": {"current": 1, "min_supported": 1}}


def _make_package(root: Path) -> Path:
    """构造最小合法包目录（DES-RELEASE-018 布局子集）"""
    (root / "runtime" / "backend" / "_internal").mkdir(parents=True)
    (root / "runtime" / "backend" / "AI-Town.exe").write_bytes(b"MZ-fake")
    (root / "runtime" / "backend" / "_internal" / "app.py").write_text(
        "print('hi')", encoding="utf-8")
    (root / "assets" / "web").mkdir(parents=True)
    (root / "assets" / "web" / "index.html").write_text(
        "<html></html>", encoding="utf-8")
    (root / "licenses" / "python").mkdir(parents=True)
    (root / "licenses" / "python" / "LICENSE.txt").write_text(
        "PSF", encoding="utf-8")
    (root / "licenses" / "THIRD-PARTY-NOTICES.txt").write_text(
        "python 3.11", encoding="utf-8")
    (root / "README-开始游戏.txt").write_bytes(
        b"\xef\xbb\xbf" + "说明".encode("utf-8"))
    return root


class TestPackageLayout:  # TEST-RELEASE-033：RULE-RELEASE-063..065
    def test_skeleton_entries_present(self):
        """骨架含玩家可见四件套；manifest 由流水线生成故不在骨架"""
        names = {p.name for p in SKELETON_DIR.iterdir()}
        assert {"启动AI小镇.bat", "停止AI小镇.bat",
                "README-开始游戏.txt", "runtime"} <= names
        assert (SKELETON_DIR / "runtime" / "stop-ai-town.ps1").is_file()

    def test_skeleton_contains_no_dev_artifacts(self):
        """RULE-RELEASE-064/065：零开发依赖，无 node_modules/源码/sourcemap"""
        bad = []
        for path in SKELETON_DIR.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(SKELETON_DIR).as_posix().lower()
            if ("node_modules" in relative or relative.endswith(".map")
                    or relative.endswith((".ts", ".tsx", ".py"))):
                bad.append(relative)
        assert bad == []

    def test_skeleton_no_user_data_dirs(self):
        """RULE-RELEASE-063：运行期数据绝不写入包目录"""
        for banned in ("worlds", "logs", "diagnostics", "secrets", "trash"):
            assert not (SKELETON_DIR / banned).exists()

    def test_relative_path_budget(self, tmp_path):
        """§7：包内最长相对路径 ≤ 120 字符"""
        package = _make_package(tmp_path / "pkg")
        manifest = release_manifest.build_manifest(
            package, package_version="0.1.0", build_id="abc123",
            migration_current=MIGRATION_CURRENT,
            utc_now=make_utc_factory())
        longest = max(len(f["path"]) for f in manifest["files"])
        assert longest <= release_manifest.MAX_RELATIVE_PATH

    def test_overlong_path_rejected(self, tmp_path):
        package = _make_package(tmp_path / "pkg")
        deep = package / "assets" / "web"
        name = "非常长的目录名" * 20  # 相对路径 > 120 字符
        (deep / name).mkdir()
        (deep / name / "x.js").write_text("x", encoding="utf-8")
        with pytest.raises(ValueError):
            release_manifest.build_manifest(
                package, package_version="0.1.0", build_id="abc123",
                migration_current=MIGRATION_CURRENT)


class TestManifestConsistency:  # TEST-RELEASE-034：RULE-RELEASE-066/067
    def test_build_manifest_fields(self, tmp_path):
        package = _make_package(tmp_path / "pkg")
        manifest = release_manifest.build_manifest(
            package, package_version="0.1.0", build_id="deadbeef",
            migration_current=MIGRATION_CURRENT,
            utc_now=make_utc_factory())
        assert manifest["manifest_format_version"] == MANIFEST_FORMAT_VERSION
        assert manifest["product"] == "AI-Town"
        assert manifest["package_version"] == "0.1.0"
        assert manifest["build_id"] == "deadbeef"
        assert manifest["target"] == "windows-x64"
        assert manifest["migration_manifest_current"] == MIGRATION_CURRENT
        assert manifest["build_time"].endswith("Z")
        # 逐文件 SHA-256 + 大小；清单自身不列入
        paths = {f["path"] for f in manifest["files"]}
        assert "release-manifest.json" not in paths
        assert "runtime/backend/AI-Town.exe" in paths
        for entry in manifest["files"]:
            assert len(entry["sha256"]) == 64
            assert entry["size_bytes"] >= 0

    def test_verify_roundtrip_ok(self, tmp_path):
        package = _make_package(tmp_path / "pkg")
        manifest = release_manifest.build_manifest(
            package, package_version="0.1.0", build_id="abc",
            migration_current=MIGRATION_CURRENT)
        result = release_manifest.verify_manifest(package, manifest)
        assert result == {"ok": True, "mismatches": [],
                          "missing": [], "extra": []}

    def test_verify_detects_tampering(self, tmp_path):
        package = _make_package(tmp_path / "pkg")
        manifest = release_manifest.build_manifest(
            package, package_version="0.1.0", build_id="abc",
            migration_current=MIGRATION_CURRENT)
        (package / "assets" / "web" / "index.html").write_text(
            "<html>tampered</html>", encoding="utf-8")
        result = release_manifest.verify_manifest(package, manifest)
        assert result["ok"] is False
        assert result["mismatches"] == ["assets/web/index.html"]

    def test_verify_detects_missing_and_extra(self, tmp_path):
        package = _make_package(tmp_path / "pkg")
        manifest = release_manifest.build_manifest(
            package, package_version="0.1.0", build_id="abc",
            migration_current=MIGRATION_CURRENT)
        (package / "runtime" / "backend" / "AI-Town.exe").unlink()
        (package / "assets" / "web" / "sneaky.js").write_text(
            "x", encoding="utf-8")
        result = release_manifest.verify_manifest(package, manifest)
        assert result["ok"] is False
        assert result["missing"] == ["runtime/backend/AI-Town.exe"]
        assert result["extra"] == ["assets/web/sneaky.js"]

    def test_version_triplet_comparison(self):
        manifest = {"package_version": "0.1.0", "build_id": "abc123"}
        runtime = {"package_version": "0.1.0", "build_id": "abc123"}
        result = release_manifest.verify_version_triplet(
            manifest, runtime, "abc123")
        assert result["ok"] is True
        bad = release_manifest.verify_version_triplet(
            manifest, {"package_version": "0.1.0", "build_id": "different"},
            "abc123")
        assert bad["ok"] is False
        assert bad["build_id_match"] is False


class TestBlacklistAndLicenses:  # TEST-RELEASE-035：RULE-RELEASE-068/069
    @pytest.mark.parametrize("relative", [
        ".env",
        "config/.env",
        "worlds/01ABC/world.sqlite3",
        "worlds/01ABC/world.sqlite3-wal",
        "worlds/01ABC/world.sqlite3-shm",
        "logs/app-20260728.log",
        "diagnostics/aitown-diag-x.zip",
        ".git/HEAD",
        "old-dont-look/secret.txt",
        "old-dont-look-anything/x.bin",
        "secrets/deepseek-api-key.dpapi",
        "node_modules/phaser/package.json",
        "assets/web/bundle.js.map",
        "tests/fixture.json",
        "runtime/backend/_internal/test/data.json",
    ])
    def test_blacklist_patterns_hit(self, tmp_path, relative):
        package = _make_package(tmp_path / "pkg")
        target = package / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"x")
        hits = release_manifest.scan_package_blacklist(package)
        assert relative in hits

    def test_clean_package_has_no_hits(self, tmp_path):
        package = _make_package(tmp_path / "pkg")
        assert release_manifest.scan_package_blacklist(package) == []

    def test_licenses_full_coverage(self, tmp_path):
        package = _make_package(tmp_path / "pkg")
        result = release_manifest.verify_licenses(package, ["python"])
        assert result["ok"] is True
        assert result["missing_dependencies"] == []
        assert result["notices_present"] is True

    def test_licenses_missing_dependency_detected(self, tmp_path):
        package = _make_package(tmp_path / "pkg")
        result = release_manifest.verify_licenses(
            package, ["python", "phaser", "fastapi"])
        assert result["ok"] is False
        assert result["missing_dependencies"] == ["fastapi", "phaser"]

    def test_licenses_missing_notices_detected(self, tmp_path):
        package = _make_package(tmp_path / "pkg")
        (package / "licenses" / "THIRD-PARTY-NOTICES.txt").unlink()
        result = release_manifest.verify_licenses(package, ["python"])
        assert result["ok"] is False
        assert result["notices_present"] is False


class TestEncoding:  # TEST-RELEASE-036：RULE-RELEASE-070
    def test_shipped_readme_has_utf8_bom(self):
        assert release_manifest.check_readme_encoding(
            SKELETON_DIR / "README-开始游戏.txt") is True

    def test_readme_without_bom_rejected(self, tmp_path):
        path = tmp_path / "README.txt"
        path.write_text("无 BOM 中文", encoding="utf-8")
        assert release_manifest.check_readme_encoding(path) is False

    def test_readme_invalid_utf8_rejected(self, tmp_path):
        path = tmp_path / "README.txt"
        path.write_bytes(b"\xef\xbb\xbf" + "中文".encode("gbk"))
        assert release_manifest.check_readme_encoding(path) is False

    def test_shipped_readme_chinese_readable(self):
        text = (SKELETON_DIR / "README-开始游戏.txt").read_text(
            encoding="utf-8-sig")
        assert "AI" in text and len(text) > 50
        # 常见乱码标志不应出现
        assert "ï»¿" not in text and "锘" not in text

    def test_bat_files_utf8_with_chcp(self):
        for name in ("启动AI小镇.bat", "停止AI小镇.bat"):
            raw = (SKELETON_DIR / name).read_bytes()
            raw.decode("utf-8")  # 必须可 UTF-8 解码
            result = release_manifest.check_bat_content(SKELETON_DIR / name)
            assert result["has_chcp"] is True
            assert result["ok"] is True
