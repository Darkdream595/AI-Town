"""
有界队列与满溢策略（DOC-BACKEND-001 RULE-BACKEND-004..006）

- AI Request / Long Action / Persistence / WebSocket Outbox 四类异步队列与
  World Command Queue 彼此隔离；任一队列积压不得阻塞 World Tick 提交
- 每队列固定容量上限：World Command Queue 满 → BACKEND_QUEUE_FULL 回执；
  其余队列按 owner 降级策略丢弃可合并项；不可丢 DomainEvent 永不丢弃（Outbox 层保证）
"""

from __future__ import annotations

from collections import deque
from typing import Callable, Deque, Dict, List, Optional

from ..foundation.errors import ApiError

#: 满溢策略：reject_new（World Command）/ drop_oldest_mergeable（可合并项）/ never_drop
OVERFLOW_REJECT_NEW = "reject_new"
OVERFLOW_DROP_MERGEABLE = "drop_oldest_mergeable"
OVERFLOW_NEVER_DROP = "never_drop"


class QueueOverflow(Exception):
    def __init__(self, queue: str) -> None:
        super().__init__(queue)
        self.queue = queue


class BoundedQueue:
    """单消费者有界队列；item 可标 mergeable=True（可被满溢策略合并丢弃）"""

    def __init__(self, name: str, capacity: int,
                 overflow_policy: str,
                 monotonic_ms: Callable[[], int],
                 on_drop: Optional[Callable[[object], None]] = None) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.name = name
        self.capacity = capacity
        self.overflow_policy = overflow_policy
        self._clock = monotonic_ms
        self._on_drop = on_drop
        self._items: Deque = deque()
        self._enqueued_at: Deque = deque()
        self.dropped_count = 0

    def __len__(self) -> int:
        return len(self._items)

    def depth(self) -> int:
        return len(self._items)

    def oldest_wait_ms(self) -> int:
        if not self._enqueued_at:
            return 0
        return max(0, self._clock() - self._enqueued_at[0])

    def put(self, item: object, mergeable: bool = False) -> None:
        if len(self._items) < self.capacity:
            self._items.append((item, mergeable))
            self._enqueued_at.append(self._clock())
            return
        # 满溢
        if self.overflow_policy == OVERFLOW_REJECT_NEW:
            raise QueueOverflow(self.name)
        if self.overflow_policy == OVERFLOW_DROP_MERGEABLE:
            # 从队首找第一个可合并项丢弃；新项入队
            for index in range(len(self._items)):
                if self._items[index][1]:
                    del self._items[index]
                    del self._enqueued_at[index]
                    self.dropped_count += 1
                    if self._on_drop is not None:
                        self._on_drop(item)
                    self._items.append((item, mergeable))
                    self._enqueued_at.append(self._clock())
                    return
            raise QueueOverflow(self.name)
        # never_drop：调用方（Outbox）必须先降级（合并/快照），不得走到这里
        raise QueueOverflow(self.name)

    def get(self) -> object:
        item, _mergeable = self._items.popleft()
        self._enqueued_at.popleft()
        return item

    def drain(self) -> List[object]:
        items = [item for item, _ in self._items]
        self._items.clear()
        self._enqueued_at.clear()
        return items

    def peek_items(self) -> List[object]:
        return [item for item, _ in self._items]


class QueueSet:
    """进程级隔离队列组（RULE-BACKEND-004）：任一积压不影响其他"""

    QUEUE_NAMES = ("ai_request", "long_action", "persistence", "ws_outbox")

    def __init__(self, monotonic_ms: Callable[[], int],
                 capacities: Optional[Dict[str, int]] = None,
                 world_command_capacity: int = 256) -> None:
        capacities = capacities or {}
        self._clock = monotonic_ms
        self.world_command: Dict[str, BoundedQueue] = {}
        self._world_command_capacity = world_command_capacity
        self.queues: Dict[str, BoundedQueue] = {
            name: BoundedQueue(
                name,
                capacities.get(name, 512 if name == "ws_outbox" else 256),
                OVERFLOW_DROP_MERGEABLE if name != "ws_outbox" else OVERFLOW_NEVER_DROP,
                monotonic_ms,
            )
            for name in self.QUEUE_NAMES
        }

    def world_command_queue(self, world_id: str) -> BoundedQueue:
        queue = self.world_command.get(world_id)
        if queue is None:
            queue = BoundedQueue(f"world_command.{world_id}",
                                 self._world_command_capacity,
                                 OVERFLOW_REJECT_NEW, self._clock)
            self.world_command[world_id] = queue
        return queue

    def metrics_snapshot(self) -> Dict[str, dict]:
        snapshot = {}
        for name, queue in self.queues.items():
            snapshot[name] = {"depth": queue.depth(),
                              "oldest_wait_ms": queue.oldest_wait_ms(),
                              "dropped": queue.dropped_count}
        for world_id, queue in self.world_command.items():
            snapshot[queue.name] = {"depth": queue.depth(),
                                    "oldest_wait_ms": queue.oldest_wait_ms(),
                                    "dropped": queue.dropped_count}
        return snapshot


def put_world_command(queue: BoundedQueue, envelope: object) -> None:
    """World Command Queue 入口：满 → BACKEND_QUEUE_FULL（retryable）"""
    try:
        queue.put(envelope)
    except QueueOverflow:
        raise ApiError("BACKEND_QUEUE_FULL",
                       {"queue": "world_command"}, retry_after_ms=500) from None
