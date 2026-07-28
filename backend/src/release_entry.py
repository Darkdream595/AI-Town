"""Windows release launcher 入口（DOC-RELEASE-008）。

该模块只编排发布进程生命周期；世界数据始终交由 persistence 层管理，
异常清理仅触碰临时监听 socket、instance.json 与进程级 mutex。
"""
from __future__ import annotations

import ctypes
import json
import os
import socket
import sys
import threading
import urllib.request
import webbrowser
from pathlib import Path
from typing import Callable, Mapping

from .bootstrap.config import BackendConfig
from .persistence.launcher import (
    HealthPoller,
    delete_instance,
    generate_shutdown_token,
    read_instance,
    write_instance,
)

MUTEX_NAME = r"Local\AITown.Launcher.Singleton"
ERROR_ALREADY_EXISTS = 183
LOOPBACK_HOST = "127.0.0.1"


class InlineThread:
    """测试用同步线程适配器；生产路径仍使用 ``threading.Thread``。"""

    def __init__(self, *, target: Callable[[], None], daemon: bool = False) -> None:
        self._target = target

    def start(self) -> None:
        self._target()

    def join(self, timeout: float | None = None) -> None:
        return None


class WindowsSingletonMutex:
    """每用户会话单实例 mutex；非 Windows 平台导入本模块不会触发 Win32 调用。"""

    def __init__(self, name: str = MUTEX_NAME, kernel32=None) -> None:
        if kernel32 is None:
            if os.name != "nt":
                raise OSError("Windows singleton mutex is only available on Windows")
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel32 = kernel32
        self._name = name
        self._handle = None

    def acquire(self) -> bool:
        create_mutex = self._kernel32.CreateMutexW
        create_mutex.argtypes = (ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p)
        create_mutex.restype = ctypes.c_void_p
        ctypes.set_last_error(0)
        self._handle = create_mutex(None, True, self._name)
        if not self._handle:
            raise ctypes.WinError(ctypes.get_last_error())
        return ctypes.get_last_error() != ERROR_ALREADY_EXISTS

    def close(self) -> None:
        if self._handle:
            self._kernel32.CloseHandle(self._handle)
            self._handle = None


class _SingleProcessMutex:
    """非 Windows 开发/测试回退；正式发布包只在 Windows 上运行。"""

    def acquire(self) -> bool:
        return True

    def close(self) -> None:
        return None


def _default_mutex_factory():
    return WindowsSingletonMutex() if os.name == "nt" else _SingleProcessMutex()


def resolve_runtime_dir(environment: Mapping[str, str] | None = None) -> Path:
    environment = os.environ if environment is None else environment
    local_app_data = environment.get("LOCALAPPDATA")
    if not local_app_data:
        raise RuntimeError("LOCALAPPDATA is required for the Windows release launcher")
    return Path(local_app_data) / "AI-Town" / "runtime"


def bind_ephemeral_socket(
    socket_factory: Callable[[], socket.socket] | None = None,
) -> socket.socket:
    """先绑定 ``127.0.0.1:0``，消除选端口与 uvicorn 启动之间的竞争窗口。"""
    listener = socket_factory() if socket_factory else socket.socket(
        socket.AF_INET, socket.SOCK_STREAM
    )
    try:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((LOOPBACK_HOST, 0))
        listener.listen(socket.SOMAXCONN)
        return listener
    except BaseException:
        listener.close()
        raise


def _canonical_instance_url(record: dict | None) -> str | None:
    if not isinstance(record, dict):
        return None
    port = record.get("port")
    if not isinstance(port, int) or not 1 <= port <= 65535:
        return None
    expected = f"http://{LOOPBACK_HOST}:{port}/"
    return expected if record.get("url") == expected else None


def _fetch_health(url: str) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=1.0) as response:
            payload = json.load(response)
    except (OSError, ValueError):
        return None
    data = payload.get("data") if isinstance(payload, dict) else None
    return data if isinstance(data, dict) else None


def _default_assemble(
    config: BackendConfig,
    shutdown_token: str,
    shutdown_request: Callable[[], None],
    *,
    package_version: str,
    build_id: str,
):
    from .api.app import create_app
    from .bootstrap.startup import assemble, run_recovery_sequence

    assembled = assemble(config)
    assembled.runtime.package_version = package_version
    assembled.runtime.build_id = build_id
    assembled.runtime.package_integrity = "verified"
    assembled.services.shutdown_token = shutdown_token
    assembled.services.shutdown_request = shutdown_request
    run_recovery_sequence(assembled)
    return create_app(assembled.app_context), assembled


