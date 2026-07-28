from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEVELOPMENT_LAUNCHER = PROJECT_ROOT / "tools" / "dev" / "启动开发环境.bat"


def test_development_launcher_is_not_kept_at_project_root() -> None:
    assert not (PROJECT_ROOT / "启动AI小镇.bat").exists()


def test_development_launcher_is_kept_under_tools() -> None:
    assert DEVELOPMENT_LAUNCHER.is_file()


def test_development_launcher_resolves_project_root_from_its_own_path() -> None:
    script = DEVELOPMENT_LAUNCHER.read_text(encoding="utf-8")

    assert 'set "PROJECT_ROOT=%~dp0..\\.."' in script
    assert 'cd /d "%PROJECT_ROOT%"' in script
