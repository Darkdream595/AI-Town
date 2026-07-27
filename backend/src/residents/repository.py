"""
居民仓储接口

符合 DOC-RESIDENT-001 规范
提供居民聚合根的 CRUD 操作
"""

from typing import Dict, List, Optional
from abc import ABC, abstractmethod

from .models import ResidentAggregate, ResidentSummaryProjection


class ResidentRepository(ABC):
    """
    居民仓储抽象接口

    定义居民数据的存储和检索操作
    """

    @abstractmethod
    def save(self, resident: ResidentAggregate) -> None:
        """
        保存居民聚合根

        Args:
            resident: 居民聚合根

        Raises:
            ValueError: 如果数据验证失败
        """
        pass

    @abstractmethod
    def get_by_id(self, resident_id: str) -> Optional[ResidentAggregate]:
        """
        根据 ID 获取居民

        Args:
            resident_id: 居民ID

        Returns:
            居民聚合根，如果不存在返回 None
        """
        pass

    @abstractmethod
    def get_by_key(self, resident_key: str) -> Optional[ResidentAggregate]:
        """
        根据 Key 获取居民

        Args:
            resident_key: 居民稳定 Catalog ID

        Returns:
            居民聚合根，如果不存在返回 None
        """
        pass

    @abstractmethod
    def list_all(self) -> List[ResidentAggregate]:
        """
        获取所有居民列表

        Returns:
            居民聚合根列表
        """
        pass

    @abstractmethod
    def list_summaries(self) -> List[ResidentSummaryProjection]:
        """
        获取所有居民摘要列表

        Returns:
            居民摘要列表
        """
        pass

    @abstractmethod
    def delete(self, resident_id: str) -> bool:
        """
        删除居民

        Args:
            resident_id: 居民ID

        Returns:
            是否删除成功
        """
        pass

    @abstractmethod
    def exists(self, resident_id: str) -> bool:
        """
        检查居民是否存在

        Args:
            resident_id: 居民ID

        Returns:
            是否存在
        """
        pass

    @abstractmethod
    def count(self) -> int:
        """
        获取居民总数

        Returns:
            居民数量
        """
        pass


class InMemoryResidentRepository(ResidentRepository):
    """
    内存居民仓储实现

    用于开发和测试
    数据存储在内存中，不持久化
    """

    def __init__(self):
        self._residents: Dict[str, ResidentAggregate] = {}
        self._residents_by_key: Dict[str, str] = {}  # resident_key -> resident_id 映射

    def save(self, resident: ResidentAggregate) -> None:
        """保存居民到内存"""
        # 验证数据（Pydantic 自动验证）
        self._residents[resident.resident_id] = resident
        self._residents_by_key[resident.resident_key] = resident.resident_id

    def get_by_id(self, resident_id: str) -> Optional[ResidentAggregate]:
        """根据 ID 获取居民"""
        return self._residents.get(resident_id)

    def get_by_key(self, resident_key: str) -> Optional[ResidentAggregate]:
        """根据 Key 获取居民"""
        resident_id = self._residents_by_key.get(resident_key)
        if resident_id:
            return self._residents.get(resident_id)
        return None

    def list_all(self) -> List[ResidentAggregate]:
        """获取所有居民"""
        return list(self._residents.values())

    def list_summaries(self) -> List[ResidentSummaryProjection]:
        """获取所有居民摘要"""
        return [
            ResidentSummaryProjection.from_aggregate(resident)
            for resident in self._residents.values()
        ]

    def delete(self, resident_id: str) -> bool:
        """删除居民"""
        resident = self._residents.get(resident_id)
        if resident:
            del self._residents[resident_id]
            del self._residents_by_key[resident.resident_key]
            return True
        return False

    def exists(self, resident_id: str) -> bool:
        """检查居民是否存在"""
        return resident_id in self._residents

    def count(self) -> int:
        """获取居民总数"""
        return len(self._residents)

    def clear(self) -> None:
        """清空所有居民（测试用）"""
        self._residents.clear()
        self._residents_by_key.clear()


# 全局仓储实例（单例模式）
_repository: Optional[ResidentRepository] = None


def get_repository() -> ResidentRepository:
    """
    获取全局居民仓储实例

    Returns:
        居民仓储实例
    """
    global _repository
    if _repository is None:
        _repository = InMemoryResidentRepository()
    return _repository


def set_repository(repository: ResidentRepository) -> None:
    """
    设置全局居民仓储实例（用于测试或切换实现）

    Args:
        repository: 居民仓储实例
    """
    global _repository
    _repository = repository