def _create_uvicorn_server(application, port: int):
    """Windowed EXE 没有 stderr，禁用 Uvicorn 的 stream formatter。"""
    import uvicorn

    uvicorn_config = uvicorn.Config(
        application,
        host=LOOPBACK_HOST,
        port=port,
        log_config=None,
        access_log=False,
    )
    return uvicorn.Server(uvicorn_config)


def _package_root() -> Path:
    executable = Path(sys.executable).resolve()
    if getattr(sys, "frozen", False):
        return executable.parent
    return Path(__file__).resolve().parents[2]


def run_launcher(
    *,
    runtime_dir: Path | str | None = None,
    package_version: str = "0.1.0",
    build_id: str = "release-local",
    static_dir: Path | str | None = None,
    data_dir: Path | str | None = None,
    mutex_factory: Callable[[], object] = _default_mutex_factory,
    socket_factory: Callable[[], socket.socket] | None = None,
    browser_open: Callable[[str], object] = webbrowser.open,
    health_fetch: Callable[[str], dict | None] = _fetch_health,
    assemble_runtime=None,
    server_factory=None,
    thread_factory=threading.Thread,
    pid: int | None = None,
    utc_now=None,
) -> str:
    """运行单实例 launcher，直到 uvicorn 正常退出或启动异常。

    依赖均可注入，确保 mutex、浏览器与 uvicorn 行为无需真实 GUI 即可测试。
    """
    runtime_path = Path(runtime_dir) if runtime_dir is not None else resolve_runtime_dir()
    mutex = mutex_factory()
    listener = None
    instance_written = False
    stop_health_poll = threading.Event()
    server_ref: dict[str, object] = {}

    try:
        if not mutex.acquire():
            existing_url = _canonical_instance_url(read_instance(runtime_path))
            if existing_url is not None:
                browser_open(existing_url)
            return "existing_instance"

        # mutex 已归当前进程所有，因此遗留记录只能来自上次崩溃。
        delete_instance(runtime_path)
        listener = bind_ephemeral_socket(socket_factory)
        port = int(listener.getsockname()[1])
        package_root = _package_root()
        config = BackendConfig(
            bind_host=LOOPBACK_HOST,
            bind_port=port,
            static_dir=str(static_dir or package_root / "assets" / "frontend"),
            data_dir=str(data_dir or Path(runtime_path).parent / "data"),
        )

        def request_shutdown() -> None:
            server = server_ref.get("server")
            if server is not None:
                server.should_exit = True

        token = generate_shutdown_token()
        if assemble_runtime is None:
            application, assembled = _default_assemble(
                config,
                token,
                request_shutdown,
                package_version=package_version,
                build_id=build_id,
            )
        else:
            application = assemble_runtime(config, token, request_shutdown)
            assembled = None

        if server_factory is None:
            server = _create_uvicorn_server(application, port)
        else:
            server = server_factory(application)
        server_ref["server"] = server

        write_arguments = {
            "pid": os.getpid() if pid is None else pid,
            "port": port,
            "package_version": package_version,
            "shutdown_token": token,
        }
        if utc_now is not None:
            write_arguments["utc_now"] = utc_now
        write_instance(runtime_path, **write_arguments)
        instance_written = True
        health_url = f"http://{LOOPBACK_HOST}:{port}/api/v1/health"
        game_url = f"http://{LOOPBACK_HOST}:{port}/"

        def wait_until_ready() -> None:
            def safe_fetch() -> dict | None:
                if stop_health_poll.is_set():
                    return {"process_state": "error"}
                try:
                    return health_fetch(health_url)
                except Exception:
                    return None

            outcome = HealthPoller(safe_fetch).poll(package_version)
            if outcome["outcome"] == "ready" and not stop_health_poll.is_set():
                browser_open(game_url)

        health_thread = thread_factory(target=wait_until_ready, daemon=True)
        health_thread.start()
        try:
            server.run(sockets=[listener])
        finally:
            stop_health_poll.set()
            health_thread.join(timeout=1.0)
            if assembled is not None:
                from .bootstrap.drain import run_graceful_drain

                run_graceful_drain(
                    assembled.runtime,
                    assembled.gateway,
                    assembled.services.monotonic_ms,
                )
        return "stopped"
    finally:
        stop_health_poll.set()
        if instance_written:
            delete_instance(runtime_path)
        if listener is not None:
            try:
                listener.close()
            except OSError:
                pass
        mutex.close()


def main() -> None:
    run_launcher()


if __name__ == "__main__":
    main()
