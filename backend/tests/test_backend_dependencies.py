"""TEST-BACKEND-005..008：依赖矩阵静态审计、UoW 原子性、Domain 确定性、Secret 边界"""
from __future__ import annotations

import ast
import os
import re

import pytest

from backend_helpers import make_id_factory, make_utc_factory
from src.foundation.errors import ApiError
from src.orchestrator.commands import CommandRegistry, CommandSpec
from src.orchestrator.events import EventRegistry
from src.orchestrator.idempotency import IdempotencyStore
from src.orchestrator.uow import (
    UOW_STEPS,
    WorldStore,
    WorldWriter,
)
from src.api.wire import register_command_specs, register_event_specs
from src.api.schemas import SchemaRegistry

SRC_ROOT = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src")

DOMAIN_PACKAGES = frozenset({
    "ai", "combat", "dialogue", "economy", "events", "magic", "map",
    "memory", "player", "residents", "shared", "time", "time_simulation",
    "world",
})
LEAF_PACKAGES = frozenset({"foundation", "diagnostics", "security",
                           "persistence"})


def _iter_src_files():
    for package in sorted(os.listdir(SRC_ROOT)):
        package_dir = os.path.join(SRC_ROOT, package)
        if package == "__pycache__" or not os.path.isdir(package_dir):
            continue
        for root, _dirs, files in os.walk(package_dir):
            if "__pycache__" in root:
                continue
            for filename in sorted(files):
                if filename.endswith(".py"):
                    yield package, os.path.join(root, filename)


def _src_packages():
    return {package for package, _path in _iter_src_files()}


def _collect_edges():
    """(package, path) → (src 边集合, 第三方 import 集合)。

    `src.x` 显式前缀与裸包名（遗留风格 `from world import ...`）都归一化为边。
    """
    known = _src_packages()
    edges = {}
    for package, path in _iter_src_files():
        src_edges, third_party = set(), set()
        rel = os.path.relpath(path, SRC_ROOT).replace(os.sep, "/")[:-3]
        package_parts = rel.split("/")[:-1]
        tree = ast.parse(open(path, encoding="utf-8").read())
        for node in ast.walk(tree):
            targets = []
            if isinstance(node, ast.Import):
                targets = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level > 0:
                    base = package_parts[:len(package_parts) - (node.level - 1)]
                    module = ".".join(["src"] + base +
                                      ([node.module] if node.module else []))
                else:
                    module = node.module or ""
                targets = [module]
            for target in targets:
                parts = target.split(".")
                if parts[0] == "src" and len(parts) > 1 and parts[1] in known:
                    src_edges.add(parts[1])
                elif parts[0] in known:
                    src_edges.add(parts[0])  # 裸包名遗留风格
                elif parts[0] not in ("__future__",):
                    third_party.add(parts[0])
        edges[(package, path)] = (src_edges - {package}, third_party)
    return edges


# ---------------------------------------------------------------------------
# TEST-BACKEND-005：RULE-BACKEND-007..008 依赖矩阵静态审计
# ---------------------------------------------------------------------------

