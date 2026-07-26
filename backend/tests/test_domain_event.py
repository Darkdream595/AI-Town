"""
测试 Domain Event

验证 DOC-FOUNDATION-004 和 RULE-FOUNDATION-022
"""

import pytest
import sys
from pathlib import Path

# 添加 src 到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from foundation.domain_event import DomainEvent
from foundation.time_conversion import RealTime
from foundation.id_generator import is_valid_ulid


from dataclasses import dataclass


@dataclass(frozen=True)
class ResidentMovedEvent(DomainEvent):
    """测试用的具体事件类"""
    resident_id: str = ""
    from_x: float = 0.0
    from_y: float = 0.0
    to_x: float = 0.0
    to_y: float = 0.0


class TestDomainEvent:
    """Domain Event 测试"""

    def test_create_domain_event(self):
        """测试创建领域事件"""
        event = ResidentMovedEvent(
            world_id="test_world",
            revision=0,
            resident_id="resident_123",
            from_x=0.0,
            from_y=0.0,
            to_x=10.0,
            to_y=20.0
        )

        assert event.world_id == "test_world"
        assert event.revision == 0
        assert is_valid_ulid(event.event_id)

    def test_event_immutable(self):
        """测试事件不可变性"""
        event = ResidentMovedEvent(
            world_id="test_world",
            revision=0,
            resident_id="resident_123",
            from_x=0.0,
            from_y=0.0,
            to_x=10.0,
            to_y=20.0
        )

        # 不可变对象不能修改
        with pytest.raises(Exception):
            event.revision = 1

    def test_event_revision_validation(self):
        """测试 revision 验证"""
        with pytest.raises(ValueError):
            ResidentMovedEvent(
                world_id="test_world",
                revision=-1,  # 非法：负数
                resident_id="resident_123",
                from_x=0.0,
                from_y=0.0,
                to_x=10.0,
                to_y=20.0
            )

    def test_event_serialization(self):
        """测试事件序列化"""
        event = ResidentMovedEvent(
            world_id="test_world",
            revision=0,
            resident_id="resident_123",
            from_x=0.0,
            from_y=0.0,
            to_x=10.0,
            to_y=20.0
        )

        data = event.to_dict()

        assert data["world_id"] == "test_world"
        assert data["revision"] == 0
        assert data["event_type"] == "ResidentMovedEvent"
        assert is_valid_ulid(data["event_id"])
