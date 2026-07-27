"""
TEST-ECON-001..004：货币系统（DOC-ECON-001）

- TEST-ECON-001：CopperFeather int64 与银冠/铜羽 round-trip property
- TEST-ECON-002：普通、税费与工资 Ledger 守恒
- TEST-ECON-003：并发透支、overflow 与 unauthorized mint 拒绝
- TEST-ECON-004：Snapshot/Event 恢复后余额重建一致
"""

import pytest

from src.economy import (
    AccountKind,
    AccountState,
    CurrencyError,
    CurrencyLedger,
    format_currency,
    parse_display_amount,
)
from src.economy.constants import INT64_MAX

AUTHORITIES = frozenset({"world_bootstrap", "admin_recovery"})


def _ledger_with_accounts():
    ledger = CurrencyLedger()
    buyer = ledger.open_account("cmd-open-b", "resident.buyer", AccountKind.RESIDENT, 0)
    seller = ledger.open_account("cmd-open-s", "resident.seller", AccountKind.RESIDENT, 0)
    public = ledger.open_account("cmd-open-p", "town.public", AccountKind.PUBLIC_BUDGET, 0)
    ledger.mint("cmd-mint-b", buyer.account_id, 1234, "world_bootstrap", AUTHORITIES)
    return ledger, buyer, seller, public


class TestDisplayRoundTrip:
    """TEST-ECON-001"""

    def test_golden_display(self):
        assert format_currency(1234) == "12 银冠 34 铜羽"
        assert format_currency(34) == "34 铜羽"
        assert format_currency(1200) == "12 银冠"
        assert format_currency(0) == "0 铜羽"

    @pytest.mark.parametrize("amount", [0, 1, 34, 99, 100, 101, 1234, 9999, 10000, INT64_MAX])
    def test_round_trip_property(self, amount):
        assert parse_display_amount(format_currency(amount)) == amount

    def test_negative_and_float_rejected(self):
        with pytest.raises(CurrencyError) as excinfo:
            format_currency(-1)
        assert excinfo.value.code == "invalid_currency_amount"
        with pytest.raises(CurrencyError):
            parse_display_amount("12.5 银冠")
        with pytest.raises(CurrencyError):
            parse_display_amount("一百铜羽")


class TestLedgerConservation:
    """TEST-ECON-002"""

    def test_transfer_with_tax_sums_to_zero(self):
        ledger, buyer, seller, public = _ledger_with_accounts()
        ledger.post_legs(
            "cmd-sale",
            [(buyer.account_id, -110), (seller.account_id, 100), (public.account_id, 10)],
            expected_revision=ledger.revision,
        )
        assert buyer.balance_copper_feather == 1124
        assert seller.balance_copper_feather == 100
        assert public.balance_copper_feather == 10
        event = ledger.events()[-1]
        assert sum(delta for _aid, delta in event.legs) == 0

    def test_wage_and_compensation_also_conserved(self):
        ledger, buyer, seller, _public = _ledger_with_accounts()
        ledger.post_legs(
            "cmd-wage", [(buyer.account_id, -180), (seller.account_id, 180)],
            expected_revision=ledger.revision,
        )
        ledger.post_legs(
            "cmd-comp", [(buyer.account_id, -50), (seller.account_id, 50)],
            expected_revision=ledger.revision,
        )
        assert all(
            sum(delta for _aid, delta in event.legs) == 0
            for event in ledger.events()
            if event.kind == "transfer"
        )

    def test_unbalanced_and_zero_leg_rejected(self):
        ledger, buyer, seller, _public = _ledger_with_accounts()
        with pytest.raises(CurrencyError) as excinfo:
            ledger.post_legs("cmd-bad", [(buyer.account_id, -100), (seller.account_id, 99)], ledger.revision)
        assert excinfo.value.code == "unbalanced_ledger"
        with pytest.raises(CurrencyError) as excinfo:
            ledger.post_legs("cmd-zero", [(buyer.account_id, 0), (seller.account_id, 0)], ledger.revision)
        assert excinfo.value.code == "invalid_currency_amount"

    def test_stale_revision_rejected(self):
        ledger, buyer, seller, _public = _ledger_with_accounts()
        with pytest.raises(CurrencyError) as excinfo:
            ledger.post_legs("cmd-stale", [(buyer.account_id, -1), (seller.account_id, 1)], expected_revision=999)
        assert excinfo.value.code == "stale_revision"


