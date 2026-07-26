"""
测试时间转换

验证 DOC-FOUNDATION-006 和 RULE-FOUNDATION-048
"""

import pytest
import sys
from pathlib import Path
from datetime import datetime, timezone

# 添加 src 到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from foundation.time_conversion import (
    RealTime,
    GameTime,
    real_to_game_time,
    game_to_real_time,
    GAME_MINUTES_PER_REAL_SECOND,
    REAL_MS_PER_GAME_MINUTE
)


class TestRealTime:
    """现实时间测试"""

    def test_create_real_time(self):
        """测试创建现实时间"""
        rt = RealTime(timestamp_ms=1000000)
        assert rt.timestamp_ms == 1000000

    def test_real_time_now(self):
        """测试获取当前时间"""
        rt = RealTime.now()
        assert rt.timestamp_ms > 0

    def test_real_time_iso_format(self):
        """测试 ISO 8601 序列化"""
        rt = RealTime(timestamp_ms=1609459200000)
        iso_str = rt.to_iso()
        assert iso_str.endswith('Z')
        assert '2021-01-01' in iso_str


class TestGameTime:
    """游戏时间测试"""

    def test_create_game_time(self):
        """测试创建游戏时间"""
        gt = GameTime(game_minutes=120)
        assert gt.game_minutes == 120

    def test_to_hours_minutes(self):
        """测试转换为小时和分钟"""
        gt = GameTime(game_minutes=125)
        hours, minutes = gt.to_hours_minutes()
        assert hours == 2
        assert minutes == 5


class TestTimeConversion:
    """时间转换测试"""

    def test_real_to_game_time_basic(self):
        """测试现实时间转游戏时间"""
        creation = RealTime(timestamp_ms=1000000)
        current = RealTime(timestamp_ms=1060000)
        gt = real_to_game_time(current, creation)
        assert gt.game_minutes == 60

    def test_game_to_real_time_basic(self):
        """测试游戏时间转现实时间"""
        creation = RealTime(timestamp_ms=1000000)
        game_time = GameTime(game_minutes=60)
        rt = game_to_real_time(game_time, creation)
        assert rt.timestamp_ms == 1060000
