"""TEST-BACKEND-036..038：幂等记录原子性、保留窗口、外部效应拆分与重校验"""
from __future__ import annotations

import pytest

from backend_helpers import (
    command_envelope,
    make_id_factory,
    make_utc_factory,
)
from src.api.schemas import SchemaRegistry
from src.api.wire import register_command_specs, register_event_specs
from src.foundation.errors import ApiError
from src.orchestrator.commands import CommandRegistry
from src.orchestrator.events import EventRegistry
from src.orchestrator.idempotency import (
    RETENTION_MIN_GAME_DAYS,
    RETENTION_MIN_RECORDS,
    IdempotencyStore,
    canonical_payload_hash,
)
from src.orchestrator.uow import UOW_STEPS, WorldStore, WorldWriter

ULID_A = "01K1AB2CD3EF4GH5JK6MNP7QS0"
ULID_B = "01K1AB2CD3EF4GH5JK6MNP7QS1"
ULID_C = "01K1AB2CD3EF4GH5JK6MNP7QS2"


def _writer(domain_apply=None, commit_check=None):
    schemas = SchemaRegistry()
    commands = CommandRegistry()
    events = EventRegistry()
    register_command_specs(schemas, commands)
    register_event_specs(schemas, events)
    store = WorldStore()
    store.open_world("w1")
    idem = IdempotencyStore(make_utc_factory())
    apply = domain_apply or (lambda _w, _t, _p, _ctx: {
        "state": {}, "events": [], "reservations": []})
    return (WorldWriter(store, idem, commands, events,
                        make_id_factory("tx"), make_utc_factory(), apply,
                        commit_check=commit_check),
            store, idem)


# ---------------------------------------------------------------------------
# TEST-BACKEND-036：RULE-BACKEND-055..056 幂等记录原子性与冲突判定
# ---------------------------------------------------------------------------

class TestIdempotencyAtomicity:
    def test_record_content_complete(self):
        writer, _store, idem = _writer()
        envelope = command_envelope(ULID_A, "w1")
        receipt = writer.execute(envelope)
        record = idem.lookup("w1", ULID_A,
                             canonical_payload_hash(envelope["payload"]))
        assert record.receipt == receipt
        assert record.payload_hash == canonical_payload_hash(envelope["payload"])
        assert record.committed_revision == 1
        assert record.recorded_at

    def test_record_written_atomically_with_state(self):
        """UoW 故障 → 状态与幂等记录同时不存在（同事务语义）"""
        writer, store, idem = _writer()
        store.fail_at = "commit"
        receipt = writer.execute(command_envelope(ULID_A, "w1"))
        assert receipt["result"] == "failed"
        assert receipt["error"]["code"] == "BACKEND_STORAGE_FAILURE"
        assert idem.count("w1") == 0
        assert store.current_revision("w1") == 0

    def test_replay_does_not_reexecute_domain(self):
        calls = []

        def apply(_w, _t, _p, _ctx):
            calls.append(1)
            return {"state": {}, "events": [], "reservations": []}

        writer, _store, _idem = _writer(domain_apply=apply)
        envelope = command_envelope(ULID_A, "w1")
        writer.execute(envelope)
        writer.execute(dict(envelope))
        writer.execute(dict(envelope))
        assert len(calls) == 1  # Domain 只执行一次

    def test_conflict_never_disguises_old_success(self):
        writer, _store, _idem = _writer()
        writer.execute(command_envelope(ULID_A, "w1"))
        with pytest.raises(ApiError) as exc_info:
            writer.execute(command_envelope(
                ULID_A, "w1", payload={"schema_version": 1, "paused": False}))
        assert exc_info.value.code == "BACKEND_IDEMPOTENCY_CONFLICT"
        assert exc_info.value.details["reason_code"] == "payload_hash_mismatch"

    def test_unique_per_world(self):
        """(world_id, command_id) 唯一：不同世界同 command_id 各自独立"""
        writer, store, idem = _writer()
        store.open_world("w2")
        writer.execute(command_envelope(ULID_A, "w1"))
        writer.execute(command_envelope(ULID_A, "w2"))
        assert idem.count() == 2


# ---------------------------------------------------------------------------
# TEST-BACKEND-037：RULE-BACKEND-057..058 保留窗口、UoW 步骤级故障注入
# ---------------------------------------------------------------------------

