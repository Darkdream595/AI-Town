"""
启动配置（DOC-BACKEND-001 §5 关键配置项；RULE-BACKEND-001）

- 只读装配：进程启动时一次性构造，运行时不可变
- bind_host 必须是 loopback 字面量，否则启动拒绝（BACKEND_BIND_REFUSED）
- 端口被占用时顺延最多 8 个，全部占用则退出，不静默绑定非 loopback
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Mapping, Optional

from ..foundation.errors import ApiError

LOOPBACK_LITERALS = frozenset({"127.0.0.1", "::1"})
DEFAULT_PORT = 8765
PORT_SCAN_MAX = 8
PORT_MIN = 1024
PORT_MAX = 65535


@dataclass(frozen=True)
class BackendConfig:
    bind_host: str = "127.0.0.1"
    bind_port: int = DEFAULT_PORT
    static_dir: Optional[str] = None        # 前端打包产物；None 时 API 仍可服务
    data_dir: str = "data"
    max_body_bytes: int = 65536
    world_command_queue_capacity: int = 256
    ws_outbox_capacity: int = 512

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "BackendConfig":
        env = env if env is not None else os.environ
        port_raw = env.get("AI_TOWN_PORT", str(DEFAULT_PORT))
        try:
            port = int(port_raw)
        except ValueError:
            raise ApiError("BACKEND_BIND_REFUSED",
                           {"reason_code": f"port_not_integer:{port_raw}"}) from None
        return cls(
            bind_host=env.get("AI_TOWN_BIND_HOST", "127.0.0.1"),
            bind_port=port,
            static_dir=env.get("AI_TOWN_STATIC_DIR") or None,
            data_dir=env.get("AI_TOWN_DATA_DIR", "data"),
        )

    def validate(self) -> None:
        if self.bind_host not in LOOPBACK_LITERALS:
            raise ApiError("BACKEND_BIND_REFUSED",
                           {"reason_code": f"host_not_loopback:{self.bind_host}"})
        if not PORT_MIN <= self.bind_port <= PORT_MAX:
            raise ApiError("BACKEND_BIND_REFUSED",
                           {"reason_code": f"port_out_of_range:{self.bind_port}"})
        if self.max_body_bytes <= 0:
            raise ApiError("BACKEND_BIND_REFUSED",
                           {"reason_code": "max_body_bytes_invalid"})


def resolve_port(config: BackendConfig,
                 is_available: Callable[[str, int], bool],
                 scan_max: int = PORT_SCAN_MAX) -> int:
    """8765–8772 内顺延；全部占用 → BACKEND_BIND_REFUSED（RULE-BACKEND-001 §7）"""
    config.validate()
    for offset in range(scan_max):
        candidate = config.bind_port + offset
        if candidate > PORT_MAX:
            break
        if is_available(config.bind_host, candidate):
            return candidate
    raise ApiError("BACKEND_BIND_REFUSED", {
        "reason_code": "port_exhausted",
        "range": f"{config.bind_port}..{config.bind_port + scan_max - 1}"})
