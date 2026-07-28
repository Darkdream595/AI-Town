"""Windows release launcher 入口的生命周期测试（DOC-RELEASE-008）。"""
from __future__ import annotations

import json
import socket
import sys
from pathlib import Path
from types import SimpleNamespace

from src import release_entry


class _Mutex:
    def __init__(self, acquired: bool) -> None:
        self.acquired = acquired
        self.closed = False

    def acquire(self) -> bool:
        return self.acquired

    def close(self) -> None:
        self.closed = True


class _Server:
    def __init__(self) -> None:
        self.should_exit = False
        self.sockets = []
        self.bound_ports = []

    def run(self, *, sockets) -> None:
        self.sockets = sockets
        self.bound_ports = [item.getsockname()[1] for item in sockets]


def test_frozen_package_root_is_executable_directory(monkeypatch, tmp_path):
    executable = tmp_path / "AI-Town.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))

    assert release_entry._package_root() == Path(executable).resolve().parent


def test_bind_ephemeral_socket_uses_loopback_and_real_os_port():
    bound = release_entry.bind_ephemeral_socket()
    try:
        host, port = bound.getsockname()
        assert host == "127.0.0.1"
        assert 1 <= port <= 65535
    finally:
        bound.close()


def test_runtime_directory_uses_localappdata(tmp_path):
    assert release_entry.resolve_runtime_dir(
        {"LOCALAPPDATA": str(tmp_path)}
    ) == tmp_path / "AI-Town" / "runtime"


def test_windowed_uvicorn_disables_stream_logging(monkeypatch):
    captured = {}

    class FakeConfig:
        def __init__(self, application, **kwargs):
            captured["application"] = application
            captured.update(kwargs)

    class FakeServer:
        def __init__(self, config):
            self.config = config

    monkeypatch.setitem(
        sys.modules,
        "uvicorn",
        SimpleNamespace(Config=FakeConfig, Server=FakeServer),
    )

    application = object()
    server = release_entry._create_uvicorn_server(application, 43123)

    assert server.config is not None
    assert captured == {
        "application": application,
        "host": "127.0.0.1",
        "port": 43123,
        "log_config": None,
        "access_log": False,
    }


def test_second_instance_only_reopens_existing_loopback_url(tmp_path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "instance.json").write_text(json.dumps({
        "instance_format_version": 1,
        "pid": 123,
        "port": 43123,
        "url": "http://127.0.0.1:43123/",
        "package_version": "0.1.0",
        "started_at": "2026-07-28T00:00:00.000Z",
        "shutdown_token": "a" * 32,
    }), encoding="utf-8")
    opened = []
    mutex = _Mutex(False)

    result = release_entry.run_launcher(
        runtime_dir=runtime_dir,
        package_version="0.1.0",
        mutex_factory=lambda: mutex,
        browser_open=opened.append,
    )

    assert result == "existing_instance"
    assert opened == ["http://127.0.0.1:43123/"]
    assert mutex.closed is True


def test_first_instance_writes_record_opens_after_health_and_cleans(tmp_path):
    runtime_dir = tmp_path / "runtime"
    opened = []
    server = _Server()
    captured = {}
    mutex = _Mutex(True)

    def assemble_runtime(config, shutdown_token, shutdown_request):
        captured["config"] = config
        captured["shutdown_token"] = shutdown_token
        captured["shutdown_request"] = shutdown_request
        return object()

    result = release_entry.run_launcher(
        runtime_dir=runtime_dir,
        package_version="0.1.0",
        build_id="build-test",
        mutex_factory=lambda: mutex,
        browser_open=opened.append,
        health_fetch=lambda _url: {
            "process_state": "ready",
            "package_version": "0.1.0",
        },
        assemble_runtime=assemble_runtime,
        server_factory=lambda _application: server,
        pid=9876,
        utc_now=lambda: "2026-07-28T01:02:03.000Z",
        thread_factory=release_entry.InlineThread,
    )

    assert result == "stopped"
    assert captured["config"].bind_host == "127.0.0.1"
    assert captured["config"].bind_port > 0
    assert server.bound_ports == [captured["config"].bind_port]
    assert opened == [f"http://127.0.0.1:{captured['config'].bind_port}/"]
    assert not (runtime_dir / "instance.json").exists()
    assert mutex.closed is True


def test_shutdown_callback_sets_uvicorn_should_exit(tmp_path):
    server = _Server()
    callbacks = []

    def assemble_runtime(_config, _token, shutdown_request):
        callbacks.append(shutdown_request)
        return object()

    release_entry.run_launcher(
        runtime_dir=tmp_path,
        package_version="0.1.0",
        mutex_factory=lambda: _Mutex(True),
        browser_open=lambda _url: None,
        health_fetch=lambda _url: {
            "process_state": "ready",
            "package_version": "0.1.0",
        },
        assemble_runtime=assemble_runtime,
        server_factory=lambda _application: server,
        thread_factory=release_entry.InlineThread,
    )

    callbacks[0]()
    assert server.should_exit is True


def test_failure_path_closes_bound_socket_and_removes_only_instance_file(tmp_path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "instance.json").write_text(json.dumps({
        "instance_format_version": 1,
        "pid": 1,
        "port": 40000,
        "url": "http://127.0.0.1:40000/",
        "package_version": "old",
        "started_at": "2026-07-27T00:00:00.000Z",
        "shutdown_token": "b" * 32,
    }), encoding="utf-8")
    user_data = tmp_path / "world.db"
    user_data.write_text("keep", encoding="utf-8")
    created_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def fail_assembly(_config, _token, _shutdown):
        raise RuntimeError("assembly failed")

    try:
        result = release_entry.run_launcher(
            runtime_dir=runtime_dir,
            package_version="0.1.0",
            mutex_factory=lambda: _Mutex(True),
            socket_factory=lambda: created_socket,
            assemble_runtime=fail_assembly,
        )
    except RuntimeError as exc:
        assert str(exc) == "assembly failed"
    else:
        raise AssertionError(f"expected RuntimeError, got {result}")

    assert created_socket.fileno() == -1
    assert not (runtime_dir / "instance.json").exists()
    assert user_data.read_text(encoding="utf-8") == "keep"
