"""
Narrative Pressure Budget 账本（RULE-EVENT-009..011）

- active 权重和 ≤ 12；crisis 并发 ≤ 1
- 事件进入 aftermath 后经 1440 game minutes 线性返还权重
- 冷却键 (template, scene)；灾害冷却下限 4320 分钟（admin 可越过冷却但仍占预算）
- Calm Window：无 moderate 以上新激活的连续区间；保证 7 日 ≥1 个 ≥1440 分钟
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .constants import (
    ACTIVE_WEIGHT_CAP,
    BUDGET_REFUND_GAME_MINUTES,
    CALM_WINDOW_MIN_GAME_MINUTES,
    CRISIS_CONCURRENCY_CAP,
    DISASTER_COOLDOWN_MIN_GAME_MINUTES,
    GAME_DAY_MINUTES,
    SEVERITY_WEIGHT,
)


class BudgetError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass
class _Reservation:
    world_event_id: str
    severity: str
    weight: int
    #: None = 仍在 active/escalated；否则为进入 aftermath 的 game_time
    aftermath_since: Optional[int] = None

    def effective_weight(self, game_time: int) -> float:
        if self.aftermath_since is None:
            return float(self.weight)
        elapsed = game_time - self.aftermath_since
        if elapsed >= BUDGET_REFUND_GAME_MINUTES:
            return 0.0
        return self.weight * (1.0 - elapsed / BUDGET_REFUND_GAME_MINUTES)


class NarrativePressureLedger:
    def __init__(self) -> None:
        self._reservations: Dict[str, _Reservation] = {}
        self._cooldowns: Dict[Tuple[str, str], int] = {}
        #: moderate 以上新激活时间线（Calm Window 统计）
        self._significant_activations: List[int] = []

    # -- 预算 ------------------------------------------------------------

    def current_pressure(self, game_time: int) -> float:
        return sum(r.effective_weight(game_time) for r in self._reservations.values())

    def active_crisis_count(self) -> int:
        return sum(
            1 for r in self._reservations.values() if r.severity == "crisis" and r.aftermath_since is None
        )

    def can_activate(self, severity: str, game_time: int) -> bool:
        weight = SEVERITY_WEIGHT[severity]
        if self.current_pressure(game_time) + weight > ACTIVE_WEIGHT_CAP:
            return False
        if severity == "crisis" and self.active_crisis_count() >= CRISIS_CONCURRENCY_CAP:
            return False
        return True

    def check_activate(self, severity: str, game_time: int) -> None:
        weight = SEVERITY_WEIGHT[severity]
        if self.current_pressure(game_time) + weight > ACTIVE_WEIGHT_CAP:
            raise BudgetError("budget_exceeded", f"pressure {self.current_pressure(game_time)} + {weight}")
        if severity == "crisis" and self.active_crisis_count() >= CRISIS_CONCURRENCY_CAP:
            raise BudgetError("budget_exceeded", "crisis concurrency cap")

    def reserve(self, world_event_id: str, severity: str, game_time: int) -> None:
        self.check_activate(severity, game_time)
        self._reservations[world_event_id] = _Reservation(
            world_event_id=world_event_id,
            severity=severity,
            weight=SEVERITY_WEIGHT[severity],
        )
        if severity in ("moderate", "major", "crisis"):
            self._significant_activations.append(game_time)
            self._significant_activations.sort()

    def release_to_aftermath(self, world_event_id: str, game_time: int) -> None:
        reservation = self._reservations.get(world_event_id)
        if reservation is not None and reservation.aftermath_since is None:
            reservation.aftermath_since = game_time

    def drop(self, world_event_id: str) -> None:
        """archive 时移除（aftermath 返还期可能未完，直接清零）"""
        self._reservations.pop(world_event_id, None)

    # -- 冷却 ------------------------------------------------------------

    def effective_cooldown(self, cooldown_game_minutes: int, is_disaster: bool) -> int:
        if is_disaster:
            return max(cooldown_game_minutes, DISASTER_COOLDOWN_MIN_GAME_MINUTES)
        return cooldown_game_minutes

    def cooldown_remaining(
        self, event_template_id: str, scene_id: str, game_time: int,
        cooldown_game_minutes: int, is_disaster: bool,
    ) -> int:
        last = self._cooldowns.get((event_template_id, scene_id))
        if last is None:
            return 0
        required = self.effective_cooldown(cooldown_game_minutes, is_disaster)
        return max(0, last + required - game_time)

    def check_cooldown(
        self, event_template_id: str, scene_id: str, game_time: int,
        cooldown_game_minutes: int, is_disaster: bool, admin: bool = False,
    ) -> None:
        remaining = self.cooldown_remaining(
            event_template_id, scene_id, game_time, cooldown_game_minutes, is_disaster
        )
        # admin 可越过冷却，但预算检查照常（由 reserve 负责）
        if remaining > 0 and not admin:
            raise BudgetError("cooldown_active", f"{event_template_id}@{scene_id} remaining {remaining}")

    def mark_activation(
        self, event_template_id: str, scene_id: str, game_time: int
    ) -> None:
        self._cooldowns[(event_template_id, scene_id)] = game_time

    # -- Calm Window -------------------------------------------------------

    def calm_windows(self, start: int, end: int) -> List[Tuple[int, int]]:
        """[start, end] 内无 moderate 以上新激活的连续区间列表（闭区间语义返回 (from, to)）"""
        points = [t for t in self._significant_activations if start < t < end]
        windows: List[Tuple[int, int]] = []
        cursor = start
        for point in points:
            if point - cursor >= CALM_WINDOW_MIN_GAME_MINUTES:
                windows.append((cursor, point))
            cursor = point
        if end - cursor >= CALM_WINDOW_MIN_GAME_MINUTES:
            windows.append((cursor, end))
        return windows

    def calm_window_ok(self, start: int, end: int, period_game_days: int = 7) -> bool:
        """每 period_game_days 窗口内至少一个完整 Calm Window"""
        period = period_game_days * GAME_DAY_MINUTES
        cursor = start
        while cursor < end:
            window_end = min(cursor + period, end)
            # 末窗口不足一个完整周期时按比例豁免（长跑结束余数）
            if window_end - cursor >= CALM_WINDOW_MIN_GAME_MINUTES:
                if not self.calm_windows(cursor, window_end):
                    return False
            cursor = window_end
        return True

    # -- 导出/导入 ---------------------------------------------------------

    def export_state(self) -> dict:
        return {
            "reservations": {
                event_id: {
                    "severity": r.severity,
                    "weight": r.weight,
                    "aftermath_since": r.aftermath_since,
                }
                for event_id, r in self._reservations.items()
            },
            "cooldowns": {f"{t}|{s}": ts for (t, s), ts in self._cooldowns.items()},
            "significant_activations": list(self._significant_activations),
        }

    def import_state(self, data: dict) -> None:
        self._reservations = {
            event_id: _Reservation(
                world_event_id=event_id,
                severity=r["severity"],
                weight=r["weight"],
                aftermath_since=r["aftermath_since"],
            )
            for event_id, r in data["reservations"].items()
        }
        self._cooldowns = {}
        for key, ts in data["cooldowns"].items():
            template_id, scene_id = key.split("|", 1)
            self._cooldowns[(template_id, scene_id)] = ts
        self._significant_activations = list(data["significant_activations"])
