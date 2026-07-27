"""AI Town FastAPI 主入口（DOC-BACKEND-001 §5/§6）

装配链：bootstrap.config → bootstrap.startup.assemble → run_recovery_sequence
→ api.app.create_app → uvicorn 绑定 127.0.0.1:port（RULE-BACKEND-001）
关闭链：SIGINT/SIGTERM → bootstrap.drain.run_graceful_drain（RULE-BACKEND-065）
"""

from __future__ import annotations

import socket

import uvicorn

from .api.app import create_app
from .bootstrap.config import BackendConfig, resolve_port
from .bootstrap.drain import run_graceful_drain
from .bootstrap.startup import assemble, run_recovery_sequence


def _port_available(host: str, port: int) -> bool:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        probe.close()


def build_application(config: BackendConfig | None = None):
    """装配进程并返回 (FastAPI app, AssembledRuntime, 实际端口)"""
    config = config or BackendConfig.from_env()
    port = resolve_port(config, _port_available)
    config = BackendConfig(
        bind_host=config.bind_host, bind_port=port,
        static_dir=config.static_dir, data_dir=config.data_dir,
        max_body_bytes=config.max_body_bytes,
        world_command_queue_capacity=config.world_command_queue_capacity,
        ws_outbox_capacity=config.ws_outbox_capacity)
    assembled = assemble(config)
    run_recovery_sequence(assembled)  # 失败保持 Barrier：健康/诊断仍可服务
    return create_app(assembled.app_context), assembled, port


app, _assembled, _port = build_application()


def main() -> None:
    try:
        uvicorn.run(app, host=_assembled.config.bind_host, port=_port,
                    log_level="info")
    finally:
        run_graceful_drain(_assembled.runtime, _assembled.gateway,
                           _assembled.services.monotonic_ms)


if __name__ == "__main__":
    main()