class TestDependencyMatrix:
    EDGES = None

    @classmethod
    def edges(cls):
        if cls.EDGES is None:
            cls.EDGES = _collect_edges()
        return cls.EDGES

    def _violations(self, allowed_by_package):
        violations = []
        for (package, path), (src_edges, _third) in self.edges().items():
            allowed = allowed_by_package.get(package)
            if allowed is None:  # bootstrap 可装配一切
                continue
            for target in src_edges - allowed:
                violations.append(f"{path}: {package} -> {target}")
        return violations

    def test_leaf_packages_only_depend_on_foundation(self):
        allowed = {package: {"foundation"} - {package}
                   for package in LEAF_PACKAGES}
        assert self._violations(allowed) == []

    def test_domain_packages_never_depend_outward(self):
        allowed = {package: ({"foundation"} | DOMAIN_PACKAGES) - {package}
                   for package in DOMAIN_PACKAGES}
        violations = self._violations(allowed)
        assert violations == []

    def test_orchestrator_never_depends_on_api_or_bootstrap(self):
        allowed = {"orchestrator": ({"foundation", "security", "persistence"}
                                    | DOMAIN_PACKAGES)}
        assert self._violations(allowed) == []

    def test_api_only_depends_on_foundation_orchestrator_security(self):
        allowed = {"api": {"foundation", "orchestrator", "security"}}
        assert self._violations(allowed) == []

    def test_no_transport_or_sql_imports_outside_adapters(self):
        """RULE-BACKEND-008：fastapi/uvicorn 只在 api 与入口；
        sqlite3 只在 persistence；HTTP SDK 只在 ai"""
        transport_bad, sql_bad, http_bad = [], [], []
        for (package, path), (_src, third) in self.edges().items():
            if package not in ("api", "bootstrap"):
                if third & {"fastapi", "uvicorn", "starlette", "pydantic"} - {"pydantic"}:
                    transport_bad.append(path)
            if package != "persistence" and "sqlite3" in third:
                sql_bad.append(path)
            if package != "ai" and third & {"httpx", "requests", "openai"}:
                http_bad.append(path)
        assert transport_bad == []
        assert sql_bad == []
        assert http_bad == []


# ---------------------------------------------------------------------------
# TEST-BACKEND-006：RULE-BACKEND-010 UoW 原子性故障注入
# ---------------------------------------------------------------------------

def _make_writer(domain_apply=None, on_storage_failure=None):
    schemas = SchemaRegistry()
    commands = CommandRegistry()
    events = EventRegistry()
    register_command_specs(schemas, commands)
    register_event_specs(schemas, events)
    store = WorldStore()
    store.open_world("w1")
    idem = IdempotencyStore(make_utc_factory())
    apply = domain_apply or (lambda _w, _t, payload, _ctx: {
        "state": {"paused": payload.get("paused")},
        "events": [],
        "reservations": [],
    })
    writer = WorldWriter(store, idem, commands, events,
                         make_id_factory("tx"), make_utc_factory(), apply,
                         on_storage_failure=on_storage_failure)
    envelope = {
        "protocol_version": 1,
        "command_id": "01K1AB2CD3EF4GH5JK6MNP7QS0",
        "world_id": "w1",
        "type": "system.world.pause",
        "expected_revision": None,
        "payload": {"schema_version": 1, "paused": True},
    }
    return writer, store, idem, envelope, events


def _weather_event(events, context, tick=1):
    from src.orchestrator.events import build_event
    return build_event(
        events, make_id_factory("evt"), world_id=context["world_id"],
        revision=context["revision"], event_type="world.weather.changed",
        game_time=context["game_time"],
        causation_id=context["command_id"],
        correlation_id=context["command_id"],
        payload={"schema_version": 1, "weather": "rain",
                 "started_at_tick": tick})


class TestUowAtomicity:
    def test_commit_success_all_steps_materialized(self):
        def apply(_w, _t, _p, context):
            return {
                "state": {"x": 1},
                "events": [_weather_event(_events_ref[0], context)],
                "reservations": [{"reservation_id": "r1"}],
            }

        _events_ref = [None]
        writer, store, idem, envelope, events = _make_writer(domain_apply=apply)
        _events_ref[0] = events
        receipt = writer.execute(envelope)
        assert receipt["result"] == "committed"
        assert receipt["committed_revision"] == 1
        assert store.current_revision("w1") == 1
        assert store.step_log == list(UOW_STEPS)
        assert len(receipt["event_ids"]) == 1

    @pytest.mark.parametrize("fail_step", list(UOW_STEPS))
    def test_failure_at_any_step_rolls_back_everything(self, fail_step):
        writer, store, idem, envelope, _events = _make_writer()
        store.fail_at = fail_step
        receipt = writer.execute(envelope)
        # 存储失败：failed 回执、revision 不动、无幂等记录、无半提交状态
        assert receipt["result"] == "failed"
        assert receipt["error"]["code"] == "BACKEND_STORAGE_FAILURE"
        assert store.current_revision("w1") == 0
        assert idem.lookup("w1", envelope["command_id"], "any") is None

    def test_storage_failure_callback_invoked(self):
        seen = []
        writer, store, _idem, envelope, _e = _make_writer(
            on_storage_failure=seen.append)
        store.fail_at = UOW_STEPS[2]
        writer.execute(envelope)
        assert seen == ["w1"]

    def test_retry_after_failure_commits_cleanly(self):
        writer, store, _idem, envelope, _e = _make_writer()
        store.fail_at = UOW_STEPS[-1]
        failed = writer.execute(envelope)
        assert failed["result"] == "failed"
        store.fail_at = None
        receipt = writer.execute(envelope)
        assert receipt["result"] == "committed"
        assert store.current_revision("w1") == 1


