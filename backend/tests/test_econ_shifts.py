"""
TEST-ECON-009..012：工作排班与收入（DOC-ECON-003）

- TEST-ECON-009：班次边界裁剪与窗口外 0 计
- TEST-ECON-010：credit 幂等 + payroll exactly-once
- TEST-ECON-011：批量与逐分钟 credit 等价；0× 暂停不计工时
- TEST-ECON-012：欠薪 wage claim、崩溃恢复幂等与 missed 零结算
"""

import pytest

from src.economy import (
    AccountKind,
    CurrencyLedger,
    SessionState,
    ShiftDefinition,
    ShiftError,
    WorkSettlement,
)
from src.economy.constants import MAX_SHIFT_MINUTES

AUTHORITIES = frozenset({"world_bootstrap"})


def _settlement(employer_balance: int = 1000):
    ledger = CurrencyLedger()
    employer = ledger.open_account("cmd-open-e", "shop.fixture.owner", AccountKind.SHOP, 0)
    worker = ledger.open_account("cmd-open-w", "resident.fixture.worker", AccountKind.RESIDENT, 0)
    if employer_balance:
        ledger.mint("cmd-mint-e", employer.account_id, employer_balance, "world_bootstrap", AUTHORITIES)
    return WorkSettlement(ledger), ledger, employer, worker


def _open_session(settlement, employer, worker, start=480, end=720, wage=180, arrived=True):
    shift = ShiftDefinition(
        shift_id="shift.fixture.1",
        employment_contract_id="contract.fixture.1",
        starts_at_game_time=start,
        ends_at_game_time=end,
    )
    return settlement.open_session(
        "cmd-open-session",
        shift,
        action_id="action.fixture.1",
        worker_reservation_id="reservation.worker.1",
        workplace_reservation_id="reservation.workplace.1",
        wage_copper_feather_per_shift=wage,
        employer_account_id=employer.account_id,
        worker_account_id=worker.account_id,
        game_time=start,
        arrived=arrived,
    )


class TestShiftBoundaries:
    """TEST-ECON-009"""

    def test_shift_definition_validation(self):
        with pytest.raises(ShiftError) as excinfo:
            ShiftDefinition("s", "c", 720, 480)
        assert excinfo.value.code == "shift_window_invalid"
        with pytest.raises(ShiftError) as excinfo:
            ShiftDefinition("s", "c", 0, MAX_SHIFT_MINUTES + 1)
        assert excinfo.value.code == "shift_window_invalid"

    def test_credit_clipped_to_window(self):
        settlement, _ledger, employer, worker = _settlement()
        session = _open_session(settlement, employer, worker)
        first = settlement.credit_work_interval(
            "cmd-credit-1", session.work_session_id, 480, 600, expected_revision=0
        )
        second = settlement.credit_work_interval(
            "cmd-credit-2", session.work_session_id, 600, 720, expected_revision=1
        )
        assert (first, second) == (120, 120)
        assert session.credited_minutes == 240
        # 窗口外区间裁剪为 0：右侧 [720,721) 与左侧 [400,480) 都不计
        assert settlement.credit_work_interval(
            "cmd-credit-3", session.work_session_id, 720, 721, expected_revision=2
        ) == 0
        assert settlement.credit_work_interval(
            "cmd-credit-4", session.work_session_id, 400, 480, expected_revision=2
        ) == 0
        assert session.credited_minutes == 240

    def test_open_session_requires_reservations(self):
        settlement, _ledger, employer, worker = _settlement()
        shift = ShiftDefinition("s", "c", 480, 720)
        with pytest.raises(ShiftError) as excinfo:
            settlement.open_session(
                "cmd-open-bad", shift, "a", None, "res.workplace",
                180, employer.account_id, worker.account_id, 480,
            )
        assert excinfo.value.code == "reservation_missing"

    def test_overlap_rejected(self):
        settlement, _ledger, employer, worker = _settlement()
        session = _open_session(settlement, employer, worker)
        settlement.credit_work_interval("cmd-c1", session.work_session_id, 480, 600, 0)
        with pytest.raises(ShiftError) as excinfo:
            settlement.credit_work_interval("cmd-c2", session.work_session_id, 540, 660, 1)
        assert excinfo.value.code == "interval_overlap"


