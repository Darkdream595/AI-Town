"""
TEST-ECON-029..032：有界定价模型（DOC-ECON-008）

- TEST-ECON-029：golden 公式 = 135 且供需只经 scarcity 计一次
- TEST-ECON-030：multiplier 边界/clamp 与独立 demand 字段拒绝
- TEST-ECON-031：golden preimage/hash 逐字节、tamper、过期与最高价
- TEST-ECON-032：本地信息边界与 entitlement 校验
"""

import pytest

from src.economy import (
    DiscountEntitlement,
    PricingError,
    canonical_json,
    check_quote_acceptance,
    compute_unit_price,
    decode_quote,
    make_quote,
    quote_input_hash,
    round_half_up,
    verify_quote_integrity,
)

GOLDEN_HASH = "sha256:18aa059a94c920a5f03c3f0ac5c489941b643143be6f4c8a6e27c59f52b5fee2"

GOLDEN_PREIMAGE = (
    '{"base_unit_price_copper_feather":100,"ceiling_copper_feather":300,'
    '"expires_at_game_time":610,"floor_copper_feather":50,'
    '"hash_contract_id":"quote_input_hash.sha256_canonical_json.v1",'
    '"item_definition_id":"item.potion.healing_small",'
    '"multipliers_q1000":{"discount":900,"event":1000,"margin":1250,"scarcity":1200},'
    '"observed_revision":200,"quantity":2,'
    '"quote_id":"01K1AB2CD3EF4GH5JK6MNP7QRS",'
    '"scarcity_provenance":{'
    '"market_snapshot_hash":"sha256:30cb762b7a104a553fbcf801f248c929366b55958dfab609f012ca351ddc4c49",'
    '"market_snapshot_revision":200,"policy_id":"scarcity_policy.local_market.v1",'
    '"policy_version":1},"schema_version":1,'
    '"shop_id":"01K1AB2CD3EF4GH5JK6MNP7QRT","unit_price_copper_feather":135}'
)


def _golden_quote():
    return {
        "schema_version": 1,
        "hash_contract_id": "quote_input_hash.sha256_canonical_json.v1",
        "quote_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
        "shop_id": "01K1AB2CD3EF4GH5JK6MNP7QRT",
        "item_definition_id": "item.potion.healing_small",
        "quantity": 2,
        "base_unit_price_copper_feather": 100,
        "scarcity_provenance": {
            "policy_id": "scarcity_policy.local_market.v1",
            "policy_version": 1,
            "market_snapshot_hash": "sha256:30cb762b7a104a553fbcf801f248c929366b55958dfab609f012ca351ddc4c49",
            "market_snapshot_revision": 200,
        },
        "multipliers_q1000": {"scarcity": 1200, "event": 1000, "margin": 1250, "discount": 900},
        "unit_price_copper_feather": 135,
        "floor_copper_feather": 50,
        "ceiling_copper_feather": 300,
        "observed_revision": 200,
        "expires_at_game_time": 610,
        "input_hash": GOLDEN_HASH,
    }


def _provenance():
    return {
        "policy_id": "scarcity_policy.local_market.v1",
        "policy_version": 1,
        "market_snapshot_hash": "sha256:30cb762b7a104a553fbcf801f248c929366b55958dfab609f012ca351ddc4c49",
        "market_snapshot_revision": 200,
    }


class TestGoldenFormula:
    """TEST-ECON-029"""

    def test_golden_unit_price_135(self):
        assert compute_unit_price(100, 1200, 1000, 1250, 900, 50, 300) == 135

    def test_single_rounding_no_float(self):
        # 分数情形：100 × 1005 / 1000 = 100.5 → round_half_up = 101
        assert round_half_up(100 * 1005, 1000) == 101
        assert compute_unit_price(100, 1005, 1000, 1000, 1000, 1, 10**9) == 101
        # round_half_up(x.5) 向上，不向偶
        assert round_half_up(1, 2) == 1
        assert round_half_up(3, 2) == 2

    def test_scarcity_is_only_demand_input(self):
        # 同样的 base/floor/ceiling，供需变化只能由 scarcity 改变价格
        base_price = compute_unit_price(100, 1000, 1000, 1000, 1000, 1, 10**9)
        scarce_price = compute_unit_price(100, 1500, 1000, 1000, 1000, 1, 10**9)
        assert base_price == 100
        assert scarce_price == 150


