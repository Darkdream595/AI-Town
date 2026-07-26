"""
Time Simulation 时间模拟系统

符合游戏时间规范：
- 1 现实秒 = 1 游戏分钟
- 24 游戏小时 = 1 游戏日
- 游戏时间连续推进
"""

from dataclasses import dataclass
from typing import Optional, List, Callable
from foundation import RealTime, GameTime, real_to_game_time
from world import Season, Month, MONTHS, get_festival_on_date


@dataclass
class TimeState:
    """时间状态"""
    current_game_time: int  # 游戏分钟数
    world_creation_time: RealTime  # 世界创建时的现实时间

    def get_current_date(self) -> tuple:
        """获取当前日期（年、月、日、时、分）"""
        from world.calendar import game_minutes_to_date
        return game_minutes_to_date(self.current_game_time)

    def get_current_season(self) -> Season:
        """获取当前季节"""
        _, month_num, _, _, _ = self.get_current_date()

        # 根据月份获取季节
        for month_info in MONTHS.values():
            if month_info.month_number == month_num:
                return month_info.season

        return Season.SPRING

    def is_daytime(self) -> bool:
        """是否白天（6:00-18:00）"""
        _, _, _, hour, _ = self.get_current_date()
        return 6 <= hour < 18


class TimeSimulator:
    """时间模拟器"""

    def __init__(self, world_creation_time: RealTime):
        self.state = TimeState(
            current_game_time=0,
            world_creation_time=world_creation_time
        )
        self.event_handlers: List[Callable] = []

    def update(self, current_real_time: RealTime):
        """更新游戏时间"""
        old_game_time = self.state.current_game_time

        new_game_time_obj = real_to_game_time(current_real_time, self.state.world_creation_time)
        new_game_time = new_game_time_obj.game_minutes

        # 检查是否跨越重要时间点
        self._check_time_events(old_game_time, new_game_time)

        self.state.current_game_time = new_game_time

    def _check_time_events(self, old_time: int, new_time: int):
        """检查时间事件"""
        from world.calendar import game_minutes_to_date

        old_date = game_minutes_to_date(old_time)
        new_date = game_minutes_to_date(new_time)

        # 跨日检查
        if old_date[2] != new_date[2]:  # 日期变化
            self._trigger_event("day_changed", new_date)

        # 跨月检查
        if old_date[1] != new_date[1]:  # 月份变化
            self._trigger_event("month_changed", new_date)

        # 节日检查
        year, month, day, _, _ = new_date
        for month_enum, month_info in MONTHS.items():
            if month_info.month_number == month:
                festival = get_festival_on_date(month_enum, day)
                if festival and old_date[2] != new_date[2]:
                    self._trigger_event("festival_started", festival)

    def _trigger_event(self, event_type: str, data):
        """触发时间事件"""
        for handler in self.event_handlers:
            handler(event_type, data)

    def register_handler(self, handler: Callable):
        """注册事件处理器"""
        self.event_handlers.append(handler)
