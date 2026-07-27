"""
确定性随机流（DOC-TIME-010 的 COMBAT 侧落地）

- stream + scope + 递增 sequence 派生 uint32；重放逐字节一致
- rejection sampling 的 raw block 消耗全部计入同一 draw result
- sequence 只在事务提交时前进；回滚 = 恢复到事务前快照
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

_UINT32_SPACE = 1 << 32


class RandomStreamError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


class DeterministicRandomStream:
    """单一 (stream, scope) 的确定性抽取序列"""

    def __init__(self, world_seed_hex: str, stream: str, scope: str) -> None:
        self._seed_material = f"{world_seed_hex}:{stream}:{scope}"
        self.stream = stream
        self.scope = scope
        self.block_counter = 0  # 已消费的 raw block 数（事务性前进）

    def _raw_block(self, index: int) -> bytes:
        digest = hashlib.sha256(f"{self._seed_material}:{index}".encode("ascii")).digest()
        return digest

    def snapshot(self) -> int:
        """事务开始时的 sequence 快照；回滚即 restore"""
        return self.block_counter

    def restore(self, snapshot: int) -> None:
        self.block_counter = snapshot

    def draw_bounded_uint32(self, bound: int) -> int:
        """rejection sampling：拒绝区重抽的 raw block 全部计入消耗"""
        if bound <= 0 or bound > _UINT32_SPACE:
            raise RandomStreamError("combat_roll_bound_invalid", str(bound))
        if bound == 1:
            self.block_counter += 1
            return 0
        accept_limit = (_UINT32_SPACE // bound) * bound
        while True:
            block = self._raw_block(self.block_counter)
            self.block_counter += 1
            for offset in range(0, 32, 4):
                value = int.from_bytes(block[offset : offset + 4], "big")
                if value < accept_limit:
                    return value % bound


class CombatRngHub:
    """按 (stream, scope) 复用流实例；三个注册流名"""

    STREAM_INITIATIVE = "combat.initiative"
    STREAM_ROLL = "combat.roll"
    STREAM_LOOT = "combat.loot"

    def __init__(self, world_seed_hex: str) -> None:
        self._seed_hex = world_seed_hex
        self._streams: dict = {}

    def stream(self, stream: str, scope: str) -> DeterministicRandomStream:
        key = (stream, scope)
        if key not in self._streams:
            self._streams[key] = DeterministicRandomStream(self._seed_hex, stream, scope)
        return self._streams[key]

    def snapshot_all(self) -> dict:
        return {key: s.block_counter for key, s in self._streams.items()}

    def restore_all(self, snapshot: dict) -> None:
        for (stream, scope), counter in snapshot.items():
            # 恢复目标流可能尚未创建：按需实例化后回写已提交 draw sequence
            self.stream(stream, scope).block_counter = counter


@dataclass(frozen=True)
class RollRecord:
    """CombatActionResolved.rolls 的单条记录"""

    slot: str
    value: int