class TestRetentionAndUowProtocol:
    def test_retention_window_constants(self):
        assert RETENTION_MIN_GAME_DAYS == 30
        assert RETENTION_MIN_RECORDS == 100_000

    def test_prune_respects_min_records(self):
        idem = IdempotencyStore(make_utc_factory())
        writer, _store, _i = _writer()
        # 写入 5 条记录（共享 store/idempotency）
        writer2, _s2, idem2 = _writer()
        idem_local = idem2
        for index, ulid in enumerate((ULID_A, ULID_B, ULID_C)):
            writer2.execute(command_envelope(ulid, "w1"))
        assert idem_local.count("w1") == 3
        # keep_min_records=5 > 3：一条都不裁
        pruned = idem_local.prune_at_checkpoint("w1", keep_min_records=5)
        assert pruned == 0
        assert idem_local.count("w1") == 3
        # keep_min_records=1：裁到 1 条，且保留最新（sequence 最大）
        pruned = idem_local.prune_at_checkpoint("w1", keep_min_records=1)
        assert pruned == 2
        assert idem_local.count("w1") == 1
        assert idem_local.lookup("w1", ULID_C, canonical_payload_hash(
            command_envelope(ULID_C, "w1")["payload"])) is not None

    def test_uow_step_order_matches_rule(self):
        """RULE-BACKEND-058：begin→写状态→append 事件→写幂等→消费 Reservation
        →Commit Check→COMMIT"""
        assert UOW_STEPS == ("begin", "write_state", "append_events",
                             "write_idempotency", "consume_reservations",
                             "commit_check", "commit")

    def test_commit_check_failure_rolls_back(self):
        def check(_state):
            return ["invariant_broken"]

        writer, store, idem = _writer(commit_check=check)
        # Commit Check 失败 = 服务器不变量违反：ApiError 直接上抛（响亮失败），
        # 但原子性不变——Revision 不变、无幂等记录、无事件
        with pytest.raises(ApiError) as exc_info:
            writer.execute(command_envelope(ULID_A, "w1"))
        assert exc_info.value.code == "BACKEND_INTERNAL_INVARIANT"
        assert "commit_check" in str(exc_info.value.details)
        assert store.current_revision("w1") == 0
        assert idem.count("w1") == 0


# ---------------------------------------------------------------------------
# TEST-BACKEND-038：RULE-BACKEND-059 外部效应拆分与最新 Revision 重校验
# ---------------------------------------------------------------------------

class TestExternalEffectSplit:
    def test_domain_apply_is_synchronous_no_io_in_uow(self):
        """事务内禁止 await 外部 I/O：domain_apply 必须是同步可调用"""
        import inspect
        writer, _store, _idem = _writer()
        assert not inspect.iscoroutinefunction(writer._domain_apply)
        assert not inspect.isasyncgenfunction(writer._domain_apply)

    def test_async_result_returns_as_new_command_with_recheck(self):
        """意图事件提交后 Revision 前进；异步结果以新命令回到队列时，
        strict expected_revision 必须按最新 Revision 重校验"""
        writer, store, _idem = _writer()
        # 1) 意图命令提交：Revision 0 → 1
        intent = command_envelope(ULID_A, "w1")
        assert writer.execute(intent)["result"] == "committed"
        assert store.current_revision("w1") == 1
        # 2) 异步效应完成，结果以 strict 命令回到队列：
        #    按入队时的旧 Revision(0) 声明 → 执行时刻重校验拒绝
        stale = command_envelope(ULID_B, "w1", command_type="mayor.tax.propose",
                                 expected_revision=0,
                                 payload={"schema_version": 1, "rate_bp": 100})
        receipt = writer.execute(stale)
        assert receipt["result"] == "rejected"
        assert receipt["error"]["code"] == "BACKEND_STALE_REVISION"
        assert receipt["error"]["details"]["received"] == 1
        # 3) 以最新 Revision 重发 → 提交成功
        fresh = command_envelope(ULID_C, "w1", command_type="mayor.tax.propose",
                                 expected_revision=1,
                                 payload={"schema_version": 1, "rate_bp": 100})
        assert writer.execute(fresh)["result"] == "committed"
        assert store.current_revision("w1") == 2