class TestPriceBoundsAndStrictMultipliers:
    """TEST-ECON-030"""

    @pytest.mark.parametrize(
        "scarcity,event,margin,discount",
        [
            (700, 500, 1000, 700),    # 全低下界
            (2000, 2000, 1600, 1000),  # 全高上界
            (700, 2000, 1000, 1000),
            (2000, 500, 1600, 700),
        ],
    )
    def test_registered_edges_accepted_and_clamped(self, scarcity, event, margin, discount):
        price = compute_unit_price(100, scarcity, event, margin, discount, 50, 300)
        assert 50 <= price <= 300

    @pytest.mark.parametrize(
        "scarcity,event,margin,discount",
        [
            (699, 1000, 1000, 1000),
            (2001, 1000, 1000, 1000),
            (1000, 499, 1000, 1000),
            (1000, 2001, 1000, 1000),
            (1000, 1000, 999, 1000),
            (1000, 1000, 1601, 1000),
            (1000, 1000, 1000, 699),
            (1000, 1000, 1000, 1001),
        ],
    )
    def test_out_of_range_rejected(self, scarcity, event, margin, discount):
        with pytest.raises(PricingError) as excinfo:
            compute_unit_price(100, scarcity, event, margin, discount, 50, 300)
        assert excinfo.value.code == "price_multiplier_out_of_range"

    def test_floor_ceiling_validated(self):
        with pytest.raises(PricingError):
            compute_unit_price(100, 1000, 1000, 1000, 1000, 0, 300)
        with pytest.raises(PricingError):
            compute_unit_price(100, 1000, 1000, 1000, 1000, 300, 50)

    def test_demand_multiplier_field_rejected(self):
        quote = _golden_quote()
        quote["multipliers_q1000"]["demand"] = 1100
        with pytest.raises(PricingError) as excinfo:
            decode_quote(quote)
        assert excinfo.value.code == "quote_schema_additional_property"

    def test_quote_extra_top_level_field_rejected(self):
        quote = _golden_quote()
        quote["demand_forecast"] = 1100
        with pytest.raises(PricingError) as excinfo:
            decode_quote(quote)
        assert excinfo.value.code == "quote_schema_additional_property"


class TestQuoteHashExpiryAndLimit:
    """TEST-ECON-031"""

    def test_canonical_preimage_byte_exact(self):
        quote = _golden_quote()
        preimage = {k: v for k, v in quote.items() if k != "input_hash"}
        assert canonical_json(preimage) == GOLDEN_PREIMAGE

    def test_golden_hash(self):
        assert quote_input_hash(_golden_quote()) == GOLDEN_HASH

    def test_decode_golden_quote(self):
        assert decode_quote(_golden_quote())["unit_price_copper_feather"] == 135

    def test_tamper_quantity_invalidates_hash(self):
        quote = _golden_quote()
        quote["quantity"] = 3  # 篡改但保留旧 hash
        with pytest.raises(PricingError) as excinfo:
            verify_quote_integrity(quote)
        assert excinfo.value.code == "quote_input_changed"

    def test_expired_quote_rejected(self):
        quote = _golden_quote()  # expires_at 610
        check_quote_acceptance(quote, current_game_time=610)
        with pytest.raises(PricingError) as excinfo:
            check_quote_acceptance(quote, current_game_time=611)
        assert excinfo.value.code == "quote_expired"

    def test_maximum_price_enforced(self):
        quote = _golden_quote()  # unit 135
        check_quote_acceptance(quote, current_game_time=600, maximum_unit_price=135)
        with pytest.raises(PricingError) as excinfo:
            check_quote_acceptance(quote, current_game_time=600, maximum_unit_price=134)
        assert excinfo.value.code == "maximum_price_exceeded"

    def test_make_quote_ttl_and_hash(self):
        quote = make_quote(
            shop_id="shop.fixture.1",
            item_definition_id="item.potion.healing_small",
            quantity=1,
            base_unit_price=100,
            scarcity_q1000=1200,
            event_q1000=1000,
            margin_q1000=1250,
            discount_q1000=900,
            floor_copper_feather=50,
            ceiling_copper_feather=300,
            scarcity_provenance=_provenance(),
            observed_revision=200,
            current_game_time=600,
        )
        assert quote["unit_price_copper_feather"] == 135
        assert quote["expires_at_game_time"] == 610
        verify_quote_integrity(quote)


class TestLocalInformation:
    """TEST-ECON-032"""

    def test_entitlement_discount_applied(self):
        entitlement = DiscountEntitlement(
            entitlement_id="ent.fixture.1",
            band="friend",
            discount_q1000=900,
            issued_revision=10,
            expires_at_game_time=1000,
        )
        entitlement.validate(current_game_time=500)
        with_discount = compute_unit_price(100, 1000, 1000, 1000, entitlement.discount_q1000, 1, 10**9)
        without_discount = compute_unit_price(100, 1000, 1000, 1000, 1000, 1, 10**9)
        assert with_discount == 90
        assert without_discount == 100

    def test_entitlement_expired_or_out_of_range(self):
        expired = DiscountEntitlement("ent.1", "friend", 900, 10, 1000)
        with pytest.raises(PricingError) as excinfo:
            expired.validate(current_game_time=1001)
        assert excinfo.value.code == "discount_entitlement_invalid"
        out_of_range = DiscountEntitlement("ent.2", "vip", 500, 10, 1000)
        with pytest.raises(PricingError) as excinfo:
            out_of_range.validate(current_game_time=500)
        assert excinfo.value.code == "discount_entitlement_invalid"

    def test_quote_carries_no_private_fields(self):
        quote = make_quote(
            shop_id="shop.fixture.1",
            item_definition_id="item.potion.healing_small",
            quantity=1,
            base_unit_price=100,
            scarcity_q1000=1000,
            event_q1000=1000,
            margin_q1000=1000,
            discount_q1000=900,
            floor_copper_feather=50,
            ceiling_copper_feather=300,
            scarcity_provenance=_provenance(),
            observed_revision=200,
            current_game_time=600,
        )
        private_markers = ("relationship", "memory", "owner", "belief", "stock", "staff")
        for key in quote:
            assert not any(marker in key for marker in private_markers)
        # provenance 只有策略与快照引用，无隐藏库存
        assert set(quote["scarcity_provenance"]) == {
            "policy_id", "policy_version", "market_snapshot_hash", "market_snapshot_revision",
        }
