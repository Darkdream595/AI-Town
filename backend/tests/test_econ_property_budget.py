"""
TEST-ECON-041..044：财产与公共预算（DOC-ECON-011）

- TEST-ECON-041：每个 Property Subject 最多一份 active Deed
- TEST-ECON-042：Deed 转移必须同意/裁定；镇长不能越权没收
- TEST-ECON-043：并发 encumber 只有一个成功；budget binding 三处金额一致
- TEST-ECON-044：阶段失败原子释放、到期释放与恢复审计
"""

import pytest

from src.economy import (
    AccountKind,
    AppropriationState,
    BudgetLedger,
    CurrencyLedger,
    CurrencyLeg,
    DeedRegistry,
    EncumbranceState,
    InventoryKind,
    InventoryManager,
    ItemRegistry,
    PropertyError,
    PropertySubject,
    PropertySubjectKind,
    ReservationLedger,
    TransactionEngine,
)

AUTHORITIES = frozenset({"world_bootstrap"})


def _subject(subject_id="building.fixture.one", version=1):
    return PropertySubject(PropertySubjectKind.BUILDING, subject_id, version)


class TestDeedSubjectUniqueness:
    """TEST-ECON-041"""

    def test_second_active_deed_rejected(self):
        registry = DeedRegistry()
        deed = registry.issue_deed(
            "cmd-issue-1", _subject(), ("use", "transfer"), "resident.owner", "event.issue.1"
        )
        assert registry.active_deed_count("building.fixture.one") == 1
        with pytest.raises(PropertyError) as excinfo:
            registry.issue_deed(
                "cmd-issue-2", _subject(), ("use",), "resident.squatter", "event.issue.2"
            )
        assert excinfo.value.code == "deed_conflict"
        assert registry.active_deed_count("building.fixture.one") == 1
        # 命令重放返回原 Deed，不产生第二份
        replay = registry.issue_deed(
            "cmd-issue-1", _subject(), ("use", "transfer"), "resident.owner", "event.issue.1"
        )
        assert replay.deed_item_id == deed.deed_item_id
        assert registry.active_deed_count("building.fixture.one") == 1


class TestDeedTransferAuthority:
    """TEST-ECON-042"""

    def test_transfer_with_consent_commits(self):
        registry = DeedRegistry()
        deed = registry.issue_deed(
            "cmd-issue-1", _subject(), ("use", "transfer"), "resident.owner", "event.issue.1"
        )
        transferred = registry.transfer_deed(
            "cmd-transfer-1", deed.deed_item_id, "resident.buyer",
            current_subject_version=1, consent_evidence_id="consent.signed.1",
        )
        assert transferred.owner_entity_id == "resident.buyer"

    def test_transfer_with_legal_order_commits(self):
        registry = DeedRegistry()
        deed = registry.issue_deed(
            "cmd-issue-1", _subject(), ("use",), "resident.owner", "event.issue.1"
        )
        transferred = registry.transfer_deed(
            "cmd-transfer-1", deed.deed_item_id, "town.public",
            current_subject_version=1, legal_order_id="court.order.1",
        )
        assert transferred.owner_entity_id == "town.public"

    def test_mayor_confiscate_without_evidence_rejected(self):
        registry = DeedRegistry()
        deed = registry.issue_deed(
            "cmd-issue-1", _subject(), ("use",), "resident.owner", "event.issue.1"
        )
        with pytest.raises(PropertyError) as excinfo:
            registry.transfer_deed(
                "cmd-confiscate", deed.deed_item_id, "resident.mayor",
                current_subject_version=1,
            )
        assert excinfo.value.code == "transfer_consent_missing"
        assert deed.owner_entity_id == "resident.owner"

    def test_stale_subject_version_rejected(self):
        registry = DeedRegistry()
        deed = registry.issue_deed(
            "cmd-issue-1", _subject(version=2), ("use",), "resident.owner", "event.issue.1"
        )
        with pytest.raises(PropertyError) as excinfo:
            registry.transfer_deed(
                "cmd-transfer-1", deed.deed_item_id, "resident.buyer",
                current_subject_version=1, consent_evidence_id="consent.signed.1",
            )
        assert excinfo.value.code == "property_version_stale"