class TestOverdraftOverflowMint:
    """TEST-ECON-003"""

    def test_concurrent_overdraft_single_winner(self):
        ledger, buyer, seller, _public = _ledger_with_accounts()  # buyer 1234
        ledger.post_legs("cmd-d1", [(buyer.account_id, -900), (seller.account_id, 900)], ledger.revision)
        with pytest.raises(CurrencyError) as excinfo:
            ledger.post_legs("cmd-d2", [(buyer.account_id, -900), (seller.account_id, 900)], ledger.revision)
        assert excinfo.value.code == "insufficient_funds"
        # 失败者无部分扣款
        assert buyer.balance_copper_feather == 334
        assert seller.balance_copper_feather == 900

    def test_float_and_scientific_amount_rejected(self):
        ledger, buyer, seller, _public = _ledger_with_accounts()
        for bad in (1.5, 1e3, True):
            with pytest.raises(CurrencyError) as excinfo:
                ledger.post_legs("cmd-f", [(buyer.account_id, -bad), (seller.account_id, bad)], ledger.revision)
            assert excinfo.value.code in ("invalid_currency_amount", "currency_overflow")

    def test_overflow_rejected(self):
        ledger = CurrencyLedger()
        rich = ledger.open_account("cmd-o1", "resident.rich", AccountKind.RESIDENT, 0)
        poor = ledger.open_account("cmd-o2", "resident.poor", AccountKind.RESIDENT, 0)
        ledger.mint("cmd-m1", rich.account_id, INT64_MAX, "world_bootstrap", AUTHORITIES)
        with pytest.raises(CurrencyError) as excinfo:
            ledger.mint("cmd-m2", rich.account_id, 1, "world_bootstrap", AUTHORITIES)
        assert excinfo.value.code == "currency_overflow"

    def test_unauthorized_mint_rejected(self):
        ledger, buyer, _seller, _public = _ledger_with_accounts()
        for authority in ("mayor_decree", "ai_proposal", "resident_wish"):
            with pytest.raises(CurrencyError) as excinfo:
                ledger.mint("cmd-mint-bad", buyer.account_id, 1, authority, AUTHORITIES)
            assert excinfo.value.code == "mint_permission_denied"

    def test_close_account_requires_zero_balance(self):
        ledger, buyer, seller, _public = _ledger_with_accounts()
        with pytest.raises(CurrencyError):
            ledger.close_account("cmd-close", buyer.account_id)
        ledger.post_legs("cmd-drain", [(buyer.account_id, -1234), (seller.account_id, 1234)], ledger.revision)
        ledger.close_account("cmd-close-2", buyer.account_id)
        assert buyer.state is AccountState.CLOSED
        with pytest.raises(CurrencyError) as excinfo:
            ledger.post_legs("cmd-after-close", [(buyer.account_id, -1), (seller.account_id, 1)], ledger.revision)
        assert excinfo.value.code == "account_closed"


class TestSnapshotReplay:
    """TEST-ECON-004"""

    def test_replay_rebuilds_committed_balances(self):
        ledger, buyer, seller, public = _ledger_with_accounts()
        ledger.post_legs("cmd-t1", [(buyer.account_id, -110), (seller.account_id, 100), (public.account_id, 10)], ledger.revision)
        ledger.mint("cmd-mint-2", seller.account_id, 50, "admin_recovery", AUTHORITIES)
        ledger.burn("cmd-burn-1", public.account_id, 5, "admin_recovery", AUTHORITIES)

        committed = ledger.snapshot()
        accounts = [buyer, seller, public]
        replayed = CurrencyLedger.replay(accounts, ledger.events())
        assert replayed == committed
