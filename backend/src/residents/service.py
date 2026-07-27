"""
居民服务层

提供居民的业务逻辑和管理功能
"""

from typing import List, Optional, Dict
from ..foundation import generate_ulid
from .resident_model import Resident
from .factory import ResidentFactory


class ResidentService:
    """居民服务"""

    def __init__(self):
        self._residents: Dict[str, Resident] = {}
        self._initialize_default_residents()

    def _initialize_default_residents(self):
        """初始化默认的10个居民"""
        initial_residents = ResidentFactory.create_all_initial_residents()
        for key, resident in initial_residents.items():
            self._residents[resident.resident_id] = resident
            print(f"[ResidentService] 初始化居民: {resident.name} ({key})")

    def get_all_residents(self) -> List[Resident]:
        """获取所有居民"""
        return list(self._residents.values())

    def get_resident_by_id(self, resident_id: str) -> Optional[Resident]:
        """根据ID获取居民"""
        return self._residents.get(resident_id)

    def create_resident(self, resident: Resident) -> Resident:
        """创建新居民"""
        if not resident.resident_id:
            resident.resident_id = generate_ulid()

        self._residents[resident.resident_id] = resident
        return resident

    def update_resident(self, resident_id: str, resident: Resident) -> Optional[Resident]:
        """更新居民"""
        if resident_id not in self._residents:
            return None

        self._residents[resident_id] = resident
        return resident

    def delete_resident(self, resident_id: str) -> bool:
        """删除居民"""
        if resident_id in self._residents:
            del self._residents[resident_id]
            return True
        return False

    def update_all_residents(self, current_game_time: int):
        """更新所有居民状态（需求衰减等）"""
        for resident in self._residents.values():
            resident.update(current_game_time)

    def get_resident_count(self) -> int:
        """获取居民总数"""
        return len(self._residents)


# 全局单例
_resident_service: Optional[ResidentService] = None


def get_resident_service() -> ResidentService:
    """获取居民服务实例"""
    global _resident_service
    if _resident_service is None:
        _resident_service = ResidentService()
    return _resident_service
