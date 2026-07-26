"""
内容边界验证

符合 DOC-WORLD-010 规范：
- RULE-WORLD-048: 黑暗西幻内容边界
- 非永久死亡机制
- 内容分级系统
"""

from enum import Enum
from dataclasses import dataclass
from typing import List, Optional


class ContentSeverity(str, Enum):
    """内容严重程度"""
    SAFE = "safe"              # 安全内容
    MILD = "mild"              # 温和内容（轻微冲突）
    MODERATE = "moderate"      # 中度内容（战斗、受伤）
    SEVERE = "severe"          # 严重内容（重伤、背叛）
    PROHIBITED = "prohibited"  # 禁止内容


@dataclass(frozen=True)
class ContentBoundary:
    """内容边界规则"""
    category: str
    is_allowed: bool
    max_severity: ContentSeverity
    description: str
    examples: List[str]


# RULE-WORLD-048: 黑暗西幻内容边界
CONTENT_BOUNDARIES = [
    ContentBoundary(
        category="violence",
        is_allowed=True,
        max_severity=ContentSeverity.SEVERE,
        description="允许战斗和非永久性伤害，禁止血腥描述",
        examples=[
            "✓ 战斗中受伤但可以治疗",
            "✓ 战败后昏迷或逃跑",
            "✗ 详细的血腥描述",
            "✗ 永久性死亡（首版）"
        ]
    ),
    ContentBoundary(
        category="death",
        is_allowed=True,
        max_severity=ContentSeverity.MODERATE,
        description="首版仅支持非永久死亡（昏迷、重伤）",
        examples=[
            "✓ 战败后昏迷，可被救治",
            "✓ 重伤需要长时间恢复",
            "✗ 角色永久死亡",
            "✗ 尸体或墓地"
        ]
    ),
    ContentBoundary(
        category="betrayal",
        is_allowed=True,
        max_severity=ContentSeverity.SEVERE,
        description="允许背叛、欺骗等社交冲突",
        examples=[
            "✓ NPC 背叛玩家或其他 NPC",
            "✓ 谎言和欺骗",
            "✓ 派系冲突",
            "✗ 极端残忍的背叛"
        ]
    ),
    ContentBoundary(
        category="capture",
        is_allowed=True,
        max_severity=ContentSeverity.MODERATE,
        description="允许被捕获或囚禁，但有逃脱机制",
        examples=[
            "✓ 被敌对势力捕获",
            "✓ 有机会逃脱或被救",
            "✗ 永久性囚禁",
            "✗ 虐待或折磨"
        ]
    ),
    ContentBoundary(
        category="dark_magic",
        is_allowed=True,
        max_severity=ContentSeverity.MODERATE,
        description="允许黑暗魔法但有道德后果",
        examples=[
            "✓ 黑暗魔法存在但受限",
            "✓ 使用黑暗魔法影响关系和声誉",
            "✗ 极端邪恶的魔法仪式",
            "✗ 灵魂交易或献祭"
        ]
    ),
    ContentBoundary(
        category="romance",
        is_allowed=True,
        max_severity=ContentSeverity.MILD,
        description="允许友谊和轻度浪漫，无露骨内容",
        examples=[
            "✓ 角色间的友谊和信任",
            "✓ 轻度的浪漫关系",
            "✗ 任何露骨或性相关内容",
            "✗ 过度亲密的描述"
        ]
    ),
    ContentBoundary(
        category="substance",
        is_allowed=True,
        max_severity=ContentSeverity.MILD,
        description="允许酒精类饮品，禁止毒品",
        examples=[
            "✓ 旅店供应麦酒",
            "✓ 节日饮酒庆祝",
            "✗ 毒品或成瘾物质",
            "✗ 过度醉酒的负面描述"
        ]
    ),
    ContentBoundary(
        category="horror",
        is_allowed=True,
        max_severity=ContentSeverity.MODERATE,
        description="允许神秘和轻度恐怖氛围",
        examples=[
            "✓ 神秘的森林和未知生物",
            "✓ 幽灵传说和民间故事",
            "✗ 恐怖或惊悚的视觉描述",
            "✗ 心理恐怖"
        ]
    ),
]


def is_content_appropriate(
    category: str,
    severity: ContentSeverity
) -> bool:
    """
    检查内容是否适当

    Args:
        category: 内容类别
        severity: 严重程度

    Returns:
        bool: True 如果内容在边界内
    """
    # 查找对应类别的边界
    for boundary in CONTENT_BOUNDARIES:
        if boundary.category == category:
            if not boundary.is_allowed:
                return False

            # 检查严重程度
            severity_order = [
                ContentSeverity.SAFE,
                ContentSeverity.MILD,
                ContentSeverity.MODERATE,
                ContentSeverity.SEVERE,
                ContentSeverity.PROHIBITED,
            ]

            max_level = severity_order.index(boundary.max_severity)
            content_level = severity_order.index(severity)

            return content_level <= max_level

    # 未定义的类别默认为安全
    return severity == ContentSeverity.SAFE


def validate_content_boundaries(
    content_type: str,
    description: str
) -> tuple[bool, Optional[str]]:
    """
    验证内容是否符合边界规则

    Args:
        content_type: 内容类型（如 "violence", "death"）
        description: 内容描述

    Returns:
        tuple: (是否通过, 违规原因)
    """
    # 检查禁用词
    prohibited_keywords = [
        "gore", "torture", "sexual", "drug", "suicide",
        "血腥", "虐待", "性", "毒品", "自杀",
    ]

    description_lower = description.lower()
    for keyword in prohibited_keywords:
        if keyword in description_lower:
            return (False, f"包含禁用词: {keyword}")

    # 检查内容类型是否在边界内
    found = False
    for boundary in CONTENT_BOUNDARIES:
        if boundary.category == content_type:
            found = True
            if not boundary.is_allowed:
                return (False, f"内容类型 '{content_type}' 被禁止")

    if not found:
        return (False, f"未知的内容类型: {content_type}")

    return (True, None)
