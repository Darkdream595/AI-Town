"""
测试坐标系统

验证 DOC-FOUNDATION-006 和 DOC-MAP-001
"""

import pytest
import sys
from pathlib import Path

# 添加 src 到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from foundation.coordinates import (
    WorldCoordinate,
    LocalCoordinate,
    convert_world_to_local,
    convert_local_to_world,
    TILE_SIZE,
    WU_PRECISION
)


class TestWorldCoordinate:
    """世界坐标测试"""

    def test_create_world_coordinate(self):
        """测试创建世界坐标"""
        wc = WorldCoordinate(x_wu=100.0, y_wu=200.0)
        assert wc.x_wu == 100.0
        assert wc.y_wu == 200.0

    def test_coordinate_precision(self):
        """测试坐标精度量化（1/16 wu）"""
        # RULE-FOUNDATION-042: 精度为 1/16 wu
        wc = WorldCoordinate(x_wu=100.123, y_wu=200.456)

        # 应该量化到最近的 1/16 wu
        assert wc.x_wu == round(100.123 / WU_PRECISION) * WU_PRECISION
        assert wc.y_wu == round(200.456 / WU_PRECISION) * WU_PRECISION

    def test_distance_calculation(self):
        """测试距离计算"""
        wc1 = WorldCoordinate(x_wu=0.0, y_wu=0.0)
        wc2 = WorldCoordinate(x_wu=3.0, y_wu=4.0)

        # 3-4-5 直角三角形
        distance = wc1.distance_to(wc2)
        assert abs(distance - 5.0) < 0.01

    def test_to_tuple(self):
        """测试转换为元组"""
        wc = WorldCoordinate(x_wu=100.0, y_wu=200.0)
        assert wc.to_tuple() == (100.0, 200.0)


class TestLocalCoordinate:
    """本地坐标测试"""

    def test_create_local_coordinate(self):
        """测试创建本地坐标"""
        lc = LocalCoordinate(tile_x=3, tile_y=2, offset_x_wu=16.0, offset_y_wu=8.0)
        assert lc.tile_x == 3
        assert lc.tile_y == 2
        assert lc.offset_x_wu == 16.0
        assert lc.offset_y_wu == 8.0

    def test_offset_range_validation(self):
        """测试偏移量范围验证"""
        # 偏移量必须在 [0, TILE_SIZE) 范围内
        with pytest.raises(ValueError):
            LocalCoordinate(tile_x=0, tile_y=0, offset_x_wu=-1.0)

        with pytest.raises(ValueError):
            LocalCoordinate(tile_x=0, tile_y=0, offset_x_wu=TILE_SIZE)

        with pytest.raises(ValueError):
            LocalCoordinate(tile_x=0, tile_y=0, offset_y_wu=100.0)

    def test_offset_precision(self):
        """测试偏移量精度"""
        lc = LocalCoordinate(tile_x=0, tile_y=0, offset_x_wu=15.123, offset_y_wu=20.456)

        # 应该量化到最近的 1/16 wu
        assert lc.offset_x_wu == round(15.123 / WU_PRECISION) * WU_PRECISION
        assert lc.offset_y_wu == round(20.456 / WU_PRECISION) * WU_PRECISION


class TestCoordinateConversion:
    """坐标转换测试"""

    def test_world_to_local_exact_tile(self):
        """测试世界坐标转本地坐标（整瓦片）"""
        # 96 wu = 3 tiles, 64 wu = 2 tiles
        wc = WorldCoordinate(x_wu=96.0, y_wu=64.0)
        lc = convert_world_to_local(wc)

        assert lc.tile_x == 3
        assert lc.tile_y == 2
        assert lc.offset_x_wu == 0.0
        assert lc.offset_y_wu == 0.0

    def test_world_to_local_with_offset(self):
        """测试世界坐标转本地坐标（带偏移）"""
        # 100 wu = 3 tiles + 4 wu offset
        wc = WorldCoordinate(x_wu=100.0, y_wu=70.0)
        lc = convert_world_to_local(wc)

        assert lc.tile_x == 3
        assert lc.tile_y == 2
        assert lc.offset_x_wu == 4.0
        assert lc.offset_y_wu == 6.0

    def test_local_to_world(self):
        """测试本地坐标转世界坐标"""
        lc = LocalCoordinate(tile_x=3, tile_y=2, offset_x_wu=16.0, offset_y_wu=8.0)
        wc = convert_local_to_world(lc)

        # 3 * 32 + 16 = 112
        # 2 * 32 + 8 = 72
        assert wc.x_wu == 112.0
        assert wc.y_wu == 72.0

    def test_conversion_round_trip(self):
        """测试往返转换的一致性"""
        # 世界坐标 → 本地坐标 → 世界坐标
        original_wc = WorldCoordinate(x_wu=123.5, y_wu=456.75)
        lc = convert_world_to_local(original_wc)
        reconstructed_wc = convert_local_to_world(lc)

        # 由于精度量化，应该非常接近
        assert abs(reconstructed_wc.x_wu - original_wc.x_wu) < 0.1
        assert abs(reconstructed_wc.y_wu - original_wc.y_wu) < 0.1

    def test_tile_size_constant(self):
        """测试 TILE_SIZE 常量（RULE-FOUNDATION-040）"""
        assert TILE_SIZE == 32
