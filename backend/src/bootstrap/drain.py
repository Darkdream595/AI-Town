"""
Graceful Drain（RULE-BACKEND-065；DOC-BACKEND-001 §6.4）

六步序列，任何一步不产生半事务：
  1. 广播 error(BACKEND_SHUTDOWN) 预告帧（不关闭连接）
  2. 新命令一律 rejected(BACKEND_SHUTDOWN)（runtime 进入 draining，
     WS 经 accepting_commands 谓词、REST 经 _require_world_write 拒绝）
  3. 已入队命令在 10000 real ms 内完成，或统一 failed(BACKEND_SHUTDOWN) 回执
  4. 取消 AI 在途（DOC-AI-009 cancel 语义，可注入）
  5. flush Outbox 尽力送达后关闭全部连接
  6. checkpoint 并关库（可注入，persistence 阶段装配）

步骤级故障注入：每步异常被捕获并记入 DrainReport.failures，
序列继续推进——已提交状态不回滚，未提交事务全部回滚由步骤 6 owner 保证。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from ..orchestrator.runtime import ProcessRuntime

DRAIN_TIMEOUT_MS = 10_000

DRAIN_STEPS = (
    "broadcast_notice",
    "reject_new_commands",
    "complete_or_fail_queued",
    "cancel_ai_in_flight",
    "flush_outbox_close_connections",
    "checkpoint_close_store",
)


@dataclass
class DrainReport:
    steps_completed: List[str] = field(default_factory=list)
    failures: List[str] = field(default_factory=list)
    forced: bool = False  # 超过 10s 强制收尾（DOC-BACKEND-001 §8）

    @property
    def clean(self) -> bool:
        return not self.failures and len(self.steps_completed) == len(DRAIN_STEPS)


def run_graceful_drain(
        runtime: ProcessRuntime,
        gateway,                                   # WsGateway
        monotonic_ms: Callable[[], int],
        complete_queued: Optional[Callable[[int], None]] = None,
        cancel_ai_in_flight: Optional[Callable[[], None]] = None,
        checkpoint_close: Optional[Callable[[], None]] = None,
        timeout_ms: int = DRAIN_TIMEOUT_MS,
        sleep_ms: Callable[[int], None] = lambda ms: time.sleep(ms / 1000),
        ) -> DrainReport:
    """执行六步 Drain；幂等——重复调用从当前状态继续，不产生二次副作用"""
    report = DrainReport()
    started = monotonic_ms()

    def budget_exceeded() -> bool:
        return monotonic_ms() - started > timeout_ms

    # 步骤 1：预告帧
    try:
        gateway.notify_all("BACKEND_SHUTDOWN")
        report.steps_completed.append("broadcast_notice")
    except Exception as exc:  # noqa: BLE001
        report.failures.append(f"broadcast_notice:{exc!r}")

    # 步骤 2：进入 draining，拒绝新命令（谓词/REST 位点随即生效）
    try:
        runtime.begin_drain()
        report.steps_completed.append("reject_new_commands")
    except Exception as exc:  # noqa: BLE001
        report.failures.append(f"reject_new_commands:{exc!r}")

    # 步骤 3：已入队命令限期完成；超时则统一失败回执并强制推进
    try:
        if complete_queued is not None:
            complete_queued(timeout_ms)
        if budget_exceeded():
            report.forced = True
        report.steps_completed.append("complete_or_fail_queued")
    except Exception as exc:  # noqa: BLE001
        report.failures.append(f"complete_or_fail_queued:{exc!r}")
        report.forced = True

    # 步骤 4：取消 AI 在途
    try:
        if cancel_ai_in_flight is not None:
            cancel_ai_in_flight()
        report.steps_completed.append("cancel_ai_in_flight")
    except Exception as exc:  # noqa: BLE001
        report.failures.append(f"cancel_ai_in_flight:{exc!r}")

    # 步骤 5：尽力送达后关闭全部连接
    try:
        gateway.close_all("BACKEND_SHUTDOWN")
        report.steps_completed.append("flush_outbox_close_connections")
    except Exception as exc:  # noqa: BLE001
        report.failures.append(f"flush_outbox_close_connections:{exc!r}")

    # 步骤 6：checkpoint 并关库
    try:
        if checkpoint_close is not None:
            checkpoint_close()
        report.steps_completed.append("checkpoint_close_store")
    except Exception as exc:  # noqa: BLE001
        report.failures.append(f"checkpoint_close_store:{exc!r}")

    runtime.state = "stopped"
    return report
