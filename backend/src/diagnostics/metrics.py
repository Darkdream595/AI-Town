"""
指标注册表与性能预算（DOC-BACKEND-012 RULE-BACKEND-068/069）

- 进程内 registry，经 MetricsSnapshotV1（含 schema_version）暴露
- 只含数值与低基数标签（world_id、queue、error code、route class）
- 预算：连续 3 个采样窗口超预算即 Budget Breach，上报降档链路
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

#: 核心指标清单（缺一即验收失败）：name → (类型, 标签维度)
CORE_METRICS: Dict[str, Tuple[str, Tuple[str, ...]]] = {
    "tick_critical_section_ms": ("summary", ("world_id",)),
    "queue_depth": ("gauge", ("queue",)),
    "queue_oldest_wait_ms": ("gauge", ("queue",)),
    "command_latency_ms": ("summary", ()),
    "event_fanout_latency_ms": ("summary", ()),
    "ws_sessions": ("gauge", ("state",)),
    "error_count": ("counter", ("code",)),
    "model_request_latency_ms": ("summary", ("result",)),
    "model_request_count": ("counter", ("result",)),
    "idempotency_hit_count": ("counter", ()),
    "budget_breach_count": ("counter", ("budget",)),
    "process_memory_bytes": ("gauge", ()),
    "db_size_bytes": ("gauge", ()),
    "log_write_failure": ("counter", ()),
}

#: 性能预算（RULE-BACKEND-069，本机基准，25 居民世界）
PERFORMANCE_BUDGETS: Dict[str, float] = {
    "rest_admin_p95_ms": 50.0,
    "command_receipt_p95_ms": 150.0,
    "event_fanout_p95_ms": 50.0,
    "ws_heartbeat_p95_ms": 20.0,
    "process_memory_bytes": 1.5 * 1024 ** 3,
}

BUDGET_BREACH_CONSECUTIVE_WINDOWS = 3
SUMMARY_MAX_SAMPLES = 2048


def _label_key(labels: Optional[dict]) -> Tuple[Tuple[str, str], ...]:
    return tuple(sorted((str(k), str(v)) for k, v in (labels or {}).items()))


class _Summary:
    def __init__(self) -> None:
        self.samples: List[float] = []

    def add(self, value: float) -> None:
        self.samples.append(float(value))
        if len(self.samples) > SUMMARY_MAX_SAMPLES:
            del self.samples[: len(self.samples) - SUMMARY_MAX_SAMPLES]

    def quantiles(self) -> Dict[str, Optional[float]]:
        if not self.samples:
            return {"p50": None, "p95": None, "p99": None}
        ordered = sorted(self.samples)

        def pick(q: float) -> float:
            index = min(len(ordered) - 1, max(0, int(q * len(ordered))))
            return ordered[index]

        return {"p50": pick(0.50), "p95": pick(0.95), "p99": pick(0.99)}


class MetricsRegistry:
    def __init__(self) -> None:
        self._counters: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], float] = {}
        self._gauges: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], float] = {}
        self._summaries: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], _Summary] = {}

    # -- 记录 ----------------------------------------------------------------

    def increment(self, name: str, amount: float = 1.0,
                  labels: Optional[dict] = None) -> None:
        key = (name, _label_key(labels))
        self._counters[key] = self._counters.get(key, 0.0) + amount

    def set_gauge(self, name: str, value: float,
                  labels: Optional[dict] = None) -> None:
        self._gauges[(name, _label_key(labels))] = float(value)

    def observe(self, name: str, value: float,
                labels: Optional[dict] = None) -> None:
        key = (name, _label_key(labels))
        summary = self._summaries.get(key)
        if summary is None:
            summary = _Summary()
            self._summaries[key] = summary
        summary.add(value)

    # -- 读取 ----------------------------------------------------------------

    def counter(self, name: str, labels: Optional[dict] = None) -> float:
        return self._counters.get((name, _label_key(labels)), 0.0)

    def gauge(self, name: str, labels: Optional[dict] = None) -> Optional[float]:
        return self._gauges.get((name, _label_key(labels)))

    def summary(self, name: str, labels: Optional[dict] = None) -> Dict[str, Optional[float]]:
        summary = self._summaries.get((name, _label_key(labels)))
        return summary.quantiles() if summary else {"p50": None, "p95": None, "p99": None}

    def snapshot(self) -> dict:
        """MetricsSnapshotV1：核心清单全键存在（无数据为 null/0）"""
        data: Dict[str, object] = {}
        for name, (kind, _dims) in CORE_METRICS.items():
            if kind == "counter":
                data[name] = [
                    {"value": value, "labels": dict(labels)}
                    for (metric, labels), value in self._counters.items()
                    if metric == name
                ]
            elif kind == "gauge":
                data[name] = [
                    {"value": value, "labels": dict(labels)}
                    for (metric, labels), value in self._gauges.items()
                    if metric == name
                ]
            else:
                data[name] = [
                    {**summary.quantiles(), "labels": dict(labels),
                     "samples": len(summary.samples)}
                    for (metric, labels), summary in self._summaries.items()
                    if metric == name
                ]
        return {"schema_version": 1, "metrics": data}


def audit_metrics_completeness(snapshot: dict) -> List[str]:
    """核心清单缺口列表；空 = 完备"""
    metrics = snapshot.get("metrics", {})
    return [name for name in CORE_METRICS if name not in metrics]


class BudgetEvaluator:
    """采样窗口评估：连续 N 窗超预算 → Budget Breach 事件"""

    def __init__(self, budgets: Optional[Dict[str, float]] = None,
                 consecutive: int = BUDGET_BREACH_CONSECUTIVE_WINDOWS) -> None:
        self._budgets = dict(budgets or PERFORMANCE_BUDGETS)
        self._consecutive = consecutive
        self._violations: Dict[str, int] = {}
        self._breached: Dict[str, bool] = {}

    def evaluate_window(self, samples: Dict[str, Optional[float]]) -> List[str]:
        """samples: budget 名 → 本窗实测值（None 跳过）；返回本窗新触发 Breach 的 budget 名"""
        fired: List[str] = []
        for budget, limit in self._budgets.items():
            value = samples.get(budget)
            if value is None:
                continue
            if value > limit:
                self._violations[budget] = self._violations.get(budget, 0) + 1
                if (self._violations[budget] >= self._consecutive
                        and not self._breached.get(budget)):
                    self._breached[budget] = True
                    fired.append(budget)
            else:
                self._violations[budget] = 0
                self._breached[budget] = False
        return fired

    def breached(self, budget: str) -> bool:
        return self._breached.get(budget, False)
