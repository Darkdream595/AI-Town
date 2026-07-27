"""
货币系统（DOC-ECON-001）

- RULE-ECON-001：整数铜羽、非负余额、int64 上下界
- RULE-ECON-002：普通 Ledger Entry 事务内代数和为 0；税费转入明确收款账户
- RULE-ECON-003：Mint/Burn 必须引用注册 authority reason，镇长/AI/居民不能自行 mint
- RULE-ECON-004：银冠/铜羽显示 round-trip 恢复原整数
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..foundation import generate_ulid
from .constants import (
    COPPER_PER_SILVER,
    INT64_MAX,
    INT64_MIN,
    AccountKind,
    AccountState,
)


class CurrencyError(Exception):
    """货币操作失败；code 为稳定 reason code"""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass
class MonetaryAccount:
    """DES-ECON-001 的运行时形态"""

    account_id: str
    owner_entity_id: str
    account_kind: AccountKind
    balance_copper_feather: int
    state: AccountState
    opened_game_time: int
    last_revision: int
    schema_version: int = 1


@dataclass(frozen=True)
class LedgerEvent:
    """守恒审计与重放的最小事件载荷"""

    event_id: str
    command_id: str
    legs: Tuple[Tuple[str, int], ...]
    kind: str  # transfer / mint / burn
    revision: int
    authority_reason_id: Optional[str] = None


@dataclass(frozen=True)
class CurrencyPostResult:
    transaction_id: str
    committed_revision: int
    event_id: str


def _validate_amount(value: object) -> int:
    """协议边界：拒绝 bool、浮点、科学计数与超界整数（DOC-ECON-001 §7）"""
    if isinstance(value, bool) or not isinstance(value, int):
        raise CurrencyError(
            "invalid_currency_amount", f"amount must be int, got {type(value).__name__}"
        )
    if value < INT64_MIN or value > INT64_MAX:
        raise CurrencyError("currency_overflow", f"{value} outside int64")
    return value


def format_currency(amount_copper_feather: int) -> str:
    """RULE-ECON-004：1234 → 「12 银冠 34 铜羽」"""
    _validate_amount(amount_copper_feather)
    if amount_copper_feather < 0:
        raise CurrencyError("invalid_currency_amount", "display amount must be >= 0")
    silver, copper = divmod(amount_copper_feather, COPPER_PER_SILVER)
    if silver and copper:
        return f"{silver} 银冠 {copper} 铜羽"
    if silver:
        return f"{silver} 银冠"
    return f"{copper} 铜羽"


_DISPLAY_PATTERN = re.compile(r"^(?:(\d+) 银冠)?(?: ?(\d+) 铜羽)?$")


def parse_display_amount(text: str) -> int:
    """RULE-ECON-004：parse(format(n)) == n，禁止四舍五入"""
    match = _DISPLAY_PATTERN.match(text.strip())
    if match is None or (match.group(1) is None and match.group(2) is None):
        raise CurrencyError("invalid_currency_amount", f"unparseable display: {text!r}")
    silver = int(match.group(1) or 0)
    copper = int(match.group(2) or 0)
    return silver * COPPER_PER_SILVER + copper


class CurrencyLedger:
    """
    Monetary Account 账本：守恒、幂等与重放。

    守恒语义：transfer 类 legs 代数和必须为 0；mint/burn 是显式登记的
    source/sink，走独立事件与权限证据。
    """

    def __init__(self) -> None:
        self._accounts: Dict[str, MonetaryAccount] = {}
        self._events: List[LedgerEvent] = []
        self._revision = 0
        self._command_results: Dict[str, CurrencyPostResult] = {}

    @property
    def revision(self) -> int:
        return self._revision

    def events(self) -> List[LedgerEvent]:
        return list(self._events)

    def get(self, account_id: str) -> MonetaryAccount:
        account = self._accounts.get(account_id)
        if account is None:
            raise CurrencyError("account_unknown", f"unknown account {account_id}")
        return account

    def open_account(
        self,
        command_id: str,
        owner_entity_id: str,
        account_kind: AccountKind,
        game_time: int,
        initial_balance: int = 0,
    ) -> MonetaryAccount:
        _validate_amount(initial_balance)
        account = MonetaryAccount(
            account_id=generate_ulid(),
            owner_entity_id=owner_entity_id,
            account_kind=account_kind,
            balance_copper_feather=initial_balance,
            state=AccountState.OPEN,
            opened_game_time=game_time,
            last_revision=self._revision,
        )
        self._accounts[account.account_id] = account
        return account

    def close_account(self, command_id: str, account_id: str) -> None:
        """§7：余额为 0 才能关闭（Reservation/未决检查由调用方先行）"""
        account = self.get(account_id)
        if account.balance_copper_feather != 0:
            raise CurrencyError(
                "invalid_currency_amount", "account balance must be 0 to close"
            )
        account.state = AccountState.CLOSED

    # -- 普通转账（守恒） --

    def post_legs(
        self,
        command_id: str,
        legs: List[Tuple[str, int]],
        expected_revision: int,
    ) -> CurrencyPostResult:
        """
        §6：写集校验后同一 Unit of Work 提交；任何错误不写余额、
        不产生事件且 Revision 不增长。
        """
        if command_id in self._command_results:
            return self._command_results[command_id]
        if expected_revision != self._revision:
            raise CurrencyError(
                "stale_revision", f"expected {expected_revision}, at {self._revision}"
            )
        if not legs:
            raise CurrencyError("unbalanced_ledger", "empty legs")
        parsed = [(account_id, _validate_amount(delta)) for account_id, delta in legs]
        for _account_id, delta in parsed:
            if delta == 0:
                # §7：金额为 0 的业务 leg 被拒绝，避免伪造无效审计
                raise CurrencyError("invalid_currency_amount", "zero-amount leg")
        if sum(delta for _aid, delta in parsed) != 0:
            # RULE-ECON-002：不能通过少记账销毁货币
            raise CurrencyError("unbalanced_ledger", "legs must sum to 0")

        new_balances: Dict[str, int] = {}
        for account_id, delta in parsed:
            account = self.get(account_id)
            if account.state is not AccountState.OPEN:
                raise CurrencyError("account_closed", account_id)
            new_balance = account.balance_copper_feather + delta
            if new_balance < 0:
                raise CurrencyError("insufficient_funds", account_id)
            if new_balance > INT64_MAX:
                raise CurrencyError("currency_overflow", account_id)
            new_balances[account_id] = new_balance

        event = LedgerEvent(
            event_id=generate_ulid(),
            command_id=command_id,
            legs=tuple(parsed),
            kind="transfer",
            revision=self._revision + 1,
        )
        for account_id, new_balance in new_balances.items():
            account = self._accounts[account_id]
            account.balance_copper_feather = new_balance
            account.last_revision = event.revision
        self._revision += 1
        self._events.append(event)
        result = CurrencyPostResult(generate_ulid(), self._revision, event.event_id)
        self._command_results[command_id] = result
        return result

    # -- Mint/Burn（显式 source/sink） --

    def mint(
        self,
        command_id: str,
        account_id: str,
        amount: int,
        authority_reason_id: str,
        registered_authority_ids: frozenset,
    ) -> CurrencyPostResult:
        """RULE-ECON-003：只有注册 authority 可 mint；普通主体一律拒绝"""
        if command_id in self._command_results:
            return self._command_results[command_id]
        if authority_reason_id not in registered_authority_ids:
            raise CurrencyError(
                "mint_permission_denied", f"{authority_reason_id} not registered"
            )
        amount = _validate_amount(amount)
        if amount <= 0:
            raise CurrencyError("invalid_currency_amount", "mint amount must be > 0")
        account = self.get(account_id)
        if account.state is not AccountState.OPEN:
            raise CurrencyError("account_closed", account_id)
        if account.balance_copper_feather + amount > INT64_MAX:
            raise CurrencyError("currency_overflow", account_id)
        account.balance_copper_feather += amount
        self._revision += 1
        account.last_revision = self._revision
        event = LedgerEvent(
            event_id=generate_ulid(),
            command_id=command_id,
            legs=((account_id, amount),),
            kind="mint",
            revision=self._revision,
            authority_reason_id=authority_reason_id,
        )
        self._events.append(event)
        result = CurrencyPostResult(generate_ulid(), self._revision, event.event_id)
        self._command_results[command_id] = result
        return result

    def burn(
        self,
        command_id: str,
        account_id: str,
        amount: int,
        authority_reason_id: str,
        registered_authority_ids: frozenset,
    ) -> CurrencyPostResult:
        if command_id in self._command_results:
            return self._command_results[command_id]
        if authority_reason_id not in registered_authority_ids:
            raise CurrencyError(
                "mint_permission_denied", f"{authority_reason_id} not registered"
            )
        amount = _validate_amount(amount)
        if amount <= 0:
            raise CurrencyError("invalid_currency_amount", "burn amount must be > 0")
        account = self.get(account_id)
        if account.balance_copper_feather - amount < 0:
            raise CurrencyError("insufficient_funds", account_id)
        account.balance_copper_feather -= amount
        self._revision += 1
        account.last_revision = self._revision
        event = LedgerEvent(
            event_id=generate_ulid(),
            command_id=command_id,
            legs=((account_id, -amount),),
            kind="burn",
            revision=self._revision,
            authority_reason_id=authority_reason_id,
        )
        self._events.append(event)
        result = CurrencyPostResult(generate_ulid(), self._revision, event.event_id)
        self._command_results[command_id] = result
        return result

    # -- 快照与重放（TEST-ECON-004） --

    def snapshot(self) -> Dict[str, int]:
        """守恒审计投影：account_id -> balance"""
        return {
            account_id: account.balance_copper_feather
            for account_id, account in sorted(self._accounts.items())
        }

    @staticmethod
    def replay(
        accounts: List[MonetaryAccount], events: List[LedgerEvent]
    ) -> Dict[str, int]:
        """Snapshot/Event 恢复：从事件重放重建余额，必须与已提交投影一致"""
        balances = {account.account_id: 0 for account in accounts}
        for event in events:
            for account_id, delta in event.legs:
                balances[account_id] = balances.get(account_id, 0) + delta
        return dict(sorted(balances.items()))