def _budget_with_fixture_state(authorized=5000):
    """fixture：spent 1200 + active 1800，返回 (ledger, appropriation, encumbrance_1800)"""
    ledger = BudgetLedger()
    appropriation = ledger.create_appropriation(
        "cmd-approp", "account.public", "purpose.road", authorized,
        starts_at_game_time=0, expires_at_game_time=10000,
        approval_evidence_id="evidence.council.1",
    )
    ledger.activate_appropriation("cmd-activate", appropriation.appropriation_id)
    enc_spent = ledger.encumber(
        "cmd-enc-spent", appropriation.appropriation_id, 1200,
        expected_version=1, created_game_time=0, expires_at_game_time=9000,
        purpose_id="purpose.road", public_account_id="account.public",
    )
    ledger.consume_encumbrance(
        "cmd-consume-spent", enc_spent.encumbrance_id,
        expected_version=1, appropriation_expected_version=2,
    )
    enc_active = ledger.encumber(
        "cmd-enc-active", appropriation.appropriation_id, 1800,
        expected_version=3, created_game_time=0, expires_at_game_time=9000,
        purpose_id="purpose.road", public_account_id="account.public",
    )
    assert appropriation.spent_copper_feather == 1200
    assert appropriation.active_encumbrance_copper_feather == 1800
    return ledger, appropriation, enc_active


class TestAppropriationEncumbranceConcurrency:
    """TEST-ECON-043"""

    def test_concurrent_encumber_only_one_commits(self):
        ledger, appropriation, _enc = _budget_with_fixture_state()
        # 剩余额度 = 5000 - 1200 - 1800 = 1000
        winner = ledger.encumber(
            "cmd-enc-winner", appropriation.appropriation_id, 1000,
            expected_version=4, created_game_time=0, expires_at_game_time=9000,
            purpose_id="purpose.road", public_account_id="account.public",
        )
        assert winner.state is EncumbranceState.ACTIVE
        # 并发败者：基于同一旧 version 提交 → 冲突
        with pytest.raises(PropertyError) as excinfo:
            ledger.encumber(
                "cmd-enc-loser", appropriation.appropriation_id, 1000,
                expected_version=4, created_game_time=0, expires_at_game_time=9000,
                purpose_id="purpose.road", public_account_id="account.public",
            )
        assert excinfo.value.code == "encumbrance_mismatch"
        # 超额拒绝：spent 1200 + active 2800 + 1001 > authorized 5000
        with pytest.raises(PropertyError) as excinfo:
            ledger.encumber(
                "cmd-enc-over", appropriation.appropriation_id, 1001,
                expected_version=appropriation.version, created_game_time=0,
                expires_at_game_time=9000, purpose_id="purpose.road",
                public_account_id="account.public",
            )
        assert excinfo.value.code == "appropriation_exceeded"
        ledger.assert_invariant(appropriation.appropriation_id)
        assert (
            appropriation.spent_copper_feather + appropriation.active_encumbrance_copper_feather
            <= appropriation.authorized_copper_feather
        )

    def test_budget_binding_three_amounts_agree(self):
        budget, appropriation, _enc = _budget_with_fixture_state()
        winner = budget.encumber(
            "cmd-enc-winner", appropriation.appropriation_id, 1000,
            expected_version=4, created_game_time=0, expires_at_game_time=9000,
            purpose_id="purpose.road", public_account_id="account.public",
        )
        # 完整交易：公共账户 debit 1000 且带 8 字段 binding
        currency = CurrencyLedger()
        public = currency.open_account("cmd-open-p", "town.public", AccountKind.PUBLIC_BUDGET, 0)
        assert public.account_id != "account.public"  # binding 以真实账户为准
        contractor = currency.open_account("cmd-open-c", "resident.contractor", AccountKind.RESIDENT, 0)
        currency.mint("cmd-mint-p", public.account_id, 5000, "world_bootstrap", AUTHORITIES)
        engine = TransactionEngine(
            "world.fixture", currency, ReservationLedger(),
            ItemRegistry(), InventoryManager(), budget_ledger=budget,
        )
        # binding 的账户/purpose 必须与 appropriation 一致：重建对齐的预算
        budget2, appropriation2, _enc2 = _budget_with_fixture_state()
        appropriation2.public_account_id = public.account_id
        winner2 = budget2.encumber(
            "cmd-enc-winner2", appropriation2.appropriation_id, 1000,
            expected_version=4, created_game_time=0, expires_at_game_time=9000,
            purpose_id="purpose.road", public_account_id=public.account_id,
        )
        engine2 = TransactionEngine(
            "world.fixture", currency, ReservationLedger(),
            ItemRegistry(), InventoryManager(), budget_ledger=budget2,
        )
        binding = {
            "public_account_id": public.account_id,
            "currency_leg_index": 0,
            "appropriation_id": appropriation2.appropriation_id,
            "appropriation_expected_version": appropriation2.version,
            "encumbrance_id": winner2.encumbrance_id,
            "encumbrance_expected_version": winner2.version,
            "amount_copper_feather": 1000,
            "purpose_id": "purpose.road",
        }
        result = engine2.submit(
            "cmd-public-works", engine2.revision, "public_works",
            [CurrencyLeg(public.account_id, -1000), CurrencyLeg(contractor.account_id, 1000)],
            [], budget_bindings=(binding,),
        )
        assert result.state.value == "committed"
        # 三处金额一致：leg / encumbrance consume / appropriation 计数
        assert currency.get(public.account_id).balance_copper_feather == 4000
        assert currency.get(contractor.account_id).balance_copper_feather == 1000
        assert appropriation2.spent_copper_feather == 2200
        assert appropriation2.active_encumbrance_copper_feather == 1800
        budget2.assert_invariant(appropriation2.appropriation_id)