# ---------------------------------------------------------------------------
# TEST-BACKEND-007：RULE-BACKEND-011 Domain 确定性（相同输入相同输出）
# ---------------------------------------------------------------------------

class TestDomainDeterminism:
    def test_economy_state_hash_deterministic(self):
        from src.economy.audit import economy_state_hash
        from src.economy.currency import CurrencyLedger
        first = economy_state_hash(CurrencyLedger())
        second = economy_state_hash(CurrencyLedger())
        assert first == second

    def test_writer_same_command_same_receipt(self):
        writer_a, _s1, _i1, envelope, _ea = _make_writer()
        writer_b, _s2, _i2, _e2, _eb = _make_writer()
        receipt_a = writer_a.execute(dict(envelope))
        receipt_b = writer_b.execute(dict(envelope))
        # 去掉 id_factory 生成的 tx id 后逐字段一致
        receipt_a.pop("event_ids")
        receipt_b.pop("event_ids")
        assert receipt_a == receipt_b

    def test_determinism_no_wall_clock_in_domain(self):
        """Domain 输出不依赖真实墙钟：同一装配在不同系统时间下结果一致"""
        from src.economy.audit import economy_state_hash
        from src.economy.currency import CurrencyLedger
        ledger = CurrencyLedger()
        before = economy_state_hash(ledger)
        import time as _time
        _time.sleep(0.001)  # 墙钟前进不影响纯计算
        assert economy_state_hash(ledger) == before


# ---------------------------------------------------------------------------
# TEST-BACKEND-008：RULE-BACKEND-009 非 security 包无 Secret 句柄访问路径
# ---------------------------------------------------------------------------

class TestSecretHandleBoundary:
    #: 明文句柄访问标识符：只允许出现在 src/security/ 与 ai/ ModelProvider adapter
    PLAINTEXT_PATTERNS = (
        r"\bCredWrite\b", r"\bCredRead\b", r"\bCredEnumerate\b",
        r"\bCryptProtectData\b", r"\bCryptUnprotectData\b",
        r"\bWindowsCredentialManagerStore\b", r"\bDpapiFileStore\b",
        r"\bAuthHeaderHandle\(", r"\bresolve_for_request\(",
    )

    def test_no_plaintext_access_outside_security_and_ai(self):
        pattern = re.compile("|".join(self.PLAINTEXT_PATTERNS))
        violations = []
        for package, path in _iter_src_files():
            if package in ("security", "ai"):
                continue
            text = open(path, encoding="utf-8").read()
            for match in pattern.finditer(text):
                line = text[:match.start()].count("\n") + 1
                violations.append(f"{path}:{line}: {match.group(0)}")
        assert violations == []

    def test_ai_adapter_never_imports_secret_store_backends(self):
        """ai/ 只能拿到 opaque credential ref，不得直接 import 存储后端"""
        for (package, path), (src_edges, _third) in \
                TestDependencyMatrix.edges().items():
            if package != "ai":
                continue
            text = open(path, encoding="utf-8").read()
            assert "MemorySecretStore" not in text, path
            assert "ChainedSecretStore" not in text, path
