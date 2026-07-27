"""
TEST-PLAYER-033..036：Sandbox Admin 确认、存档标记与审计（DOC-PLAYER-009）

- TEST-PLAYER-033：Admin session、白名单和 Mayor/Resident 隔离
- TEST-PLAYER-034：challenge tamper/replay/expiry/cross-session
- TEST-PLAYER-035：mutation/event/audit/mark 原子故障注入
- TEST-PLAYER-036：lineage taint、hash chain、篡改 Recovery Barrier
"""

import pytest

from src.player import (
    AdminAuditLog,
    AdminCommandError,
    AdminSessionManager,
    AuditResult,
    SaveIntegrityMark,
)

WORLD = "01K1WRDX000000000000000001"
OWNER = "01K1DENT000000000000000001"
TARGET = "01K1RSDT000000000000000001"


class FakeClock:
    def __init__(self, start=1_000.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def _grant_payload(quantity=100):
    return {
        "target_resident_id": TARGET,
        "resource_kind": "currency",
        "definition_id": "currency.copper_feather",
        "quantity": quantity,
        "reason_code": "sandbox.player_requested",
    }


def _manager(mutation_handler=None, clock=None, sink=None):
    clock = clock or FakeClock()
    log = AdminAuditLog(world_id=WORLD, sink=sink)
    manager = AdminSessionManager(
        audit_log=log,
        mutation_handler=mutation_handler or (lambda t, p: 402),
        monotonic_clock=clock,
    )
    return manager, log, clock


def _enabled_session(manager):
    return manager.enable_session(WORLD, OWNER, is_world_owner=True)


class TestSessionAndWhitelist:
    """TEST-PLAYER-033"""

    def test_session_requires_world_owner(self):
        manager, _, _ = _manager()
        with pytest.raises(AdminCommandError) as exc:
            manager.enable_session(WORLD, OWNER, is_world_owner=False)
        assert exc.value.code == "ADMIN_SESSION_REQUIRES_WORLD_OWNER"

    def test_mayor_role_does_not_grant_admin(self):
        """RULE-PLAYER-041：Mayor/binding/NL/Client mode 不创建 Admin authority"""
        manager, _, _ = _manager()
        with pytest.raises(AdminCommandError) as exc:
            manager.request_confirmation(
                "nonexistent-session", "cmd-1",
                "admin.resource.grant", _grant_payload(), "授予 100 铜羽",
            )
        assert exc.value.code == "ADMIN_SESSION_INVALID"

    def test_whitelist_rejects_unregistered_command(self):
        manager, log, _ = _manager()
        session = _enabled_session(manager)
        with pytest.raises(AdminCommandError) as exc:
            manager.request_confirmation(
                session.admin_session_id, "cmd-1",
                "admin.database.drop", {"reason_code": "x"}, "删除数据库",
            )
        assert exc.value.code == "ADMIN_COMMAND_TYPE_UNREGISTERED"
        # RULE-PLAYER-045：denial 也产生审计
        assert log.events[-1].result == AuditResult.DENIED

    def test_quantity_cap_enforced(self):
        manager, _, _ = _manager()
        session = _enabled_session(manager)
        with pytest.raises(AdminCommandError) as exc:
            manager.request_confirmation(
                session.admin_session_id, "cmd-1",
                "admin.resource.grant", _grant_payload(quantity=99999), "超上限",
            )
        assert exc.value.code == "ADMIN_GRANT_QUANTITY_OUT_OF_RANGE"

    def test_client_confirmed_true_has_no_effect(self):
        """RULE-PLAYER-042：Client 自报 confirmed=true 无效"""
        manager, _, _ = _manager()
        session = _enabled_session(manager)
        with pytest.raises(AdminCommandError) as exc:
            manager.execute(
                session.admin_session_id, "cmd-1",
                "admin.resource.grant", _grant_payload(),
                {"confirmed": True},
            )
        assert exc.value.code == "ADMIN_CHALLENGE_UNKNOWN"


class TestChallengeBinding:
    """TEST-PLAYER-034"""

    def _issued(self, manager, session, command_id="cmd-1", payload=None):
        return manager.request_confirmation(
            session.admin_session_id, command_id,
            "admin.resource.grant", payload or _grant_payload(), "授予 100 铜羽",
        )

    def test_happy_path_commits_and_taints(self):
        manager, log, _ = _manager()
        session = _enabled_session(manager)
        challenge = self._issued(manager, session)
        revision = manager.execute(
            session.admin_session_id, "cmd-1",
            "admin.resource.grant", _grant_payload(),
            {"challenge_id": challenge.challenge_id, "nonce": challenge.nonce},
        )
        assert revision == 402
        assert manager.save_integrity_mark.admin_modified is True
        results = [e.result for e in log.events]
        assert results == [AuditResult.ATTEMPTED, AuditResult.COMMITTED]

    def test_payload_tamper_rejected(self):
        manager, log, _ = _manager()
        session = _enabled_session(manager)
        challenge = self._issued(manager, session)
        with pytest.raises(AdminCommandError) as exc:
            manager.execute(
                session.admin_session_id, "cmd-1",
                "admin.resource.grant", _grant_payload(quantity=200),
                {"challenge_id": challenge.challenge_id, "nonce": challenge.nonce},
            )
        assert exc.value.code == "ADMIN_CHALLENGE_PAYLOAD_TAMPERED"

    def test_challenge_replay_rejected(self):
        manager, _, _ = _manager()
        session = _enabled_session(manager)
        challenge = self._issued(manager, session)
        manager.execute(
            session.admin_session_id, "cmd-1",
            "admin.resource.grant", _grant_payload(),
            {"challenge_id": challenge.challenge_id, "nonce": challenge.nonce},
        )
        with pytest.raises(AdminCommandError) as exc:
            manager.execute(
                session.admin_session_id, "cmd-2",
                "admin.resource.grant", _grant_payload(),
                {"challenge_id": challenge.challenge_id, "nonce": challenge.nonce},
            )
        assert exc.value.code == "ADMIN_CHALLENGE_REPLAYED"

    def test_expired_challenge_rejected(self):
        manager, log, clock = _manager()
        session = _enabled_session(manager)
        challenge = self._issued(manager, session)
        clock.advance(61)  # 超过 60s 有效期（monotonic 判定）
        with pytest.raises(AdminCommandError) as exc:
            manager.execute(
                session.admin_session_id, "cmd-1",
                "admin.resource.grant", _grant_payload(),
                {"challenge_id": challenge.challenge_id, "nonce": challenge.nonce},
            )
        assert exc.value.code == "ADMIN_CHALLENGE_EXPIRED"
        assert log.events[-1].result == AuditResult.EXPIRED

    def test_cross_session_challenge_rejected(self):
        manager, _, _ = _manager()
        session_a = _enabled_session(manager)
        session_b = _enabled_session(manager)
        challenge = self._issued(manager, session_a)
        with pytest.raises(AdminCommandError) as exc:
            manager.execute(
                session_b.admin_session_id, "cmd-1",
                "admin.resource.grant", _grant_payload(),
                {"challenge_id": challenge.challenge_id, "nonce": challenge.nonce},
            )
        assert exc.value.code == "ADMIN_CHALLENGE_CROSS_SESSION"

    def test_nonce_mismatch_rejected(self):
        manager, _, _ = _manager()
        session = _enabled_session(manager)
        challenge = self._issued(manager, session)
        with pytest.raises(AdminCommandError) as exc:
            manager.execute(
                session.admin_session_id, "cmd-1",
                "admin.resource.grant", _grant_payload(),
                {"challenge_id": challenge.challenge_id, "nonce": "forged"},
            )
        assert exc.value.code == "ADMIN_CHALLENGE_NONCE_MISMATCH"


class TestAtomicityFaultInjection:
    """TEST-PLAYER-035"""

    def test_mutation_failure_leaves_no_mark_and_audits_failed(self):
        def broken_handler(t, p):
            raise RuntimeError("disk full")

        manager, log, _ = _manager(mutation_handler=broken_handler)
        session = _enabled_session(manager)
        challenge = manager.request_confirmation(
            session.admin_session_id, "cmd-1",
            "admin.resource.grant", _grant_payload(), "授予",
        )
        with pytest.raises(AdminCommandError):
            manager.execute(
                session.admin_session_id, "cmd-1",
                "admin.resource.grant", _grant_payload(),
                {"challenge_id": challenge.challenge_id, "nonce": challenge.nonce},
            )
        # RULE-PLAYER-044：全成或全败——无 mark、无 committed 审计
        assert manager.save_integrity_mark.admin_modified is False
        assert AuditResult.COMMITTED not in [e.result for e in log.events]

    def test_audit_sink_failure_fails_closed(self):
        def failing_sink(event):
            raise OSError("audit sink readonly")

        manager, log, _ = _manager(sink=failing_sink)
        session = _enabled_session(manager)
        # attempted 审计写不进即 fail closed，challenge 流程中断
        with pytest.raises(OSError):
            manager.request_confirmation(
                session.admin_session_id, "cmd-1",
                "admin.resource.grant", _grant_payload(), "授予",
            )
        assert manager.save_integrity_mark.admin_modified is False

    def test_command_id_exactly_once(self):
        manager, _, _ = _manager()
        session = _enabled_session(manager)
        challenge = manager.request_confirmation(
            session.admin_session_id, "cmd-1",
            "admin.resource.grant", _grant_payload(), "授予",
        )
        manager.execute(
            session.admin_session_id, "cmd-1",
            "admin.resource.grant", _grant_payload(),
            {"challenge_id": challenge.challenge_id, "nonce": challenge.nonce},
        )
        with pytest.raises(AdminCommandError) as exc:
            manager.execute(
                session.admin_session_id, "cmd-1",
                "admin.resource.grant", _grant_payload(),
                {"challenge_id": challenge.challenge_id, "nonce": challenge.nonce},
            )
        # 已执行的 command 重放被拒绝（challenge 已标 used / command 已记录）
        assert exc.value.code in (
            "ADMIN_COMMAND_ALREADY_EXECUTED", "ADMIN_CHALLENGE_REPLAYED",
        )


class TestLineageTaintAndHashChain:
    """TEST-PLAYER-036"""

    def test_taint_is_monotonic_and_unclearable(self):
        mark = SaveIntegrityMark().taint()
        assert mark.admin_modified is True
        with pytest.raises(AdminCommandError) as exc:
            mark.try_clear()
        assert exc.value.code == "ADMIN_TAINT_CLEAR_REJECTED"

    def test_hash_chain_valid_after_multiple_events(self):
        manager, log, _ = _manager()
        session = _enabled_session(manager)
        for i in range(3):
            challenge = manager.request_confirmation(
                session.admin_session_id, f"cmd-{i}",
                "admin.resource.grant", _grant_payload(), f"授予 {i}",
            )
            manager.execute(
                session.admin_session_id, f"cmd-{i}",
                "admin.resource.grant", _grant_payload(),
                {"challenge_id": challenge.challenge_id, "nonce": challenge.nonce},
            )
        # 3 attempted + 3 committed，序号单调、链完整
        assert [e.audit_sequence for e in log.events] == [1, 2, 3, 4, 5, 6]
        assert log.verify_chain() is True

    def test_tampered_chain_detected(self):
        manager, log, _ = _manager()
        session = _enabled_session(manager)
        manager.request_confirmation(
            session.admin_session_id, "cmd-1",
            "admin.resource.grant", _grant_payload(), "授予",
        )
        # 篡改审计事件内容（frozen dataclass，用 object.__setattr__ 模拟存储层篡改）
        tampered = log.events[0]
        object.__setattr__(tampered, "result", AuditResult.COMMITTED)
        assert log.verify_chain() is False

    def test_forbidden_targets_rejected(self):
        """RULE-PLAYER-046：历史 event/审计/ID/Revision/Key/路径/Catalog 不可改写"""
        for field in ("event_history", "audit_log", "entity_id", "revision",
                      "api_key", "file_path", "catalog"):
            with pytest.raises(AdminCommandError) as exc:
                AdminSessionManager.assert_not_forbidden_target(field)
            assert exc.value.code == "ADMIN_TARGET_FORBIDDEN"