class TestBudgetEventFailureRecovery:
    """TEST-ECON-044"""

    def test_stage_failure_releases_to_initial_active(self):
        ledger, appropriation, _enc = _budget_with_fixture_state(authorized=6000)
        # 工程阶段 encumber 1800
        work = ledger.encumber(
            "cmd-enc-work", appropriation.appropriation_id, 1800,
            expected_version=appropriation.version, created_game_time=0,
            expires_at_game_time=9000, purpose_id="purpose.road",
            public_account_id="account.public",
        )
        assert appropriation.active_encumbrance_copper_feather == 3600
        # EVENT 阶段失败：原子释放，active 回到初始 1800，无公共扣款
        ledger.release_encumbrance("cmd-release-work", work.encumbrance_id)
        assert appropriation.active_encumbrance_copper_feather == 1800
        assert appropriation.spent_copper_feather == 1200
        assert ledger.orphan_encumbrance_count(appropriation.appropriation_id) == 0
        # 释放命令重放不再重复扣减
        replay = ledger.release_encumbrance("cmd-release-work", work.encumbrance_id)
        assert replay.state is EncumbranceState.RELEASED
        assert appropriation.active_encumbrance_copper_feather == 1800

    def test_no_currency_side_effect(self):
        currency = CurrencyLedger()
        public = currency.open_account("cmd-open-p", "town.public", AccountKind.PUBLIC_BUDGET, 0)
        currency.mint("cmd-mint-p", public.account_id, 6000, "world_bootstrap", AUTHORITIES)
        before = currency.snapshot()
        ledger, appropriation, _enc = _budget_with_fixture_state(authorized=6000)
        work = ledger.encumber(
            "cmd-enc-work", appropriation.appropriation_id, 1800,
            expected_version=appropriation.version, created_game_time=0,
            expires_at_game_time=9000, purpose_id="purpose.road",
            public_account_id="account.public",
        )
        ledger.release_encumbrance("cmd-release-work", work.encumbrance_id)
        # 预算操作本身不动货币账本；只有带 binding 的 Transaction 才扣款
        assert currency.snapshot() == before

    def test_expiry_releases_active_and_marks_appropriation(self):
        ledger, appropriation, _enc = _budget_with_fixture_state(authorized=6000)
        short = ledger.encumber(
            "cmd-enc-short", appropriation.appropriation_id, 500,
            expected_version=appropriation.version, created_game_time=0,
            expires_at_game_time=100, purpose_id="purpose.road",
            public_account_id="account.public",
        )
        expired_enc, expired_app = ledger.expire_overdue(current_game_time=200)
        assert short.encumbrance_id in expired_enc
        assert appropriation.active_encumbrance_copper_feather == 1800
        assert ledger.orphan_encumbrance_count(appropriation.appropriation_id) == 0
        assert expired_app == []  # appropriation 10000 才到期
        expired_enc2, expired_app2 = ledger.expire_overdue(current_game_time=10001)
        assert appropriation.appropriation_id in expired_app2
        assert appropriation.state is AppropriationState.EXPIRED
        # 已到期 appropriation 不能再 encumber
        with pytest.raises(PropertyError) as excinfo:
            ledger.encumber(
                "cmd-enc-late", appropriation.appropriation_id, 1,
                expected_version=appropriation.version, created_game_time=10002,
                expires_at_game_time=11000, purpose_id="purpose.road",
                public_account_id="account.public",
            )
        assert excinfo.value.code == "appropriation_missing"

    def test_budget_ledger_has_no_building_writes(self):
        # RULE-ECON-044：Building 阶段归 EVENT，ECON 只结算经济资源
        ledger = BudgetLedger()
        assert not hasattr(ledger, "write_building")
        assert not hasattr(ledger, "buildings")
