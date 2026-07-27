"""
测试时间模拟器

验证游戏时间推进和事件触发
"""

import pytest

from src.time_simulation import TimeSimulator, TimeState
from src.foundation import RealTime
from src.world import Season


class TestTimeState:
    """时间状态测试"""

    def test_create_time_state(self):
        """测试创建时间状态"""
        creation_time = RealTime(timestamp_ms=1000000)
        state = TimeState(
            current_game_time=0,
            world_creation_time=creation_time
        )

        assert state.current_game_time == 0
        assert state.world_creation_time.timestamp_ms == 1000000

    def test_get_current_date(self):
        """测试获取当前日期"""
        creation_time = RealTime(timestamp_ms=1000000)
        state = TimeState(
            current_game_time=0,
            world_creation_time=creation_time
        )

        year, month, day, hour, minute = state.get_current_date()
        assert year == 0
        assert month == 1
        assert day == 1
        assert hour == 0
        assert minute == 0

    def test_get_current_season(self):
        """测试获取当前季节"""
        creation_time = RealTime(timestamp_ms=1000000)
        state = TimeState(
            current_game_time=0,
            world_creation_time=creation_time
        )

        season = state.get_current_season()
        assert season == Season.SPRING  # 第 1 个月是春季

    def test_is_daytime(self):
        """测试白天判断"""
        creation_time = RealTime(timestamp_ms=1000000)

        # 早上 8:00 (480 分钟)
        state = TimeState(current_game_time=480, world_creation_time=creation_time)
        assert state.is_daytime() is True

        # 晚上 20:00 (1200 分钟)
        state = TimeState(current_game_time=1200, world_creation_time=creation_time)
        assert state.is_daytime() is False


class TestTimeSimulator:
    """时间模拟器测试"""

    def test_create_simulator(self):
        """测试创建时间模拟器"""
        creation_time = RealTime(timestamp_ms=1000000)
        sim = TimeSimulator(creation_time)

        assert sim.state.current_game_time == 0
        assert len(sim.event_handlers) == 0

    def test_update_time(self):
        """测试时间更新"""
        creation_time = RealTime(timestamp_ms=1000000)
        sim = TimeSimulator(creation_time)

        # 60 秒后（60 游戏分钟 = 1 游戏小时）
        current_time = RealTime(timestamp_ms=1060000)
        sim.update(current_time)

        assert sim.state.current_game_time == 60

    def test_day_changed_event(self):
        """测试跨日事件"""
        creation_time = RealTime(timestamp_ms=1000000)
        sim = TimeSimulator(creation_time)

        events_triggered = []

        def handler(event_type, data):
            events_triggered.append(event_type)

        sim.register_handler(handler)

        # 1440 游戏分钟后（1 游戏天）：1 现实秒 = 1 游戏分钟，对应 1440 现实秒
        # 第 0 年 1 月 1 日 → 第 0 年 1 月 2 日
        current_time = RealTime(timestamp_ms=1000000 + 1440 * 1000)
        sim.update(current_time)

        assert "day_changed" in events_triggered
        # 跨日但不跨月，不应该有 month_changed
        assert "month_changed" not in events_triggered

    def test_month_changed_event(self):
        """测试跨月事件"""
        creation_time = RealTime(timestamp_ms=1000000)

        # 从第 29 天开始（避免从 0 跳太远）
        sim = TimeSimulator(creation_time)
        sim.state.current_game_time = 29 * 1440  # 第 0 年 1 月 30 日

        events_triggered = []

        def handler(event_type, data):
            events_triggered.append(event_type)

        sim.register_handler(handler)

        # 再推进 1 游戏天（1440 现实秒），跨到第 2 个月
        # 第 0 年 1 月 30 日 → 第 0 年 2 月 1 日
        # 注意：state 已手动设在第 29 天，real_to_game_time 从世界创建起算，
        # 因此这里取第 30 天对应的现实时间，使新游戏时间恰为 30 * 1440
        current_time = RealTime(timestamp_ms=1000000 + 30 * 1440 * 1000)
        sim.update(current_time)

        assert "month_changed" in events_triggered
        assert "day_changed" in events_triggered  # 跨月也会跨日
