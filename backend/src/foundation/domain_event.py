"""
Domain Event 基类

符合 DOC-FOUNDATION-004 和 DOC-FOUNDATION-005 规范：
- 事件溯源（Event Sourcing）
- 不可变事件记录
- RULE-FOUNDATION-022: 每个事件有唯一的 event_id 和 revision
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from .id_generator import generate_ulid
from .time_conversion import RealTime


@dataclass(frozen=True)
class DomainEvent:
    """
    领域事件基类

    所有领域事件必须继承此类
    - 不可变（frozen=True）
    - 唯一标识（event_id）
    - 时间戳（occurred_at）
    - 版本号（revision）
    """

    # 必需字段（无默认值）
    world_id: str
    revision: int  # RULE-FOUNDATION-022: Revision 从 0 开始单调递增

    # 可选字段（有默认值）
    event_id: str = field(default_factory=generate_ulid)
    event_type: str = field(init=False)  # 由子类设置
    occurred_at: RealTime = field(default_factory=RealTime.now)
    caused_by_command_id: Optional[str] = None

    def __post_init__(self):
        """验证事件完整性"""
        if self.revision < 0:
            raise ValueError(f"revision must be non-negative, got {self.revision}")

        # 设置事件类型（子类名）
        object.__setattr__(self, 'event_type', self.__class__.__name__)

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "occurred_at": self.occurred_at.to_iso(),
            "world_id": self.world_id,
            "revision": self.revision,
            "caused_by_command_id": self.caused_by_command_id,
        }
