"""
测试内容边界

验证 DOC-WORLD-010 和 RULE-WORLD-048
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from world.content_boundaries import (
    ContentSeverity,
    CONTENT_BOUNDARIES,
    is_content_appropriate,
    validate_content_boundaries,
)


class TestContentBoundaries:
    """内容边界测试"""

    def test_boundaries_defined(self):
        """测试内容边界已定义"""
        assert len(CONTENT_BOUNDARIES) >= 8

        categories = [b.category for b in CONTENT_BOUNDARIES]
        assert "violence" in categories
        assert "death" in categories
        assert "betrayal" in categories
        assert "capture" in categories

    def test_violence_boundaries(self):
        """测试暴力内容边界"""
        # 允许中度暴力
        assert is_content_appropriate("violence", ContentSeverity.MODERATE) is True

        # 允许严重暴力（战斗、重伤）
        assert is_content_appropriate("violence", ContentSeverity.SEVERE) is True

        # 禁止极端暴力
        assert is_content_appropriate("violence", ContentSeverity.PROHIBITED) is False

    def test_death_boundaries(self):
        """测试死亡内容边界（首版非永久死亡）"""
        # 允许轻度（昏迷）
        assert is_content_appropriate("death", ContentSeverity.MILD) is True

        # 允许中度（重伤）
        assert is_content_appropriate("death", ContentSeverity.MODERATE) is True

        # 不允许严重（永久死亡）
        assert is_content_appropriate("death", ContentSeverity.SEVERE) is False

    def test_romance_boundaries(self):
        """测试浪漫内容边界"""
        # 允许轻度浪漫
        assert is_content_appropriate("romance", ContentSeverity.MILD) is True

        # 不允许中度或以上
        assert is_content_appropriate("romance", ContentSeverity.MODERATE) is False

    def test_validate_prohibited_keywords(self):
        """测试禁用词检查"""
        # 包含禁用词
        passed, reason = validate_content_boundaries(
            "violence",
            "This contains gore and blood"
        )
        assert passed is False
        assert "gore" in reason.lower()

        # 中文禁用词
        passed, reason = validate_content_boundaries(
            "violence",
            "这里包含血腥描述"
        )
        assert passed is False

    def test_validate_appropriate_content(self):
        """测试合法内容"""
        passed, reason = validate_content_boundaries(
            "violence",
            "The knight defeated the enemy in battle"
        )
        assert passed is True
        assert reason is None

        passed, reason = validate_content_boundaries(
            "betrayal",
            "The merchant deceived the player"
        )
        assert passed is True

    def test_validate_unknown_category(self):
        """测试未知类别"""
        passed, reason = validate_content_boundaries(
            "unknown_category",
            "Some content"
        )
        assert passed is False
        assert "未知" in reason or "unknown" in reason.lower()
