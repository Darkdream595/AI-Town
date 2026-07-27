"""
确定性随机流（DOC-TIME-010 的 EVENT 侧落地）

- stream + scope + 递增 sequence 派生 uint32；重放逐字节一致
- 抽样流命名：触发器 `event.trigger.<trigger_id 末段>`，天气 `event.weather.<region 末段>`
- sequence 只在事务提交时前进；回滚 = 恢复到事务前快照
"""

from __future__ import annotations

import hashlib

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
        self.block_counter = 0

    def _raw_block(self, index: int) -> bytes:
        return hashlib.sha256(f"{self._seed_material}:{index}".encode("ascii")).digest()

    def snapshot(self) -> int:
        return self.block_counter

    def restore(self, snapshot: int) -> None:
        self.block_counter = snapshot

    def draw_bounded_uint32(self, bound: int) -> int:
        """rejection sampling：拒绝区重抽的 raw block 全部计入消耗"""
        if bound <= 0 or bound > _UINT32_SPACE:
            raise RandomStreamError("event_roll_bound_invalid", str(bound))
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

    def draw_probability_millionths(self) -> int:
        """0..999999 均匀抽取，与 activation_chance_0_to_1（百万分之一精度）比较"""
        return self.draw_bounded_uint32(1_000_000)


class EventRngHub:
    """按 (stream, scope) 复用流实例；导出/导入状态用于崩溃恢复"""

    def __init__(self, world_seed_hex: str) -> None:
        self._seed_hex = world_seed_hex
        self._streams: dict = {}

    def stream(self, stream: str, scope: str) -> DeterministicRandomStream:
        key = (stream, scope)
        if key not in self._streams:
            self._streams[key] = DeterministicRandomStream(self._seed_hex, stream, scope)
        return self._streams[key]

    def trigger_stream(self, trigger_id: str) -> DeterministicRandomStream:
        return self.stream(f"event.trigger.{trigger_id.split('.')[-1]}", trigger_id)

    def weather_stream(self, region_id: str) -> DeterministicRandomStream:
        return self.stream(f"event.weather.{region_id.split('.')[-1]}", region_id)

    def snapshot_all(self) -> dict:
        return {f"{stream}|{scope}": s.block_counter for (stream, scope), s in self._streams.items()}

    def restore_all(self, snapshot: dict) -> None:
        self._streams = {}
        for key, counter in snapshot.items():
            stream, scope = key.split("|", 1)
            # 恢复目标流可能尚未创建：按需实例化后回写已提交 draw sequence
            self.stream(stream, scope).block_counter = counter


def trigger_stream_name(trigger_id: str) -> str:
    return f"event.trigger.{trigger_id.split('.')[-1]}"


def weather_stream_name(region_id: str) -> str:
    return f"event.weather.{region_id.split('.')[-1]}"
