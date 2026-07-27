"""
TEST-PLAYER-025..028：玩家居民模式权限（DOC-PLAYER-007）

- TEST-PLAYER-025：resident capability matrix 与 AI parity
- TEST-PLAYER-026：role/ownership/consent stale revocation
- TEST-PLAYER-027：Mayor/Admin union confusion 拒绝
- TEST-PLAYER-028：secret enumeration、error/log 最小披露
"""

import pytest

from src.player import (
    CapabilityProjection,
    PermissionDenial,
    PlayerMode,
    ResidentPermissionService,
)
from src.player.permissions import UNIFORM_ENTRY_DENIAL_MESSAGE

BINDING = "01K1BNDG000000000000000001"
RESIDENT = "01K1RSDT000000000000000001"


def _service():
    return ResidentPermissionService()


def _projection(service, **kwargs):
    defaults = dict(
        binding_id=BINDING,
        resident_id=RESIDENT,
        mode=PlayerMode.RESIDENT_ACTIVE,
        revision=240,
    )
    defaults.update(kwargs)
    return service.build_projection(**defaults)


class TestCapabilityMatrix:
    """TEST-PLAYER-025"""

    def test_resident_mode_default_capabilities(self):
        projection = _projection(_service())
        for cap in ("resident.move", "resident.talk", "resident.trade", "resident.work"):
            assert cap in projection.capability_ids
        # RULE-PLAYER-031：居民模式不含 mayor/admin 能力
        assert not any(c.startswith(("mayor.", "admin.")) for c in projection.capability_ids)

    def test_unhealthy_resident_loses_labor_capabilities(self):
        projection = _projection(_service(), healthy=False)
        assert "resident.work" not in projection.capability_ids
        assert "resident.combat" not in projection.capability_ids
        assert "health" in projection.restriction_codes
        # 移动/交谈等基本能力保留
        assert "resident.move" in projection.capability_ids

    def test_projection_contains_no_private_values(self):
        """§5.1：不含余额、Inventory、secret、relationship raw values"""
        projection = _projection(_service())
        for forbidden in ("balance", "inventory", "secrets", "relationship_values"):
            assert not hasattr(projection, forbidden)


class TestStaleRevocation:
    """TEST-PLAYER-026"""

    def test_stale_projection_rejected(self):
        service = _service()
        projection = _projection(service, revision=240)
        # §7：projection 最多有效到生成时 Revision
        denial = service.check_capability(projection, "resident.move", current_revision=241)
        assert denial is not None
        assert denial.deny_code == "PLAYER_CAPABILITY_PROJECTION_STALE"
        assert denial.retryable is True

    def test_current_revision_passes_gate(self):
        service = _service()
        projection = _projection(service, revision=240)
        assert service.check_capability(projection, "resident.move", 240) is None

    def test_projection_expiry_invariant(self):
        with pytest.raises(ValueError):
            CapabilityProjection(
                binding_id=BINDING,
                resident_id=RESIDENT,
                mode=PlayerMode.RESIDENT_ACTIVE,
                revision=240,
                capability_ids=(),
                expires_after_revision=239,
            )


class TestUnionConfusion:
    """TEST-PLAYER-027"""

    @pytest.mark.parametrize(
        "capability",
        ["mayor.budget.propose", "admin.resource.grant",
         "governance.public_budget", "governance.tax_rate"],
    )
    def test_governance_capabilities_denied_in_resident_mode(self, capability):
        service = _service()
        projection = _projection(service)
        denial = service.check_capability(projection, capability, 240)
        assert denial is not None
        assert denial.deny_code == "PLAYER_GOVERNANCE_REQUIRES_MAYOR_MODE"
        assert denial.retryable is False


class TestMinimalDisclosure:
    """TEST-PLAYER-028"""

    def test_secret_target_uses_uniform_message(self):
        """§9：secret 门失败统一显示「无法进入」，不泄露 owner 或内部事件"""
        service = _service()
        projection = _projection(service)
        denial = service.check_capability(
            projection, "resident.enter_building", 240, target_is_secret=True
        )
        # capability 存在于默认集合，所以这里不会命中；改为不存在的能力 + secret 目标
        denial = service.check_capability(
            projection, "resident.enter_secret_vault", 240, target_is_secret=True
        )
        assert denial is not None
        assert denial.deny_code == "not_permitted"
        assert denial.safe_player_message == UNIFORM_ENTRY_DENIAL_MESSAGE

    def test_secret_access_denied_with_safe_message(self):
        denial = ResidentPermissionService.check_secret_access()
        assert denial.deny_code == "not_permitted"
        assert "秘密" not in denial.safe_player_message
        assert "secret" not in denial.safe_player_message.lower()

    def test_denial_is_stable_no_fallback(self):
        """RULE-PLAYER-035：拒绝是稳定结果，无近似成功 fallback"""
        denial = PermissionDenial(
            deny_code="not_permitted", safe_player_message="无法执行", retryable=False
        )
        ResidentPermissionService.assert_no_near_success_fallback(denial, committed=False)
        with pytest.raises(AssertionError):
            ResidentPermissionService.assert_no_near_success_fallback(denial, committed=True)
