"""
工作排班与收入（DOC-ECON-003）

- RULE-ECON-009：整数起止、end > start、单班最长 720 游戏分钟
- RULE-ECON-010：同一 work_session_id + credited_minute_range 只计一次
- RULE-ECON-011：只有持 Reservation、合法 location、未暂停的分钟计入
- RULE-ECON-012：雇主余额不足不 mint，应付额进入有界 wage_claim
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..foundation import generate_ulid
from .constants import MAX_CREDIT_INTERVAL_MINUTES, MAX_SHIFT_MINUTES, SessionState
from .currency import CurrencyError, CurrencyLedger


class ShiftError(Exception):
    """排班/结算失败；code 为稳定 reason code"""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True)
class ShiftDefinition:
    """ECON 发布的不可变班次计划"""

    shift_id: str
    employment_contract_id: str
    starts_at_game_time: int
    ends_at_game_time: int

    def __post_init__(self) -> None:
        if self.ends_at_game_time <= self.starts_at_game_time:
            raise ShiftError("shift_window_invalid", "end must be > start")
        if self.ends_at_game_time - self.starts_at_game_time > MAX_SHIFT_MINUTES:
            raise ShiftError(
                "shift_window_invalid",
                f"single shift must be <= {MAX_SHIFT_MINUTES} minutes",
            )

    @property
    def total_minutes(self) -> int:
        return self.ends_at_game_time - self.starts_at_game_time


@dataclass
class WageClaim:
    """RULE-ECON-012：有界欠薪凭证；需后续明确支付/调解/法律结果"""

    claim_id: str
    work_session_id: str
    employer_account_id: str
    worker_account_id: str
    amount_copper_feather: int
    state: str = "open"  # open / paid / mediated


@dataclass
class WorkSession:
    """DES-ECON-003 的运行时形态"""

    work_session_id: str
    employment_contract_id: str
    action_id: str
    scheduled_start_game_time: int
    scheduled_end_game_time: int
    wage_copper_feather_per_shift: int
    worker_reservation_id: str
    workplace_reservation_id: str
    employer_account_id: str
    worker_account_id: str
    credited_until_game_time: int
    credited_minutes: int = 0
    accrued_copper_feather: int = 0
    state: SessionState = SessionState.SCHEDULED
    last_revision: int = 0
    _credited_ranges: List[Tuple[int, int]] = field(default_factory=list)
    _payroll_command_id: Optional[str] = None

    @property
    def window_minutes(self) -> int:
        return self.scheduled_end_game_time - self.scheduled_start_game_time


class WorkSettlement:
    """WorkSession 状态机、credit 幂等与 payroll exactly-once"""

    def __init__(self, ledger: CurrencyLedger) -> None:
        self._ledger = ledger
        self._sessions: Dict[str, WorkSession] = {}
        self._credit_idempotency: Dict[Tuple[str, int, int], int] = {}
        self._payroll_results: Dict[str, object] = {}
        self._claims: List[WageClaim] = []

    def get(self, session_id: str) -> WorkSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise ShiftError("work_session_unknown", session_id)
        return session

    def claims(self) -> List[WageClaim]:
        return list(self._claims)

    # -- 开班 --

    def open_session(
        self,
        command_id: str,
        shift: ShiftDefinition,
        action_id: str,
        worker_reservation_id: Optional[str],
        workplace_reservation_id: Optional[str],
        wage_copper_feather_per_shift: int,
        employer_account_id: str,
        worker_account_id: str,
        game_time: int,
        arrived: bool = True,
    ) -> WorkSession:
        """RULE-ECON-011：无任一 Reservation 不得开班"""
        if not worker_reservation_id or not workplace_reservation_id:
            raise ShiftError(
                "reservation_missing", "worker and workplace reservations required"
            )
        session = WorkSession(
            work_session_id=generate_ulid(),
            employment_contract_id=shift.employment_contract_id,
            action_id=action_id,
            scheduled_start_game_time=shift.starts_at_game_time,
            scheduled_end_game_time=shift.ends_at_game_time,
            wage_copper_feather_per_shift=wage_copper_feather_per_shift,
            worker_reservation_id=worker_reservation_id,
            workplace_reservation_id=workplace_reservation_id,
            employer_account_id=employer_account_id,
            worker_account_id=worker_account_id,
            credited_until_game_time=shift.starts_at_game_time,
            state=SessionState.IN_PROGRESS if arrived else SessionState.SCHEDULED,
        )
        self._sessions[session.work_session_id] = session
        return session

    def arrive_session(self, command_id: str, session_id: str) -> WorkSession:
        """scheduled → in_progress：到岗后才可计工时"""
        session = self.get(session_id)
        if session.state is not SessionState.SCHEDULED:
            raise ShiftError("work_session_terminal", session.state.value)
        session.state = SessionState.IN_PROGRESS
        return session

    # -- 计工时 --

    def credit_work_interval(
        self,
        command_id: str,
        session_id: str,
        from_game_time: int,
        to_game_time: int,
        expected_revision: int,
        at_workplace: bool = True,
        game_time_frozen: bool = False,
    ) -> int:
        """
        返回本次新增 credited minutes。

        - 幂等键 (session_id, from, to)：重放返回 0 新增
        - 区间裁剪到班次窗口；与已计区间重叠（非完全相同）→ interval_overlap
        - game_time_frozen（0×）不新增任何分钟
        """
        session = self.get(session_id)
        idem_key = (session_id, from_game_time, to_game_time)
        if idem_key in self._credit_idempotency:
            return 0
        if session.state is not SessionState.IN_PROGRESS:
            raise ShiftError("work_session_terminal", session.state.value)
        if expected_revision != session.last_revision:
            raise ShiftError(
                "stale_revision",
                f"expected {expected_revision}, at {session.last_revision}",
            )
        if game_time_frozen:
            # RULE-ECON-011 / RULE-ECON-047：暂停不计工时
            self._credit_idempotency[idem_key] = 0
            return 0
        if not at_workplace:
            raise ShiftError("worker_not_at_workplace", session_id)
        if to_game_time <= from_game_time or to_game_time - from_game_time > MAX_CREDIT_INTERVAL_MINUTES:
            raise ShiftError("shift_window_invalid", "bad credit interval")

        start = max(from_game_time, session.scheduled_start_game_time)
        end = min(to_game_time, session.scheduled_end_game_time)
        credited = max(0, end - start)
        if credited > 0:
            for seen_start, seen_end in session._credited_ranges:
                if seen_start < end and start < seen_end:
                    raise ShiftError(
                        "interval_overlap",
                        f"[{start},{end}) overlaps [{seen_start},{seen_end})",
                    )
            session._credited_ranges.append((start, end))
            session.credited_minutes += credited
            session.credited_until_game_time = max(session.credited_until_game_time, end)
            # 确定性应付：按总已计分钟从整班工资折算（floor）
            session.accrued_copper_feather = (
                session.credited_minutes * session.wage_copper_feather_per_shift
            ) // session.window_minutes
            session.last_revision += 1
        self._credit_idempotency[idem_key] = credited
        return credited

    # -- 状态机 --

    def complete_session(self, command_id: str, session_id: str) -> WorkSession:
        session = self.get(session_id)
        if session.state is not SessionState.IN_PROGRESS:
            raise ShiftError("work_session_terminal", session.state.value)
        session.state = SessionState.COMPLETED
        return session

    def mark_missed(self, command_id: str, session_id: str) -> WorkSession:
        session = self.get(session_id)
        if session.state is not SessionState.SCHEDULED:
            raise ShiftError("work_session_terminal", session.state.value)
        session.state = SessionState.MISSED
        return session

    def interrupt_session(self, command_id: str, session_id: str) -> WorkSession:
        session = self.get(session_id)
        if session.state is not SessionState.IN_PROGRESS:
            raise ShiftError("work_session_terminal", session.state.value)
        session.state = SessionState.INTERRUPTED
        return session

    def resume_session(self, command_id: str, session_id: str, within_window: bool) -> WorkSession:
        session = self.get(session_id)
        if session.state is not SessionState.INTERRUPTED:
            raise ShiftError("work_session_terminal", session.state.value)
        if not within_window:
            # 窗口关闭：只能结算
            return session
        session.state = SessionState.IN_PROGRESS
        return session

    # -- 结算 --

    def settle_payroll(
        self,
        command_id: str,
        session_id: str,
        game_time: int,
    ) -> object:
        """
        RULE-ECON-010/012：payroll exactly-once；雇主余额不足形成 wage claim，
        不 mint、不负余额。崩溃恢复由 command 幂等返回原结果。
        """
        if command_id in self._payroll_results:
            return self._payroll_results[command_id]
        session = self.get(session_id)
        if session.state is SessionState.SETTLED:
            raise ShiftError("work_session_terminal", "already settled")
        if session.state is SessionState.IN_PROGRESS:
            raise ShiftError("work_session_terminal", "settle requires terminal state")
        # interrupted 超窗 / completed / missed（零应付）均可结算
        amount = session.accrued_copper_feather
        result: object
        if amount == 0:
            session.state = SessionState.SETTLED
            result = ("settled_zero", session.work_session_id, 0)
        else:
            try:
                self._ledger.post_legs(
                    command_id=f"{command_id}:legs",
                    legs=[
                        (session.employer_account_id, -amount),
                        (session.worker_account_id, amount),
                    ],
                    expected_revision=self._ledger.revision,
                )
            except CurrencyError as exc:
                if exc.code != "insufficient_funds":
                    raise
                claim = WageClaim(
                    claim_id=generate_ulid(),
                    work_session_id=session.work_session_id,
                    employer_account_id=session.employer_account_id,
                    worker_account_id=session.worker_account_id,
                    amount_copper_feather=amount,
                )
                self._claims.append(claim)
                session.state = SessionState.SETTLED
                result = ("wage_claim", claim.claim_id, amount)
            else:
                session.state = SessionState.SETTLED
                session._payroll_command_id = command_id
                result = ("paid", session.work_session_id, amount)
        self._payroll_results[command_id] = result
        return result
