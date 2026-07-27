"""
进程运行时状态（DOC-BACKEND-001 §5/§6；api 只读，bootstrap 驱动）

- Recovery Barrier：恢复序列未完成/失败时进程保持 Barrier，
  只暴露健康与诊断端点，写端点 BACKEND_CONFLICT_STATE
"""

from __future__ import annotations

from typing import Callable, Optional

PROCESS_STATES = frozenset({"booting", "recovering", "ready", "draining", "stopped"})


class ProcessRuntime:
    def __init__(self, monotonic_ms: Callable[[], int]) -> None:
        self._clock = monotonic_ms
        self._started_ms = monotonic_ms()
        self.state = "booting"
        self.recovery_barrier_active = True
        self.recovery_error: Optional[str] = None
        self.logging_degraded = False
        self.open_world_id: Optional[str] = None
        self.current_revision: int = 0

    def uptime_ms(self) -> int:
        return max(0, self._clock() - self._started_ms)

    def enter_recovering(self) -> None:
        self.state = "recovering"
        self.recovery_barrier_active = True

    def lift_barrier(self, open_world_id: Optional[str] = None) -> None:
        self.state = "ready"
        self.recovery_barrier_active = False
        self.recovery_error = None
        self.open_world_id = open_world_id

    def hold_barrier(self, reason_code: str) -> None:
        """恢复失败：保持 Barrier，只暴露健康与诊断"""
        self.state = "recovering"
        self.recovery_barrier_active = True
        self.recovery_error = reason_code

    def begin_drain(self) -> None:
        self.state = "draining"

    def health(self) -> dict:
        return {
            "schema_version": 1,
            "process_state": self.state,
            "recovery_barrier_active": self.recovery_barrier_active,
            "recovery_error": self.recovery_error,
            "open_world_id": self.open_world_id,
            "current_revision": self.current_revision,
            "uptime_ms": self.uptime_ms(),
            "logging_degraded": self.logging_degraded,
        }
