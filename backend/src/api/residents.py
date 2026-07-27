"""
居民 REST API 接口

提供居民数据的 HTTP 接口
"""

from fastapi import APIRouter, HTTPException
from typing import List
from pydantic import BaseModel

from ..residents.service import get_resident_service
from ..residents.resident_model import Resident

router = APIRouter(prefix="/api/residents", tags=["residents"])


# ============================================================================
# Response Models
# ============================================================================

class ResidentSummary(BaseModel):
    """居民摘要（用于列表展示）"""
    resident_id: str
    name: str
    race: str
    profession: str | None
    current_scene_id: str
    health_status: str
    current_hp: int
    max_hp: int

    @classmethod
    def from_resident(cls, resident: Resident) -> "ResidentSummary":
        return cls(
            resident_id=resident.resident_id,
            name=resident.name,
            race=resident.race.value,
            profession=resident.profession.value if resident.profession else None,
            current_scene_id=resident.current_scene_id,
            health_status=resident.health.status.value,
            current_hp=resident.health.current_hp,
            max_hp=resident.health.max_hp,
        )


class ResidentDetail(BaseModel):
    """居民详情（包含完整信息）"""
    resident_id: str
    name: str
    race: str
    gender: str
    age_years: int
    profession: str | None
    current_scene_id: str

    # 外观
    sprite_id: str
    skin_tone: str
    hair_color: str

    # 健康
    health_status: str
    current_hp: int
    max_hp: int

    # 需求（简化显示）
    hunger: int
    energy: int
    social: int

    # 情绪
    mood: int

    @classmethod
    def from_resident(cls, resident: Resident) -> "ResidentDetail":
        return cls(
            resident_id=resident.resident_id,
            name=resident.name,
            race=resident.race.value,
            gender=resident.gender.value,
            age_years=resident.age.years,
            profession=resident.profession.value if resident.profession else None,
            current_scene_id=resident.current_scene_id,
            sprite_id=resident.appearance.sprite_id,
            skin_tone=resident.appearance.skin_tone,
            hair_color=resident.appearance.hair_color,
            health_status=resident.health.status.value,
            current_hp=resident.health.current_hp,
            max_hp=resident.health.max_hp,
            hunger=resident.needs.get_need("hunger").value if hasattr(resident.needs, 'get_need') else 80,
            energy=resident.needs.get_need("energy").value if hasattr(resident.needs, 'get_need') else 80,
            social=resident.needs.get_need("social").value if hasattr(resident.needs, 'get_need') else 80,
            mood=resident.emotions.mood,
        )


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("/", response_model=List[ResidentSummary])
async def list_residents():
    """
    获取所有居民列表（摘要）

    返回所有居民的基本信息
    """
    service = get_resident_service()
    residents = service.get_all_residents()
    return [ResidentSummary.from_resident(r) for r in residents]


@router.get("/{resident_id}", response_model=ResidentDetail)
async def get_resident(resident_id: str):
    """
    获取单个居民详情

    Args:
        resident_id: 居民ID

    Returns:
        居民详细信息

    Raises:
        404: 居民不存在
    """
    service = get_resident_service()
    resident = service.get_resident_by_id(resident_id)

    if not resident:
        raise HTTPException(status_code=404, detail=f"Resident {resident_id} not found")

    return ResidentDetail.from_resident(resident)


@router.get("/count", response_model=dict)
async def get_resident_count():
    """
    获取居民总数

    Returns:
        {"count": int}
    """
    service = get_resident_service()
    return {"count": service.get_resident_count()}
