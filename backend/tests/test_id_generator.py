"""
测试 ULID 生成器

验证 DOC-FOUNDATION-006 和 RULE-FOUNDATION-033
"""

import pytest
import sys
from pathlib import Path

# 添加 src 到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from foundation.id_generator import (
    generate_ulid,
    is_valid_ulid,
    ulid_to_timestamp,
    ULID_PATTERN
)


class TestULIDGenerator:
    """ULID 生成器测试"""

    def test_generate_ulid_format(self):
        """测试生成的 ULID 格式正确"""
        ulid = generate_ulid()

        # 长度必须是 26
        assert len(ulid) == 26

        # 必须匹配 Crockford Base32 模式
        assert ULID_PATTERN.match(ulid) is not None

    def test_generate_ulid_uniqueness(self):
        """测试 ULID 唯一性"""
        ulids = set()
        for _ in range(1000):
            ulid = generate_ulid()
            assert ulid not in ulids, "ULID 应该是唯一的"
            ulids.add(ulid)

    def test_is_valid_ulid_valid_cases(self):
        """测试合法的 ULID"""
        # 生成的 ULID 应该是合法的
        ulid = generate_ulid()
        assert is_valid_ulid(ulid) is True

        # 标准 ULID 格式
        assert is_valid_ulid("01HQVX5W6T9YZBQXRM8NPSJ9K7") is True

    def test_is_valid_ulid_invalid_cases(self):
        """测试非法的 ULID"""
        # 长度不对
        assert is_valid_ulid("123") is False

        # 包含非法字符 U（Crockford Base32 排除 I/L/O/U）
        assert is_valid_ulid("01HQVX5W6T9YZBQXRM8NPSJ9U7") is False

        # 包含非法字符 I
        assert is_valid_ulid("01HQVX5W6T9YZBQXRM8NPSJ9I7") is False

        # 包含小写字母
        assert is_valid_ulid("01hqvx5w6t9yzbqxrm8npsj9k7") is False

        # 空字符串
        assert is_valid_ulid("") is False

        # 非字符串类型
        assert is_valid_ulid(123) is False
        assert is_valid_ulid(None) is False

    def test_ulid_to_timestamp(self):
        """测试从 ULID 提取时间戳"""
        ulid = generate_ulid()
        timestamp = ulid_to_timestamp(ulid)

        # 时间戳应该是正整数
        assert isinstance(timestamp, int)
        assert timestamp > 0

        # 时间戳应该接近当前时间（毫秒）
        import time
        current_ms = int(time.time() * 1000)
        assert abs(timestamp - current_ms) < 1000  # 误差小于 1 秒

    def test_ulid_to_timestamp_invalid(self):
        """测试非法 ULID 提取时间戳"""
        with pytest.raises(ValueError):
            ulid_to_timestamp("invalid-ulid")

    def test_ulid_ordering(self):
        """测试 ULID 按时间排序"""
        import time

        ulid1 = generate_ulid()
        time.sleep(0.002)  # 等待 2ms
        ulid2 = generate_ulid()

        # ULID 应该按时间递增
        assert ulid1 < ulid2