class TestCreditPayrollIdempotency:
    """TEST-ECON-010"""

    def test_repeated_credit_counts_once(self):
        settlement, _ledger, employer, worker = _settlement()
        session = _open_session(settlement, employer, worker)
        first = settlement.credit_work_interval("cmd-c1", session.work_session_id, 480, 600, 0)
        replay = settlement.credit_work_interval("cmd-c1-replay", session.work_session_id, 480, 600, 1)
        assert (first, replay) == (120, 0)
        assert session.credited_minutes == 120

    def test_payroll_exactly_once(self):
        settlement, ledger, employer, worker = _settlement()
        session = _open_session(settlement, employer, worker)
        settlement.credit_work_interval("cmd-c1", session.work_session_id, 480, 600, 0)
        settlement.complete_session("cmd-complete", session.work_session_id)
        # floor(120 × 180 / 240) = 90
        result = settlement.settle_payroll("payroll-x", session.work_session_id, 720)
        assert result == ("paid", session.work_session_id, 90)
        replay = settlement.settle_payroll("payroll-x", session.work_session_id, 720)
        assert replay == result
        payroll_events = [e for e in ledger.events() if e.command_id == "payroll-x:legs"]
        assert len(payroll_events) == 1
        assert ledger.get(worker.account_id).balance_copper_feather == 90
        assert ledger.get(employer.account_id).balance_copper_feather == 910

    def test_settle_requires_terminal_state(self):
        settlement, _ledger, employer, worker = _settlement()
        session = _open_session(settlement, employer, worker)
        with pytest.raises(ShiftError) as excinfo:
            settlement.settle_payroll("payroll-early", session.work_session_id, 600)
        assert excinfo.value.code == "work_session_terminal"


class TestSpeedCreditEquivalence:
    """TEST-ECON-011"""

    @pytest.mark.parametrize("chunk", [1, 10, 30, 60, 240])
    def test_chunked_credit_equals_single_state(self, chunk):
        settlement, _ledger, employer, worker = _settlement()
        session = _open_session(settlement, employer, worker)
        minute = 480
        command_index = 0
        while minute < 720:
            settlement.credit_work_interval(
                f"cmd-credit-{command_index}",
                session.work_session_id,
                minute,
                min(minute + chunk, 720),
                session.last_revision,
            )
            minute += chunk
            command_index += 1
        assert session.credited_minutes == 240
        assert session.accrued_copper_feather == 180
        assert session.credited_until_game_time == 720

    def test_frozen_game_time_credits_zero(self):
        settlement, _ledger, employer, worker = _settlement()
        session = _open_session(settlement, employer, worker)
        settlement.credit_work_interval("cmd-c1", session.work_session_id, 480, 600, 0)
        before = (session.credited_minutes, session.accrued_copper_feather)
        paused = settlement.credit_work_interval(
            "cmd-c2", session.work_session_id, 600, 660, 1, game_time_frozen=True
        )
        assert paused == 0
        assert (session.credited_minutes, session.accrued_copper_feather) == before


class TestWageClaimRecovery:
    """TEST-ECON-012"""

    def test_insolvent_employer_creates_bounded_claim(self):
        settlement, ledger, employer, worker = _settlement(employer_balance=0)
        session = _open_session(settlement, employer, worker)
        settlement.credit_work_interval("cmd-c1", session.work_session_id, 480, 720, 0)
        settlement.complete_session("cmd-complete", session.work_session_id)
        result = settlement.settle_payroll("payroll-x", session.work_session_id, 720)
        assert result[0] == "wage_claim"
        assert result[2] == 180
        claims = settlement.claims()
        assert len(claims) == 1
        assert claims[0].amount_copper_feather == 180
        assert claims[0].state == "open"
        # 不 mint、不负余额、无 payroll legs
        assert ledger.get(employer.account_id).balance_copper_feather == 0
        assert [e for e in ledger.events() if e.command_id.startswith("payroll-x")] == []
        # 计提保留且状态终态
        assert session.accrued_copper_feather == 180
        assert session.state is SessionState.SETTLED

    def test_crash_recovery_replays_same_result(self):
        settlement, _ledger, employer, worker = _settlement(employer_balance=0)
        session = _open_session(settlement, employer, worker)
        settlement.credit_work_interval("cmd-c1", session.work_session_id, 480, 720, 0)
        settlement.complete_session("cmd-complete", session.work_session_id)
        first = settlement.settle_payroll("payroll-x", session.work_session_id, 720)
        recovered = settlement.settle_payroll("payroll-x", session.work_session_id, 720)
        assert recovered == first
        assert len(settlement.claims()) == 1

    def test_missed_session_settles_zero(self):
        settlement, ledger, employer, worker = _settlement()
        session = _open_session(settlement, employer, worker, arrived=False)
        assert session.state is SessionState.SCHEDULED
        settlement.mark_missed("cmd-missed", session.work_session_id)
        result = settlement.settle_payroll("payroll-missed", session.work_session_id, 720)
        assert result == ("settled_zero", session.work_session_id, 0)
        assert ledger.get(worker.account_id).balance_copper_feather == 0
        with pytest.raises(ShiftError):
            settlement.settle_payroll("payroll-new-command", session.work_session_id, 720)
