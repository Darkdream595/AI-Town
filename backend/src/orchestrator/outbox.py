"""
Outbox 与断线补发（DOC-BACKEND-003 RULE-BACKEND-015..017 / DOC-BACKEND-006 §5）

- 事件按 Revision 严格递增推送，不重排、不跳号；ack 后释放已确认缓冲
- 不可丢 DomainEvent 永不丢弃；Outbox 满先合并 coalescible render delta，
  仍超容量 → 标记 Lagging、丢弃增量缓冲、强制 Snapshot resync
- catch-up：补发 (last_acked, current] 全部不可丢事件；区间不可用或超
  catch_up_max_events → Snapshot fallback，禁止静默跳过
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from ..foundation.errors import ApiError
from .events import EventRegistry

CATCH_UP_MAX_EVENTS = 5000
WS_OUTBOX_CAPACITY = 512


class SnapshotRequired(Exception):
    """增量不可用/过大 → 强制 Snapshot fallback"""


class CommittedEventLog:
    """已提交事件只读日志（内存 port；持久化由 persistence 阶段实现）"""

    def __init__(self, retention: Optional[int] = None) -> None:
        self._events: List[dict] = []
        self._retention = retention  # 模拟裁剪窗口
        self._pruned_before: int = 0

    def append_commit(self, events: List[dict]) -> None:
        self._events.extend(events)
        if self._retention is not None:
            while len(self._events) > self._retention:
                self._pruned_before = self._events[0]["revision"]
                self._events.pop(0)

    def current_revision(self) -> int:
        return self._events[-1]["revision"] if self._events else 0

    def events_in_range(self, after_revision: int, up_to: Optional[int] = None,
                        coalescible_filter: Optional[Callable[[str], bool]] = None
                        ) -> List[dict]:
        """补发区间 (after_revision, up_to]；区间已裁剪 → SnapshotRequired"""
        if after_revision < self._pruned_before:
            raise SnapshotRequired("range_pruned")
        selected = []
        for event in self._events:
            if event["revision"] <= after_revision:
                continue
            if up_to is not None and event["revision"] > up_to:
                continue
            if coalescible_filter is not None and coalescible_filter(event["type"]):
                continue  # catch-up 只补不可丢事件
            selected.append(event)
        return selected


@dataclass
class OutboxState:
    state: str = "live"  # live / lagging
    max_pushed_revision: int = 0   # 已入缓冲的最大 Revision
    sent_revision: int = 0         # 已发给 Client 的最大 Revision
    last_acked_revision: int = 0   # Client 已确认的最大连续 Revision


class SessionOutbox:
    """每 Session 的有界出站缓冲（RULE-BACKEND-017）"""

    def __init__(self, session_id: str, world_id: str,
                 registry: EventRegistry,
                 capacity: int = WS_OUTBOX_CAPACITY) -> None:
        self.session_id = session_id
        self.world_id = world_id
        self._registry = registry
        self.capacity = capacity
        self.state = OutboxState()
        self._events: List[dict] = []          # 不可丢事件（按 revision 递增）
        self._deltas: Dict[str, dict] = {}     # coalescible：entity 键 → 最新 delta
        self.resync_required = False

    # -- 入站 ----------------------------------------------------------------

    def push(self, event: dict) -> None:
        if self._registry.is_coalescible(event["type"]):
            key = f"{event['type']}:{event['payload'].get('entity_id', '')}"
            self._deltas[key] = event  # 合并：只保留最新一条
        else:
            self._events.append(event)
        self.state.max_pushed_revision = max(self.state.max_pushed_revision,
                                             event["revision"])
        self._enforce_capacity()

    def _enforce_capacity(self) -> None:
        pending = len(self._events) + len(self._deltas)
        if pending <= self.capacity:
            return
        # coalescible 已合并仍超容量：不可丢事件不得丢弃 → Lagging + 强制 resync
        self.state.state = "lagging"
        self._events.clear()
        self._deltas.clear()
        self.resync_required = True

    # -- 出站 ----------------------------------------------------------------

    def pending_frames(self) -> List[dict]:
        """按 Revision 全序返回尚未发送的帧（deltas 按 revision 插入序列）"""
        unsent = [e for e in self._events
                  if e["revision"] > self.state.sent_revision]
        unsent += [e for e in self._deltas.values()
                   if e["revision"] > self.state.sent_revision]
        unsent.sort(key=lambda e: (e["revision"], e["event_id"]))
        return unsent

    def mark_sent(self) -> None:
        self.state.sent_revision = self.state.max_pushed_revision

    def ack(self, last_acked_revision: int) -> None:
        """释放已 ack 的不可丢事件缓冲（只前进）"""
        if last_acked_revision > self.state.last_acked_revision:
            self.state.last_acked_revision = last_acked_revision
        self._events = [e for e in self._events
                        if e["revision"] > self.state.last_acked_revision]
        self._deltas = {k: e for k, e in self._deltas.items()
                        if e["revision"] > self.state.last_acked_revision}

    def depth(self) -> int:
        return len(self._events) + len(self._deltas)

    # -- 断线补发 ---------------------------------------------------------------

    def catch_up(self, event_log: CommittedEventLog,
                 last_acked_revision: int) -> List[dict]:
        """
        补发 (last_acked, current] 全部不可丢事件；
        区间已裁剪或超 catch_up_max_events → SnapshotRequired
        """
        events = event_log.events_in_range(
            last_acked_revision,
            coalescible_filter=self._registry.is_coalescible)
        if len(events) > CATCH_UP_MAX_EVENTS:
            raise SnapshotRequired("range_too_large")
        for event in events:
            self.push(event)
        if self.resync_required:
            raise SnapshotRequired("outbox_overflow")
        return events

    def handover_to(self, other: "SessionOutbox") -> None:
        """supersede：Outbox 游标移交给新连接（RULE-BACKEND-013）"""
        other.state.max_pushed_revision = self.state.max_pushed_revision
        other.state.sent_revision = self.state.sent_revision
        other.state.last_acked_revision = self.state.last_acked_revision
        other._events = list(self._events)
        other._deltas = dict(self._deltas)
        self._events.clear()
        self._deltas.clear()
