"""
有界定价模型（DOC-ECON-008）

- RULE-ECON-029：整数计算、单次 round_half_up、禁止二进制浮点
- RULE-ECON-030：clamp(round(base×s×e×m×d/1000^4), floor, ceiling)；scarcity 是唯一供需输入
- RULE-ECON-031：multiplier 注册范围与 floor/ceiling 界限
- RULE-ECON-032：Quote 固定输入 hash、默认 10 分钟、接受时重校验
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Dict, Optional

from ..foundation import generate_ulid
from .constants import (
    MULTIPLIER_RANGES_Q1000,
    Q1000_NEUTRAL,
    QUOTE_HASH_CONTRACT_ID,
    QUOTE_TTL_GAME_MINUTES,
)


class PricingError(Exception):
    """定价/Quote 失败；code 为稳定 reason code"""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


def round_half_up(numerator: int, denominator: int) -> int:
    """§5：round_half_up(n/d)=floor((2*n+d)/(2*d))，正整数域"""
    if numerator < 0 or denominator <= 0:
        raise PricingError("invalid_currency_amount", "round_half_up domain")
    return (2 * numerator + denominator) // (2 * denominator)


def compute_unit_price(
    base: int,
    scarcity_q1000: int,
    event_q1000: int,
    margin_q1000: int,
    discount_q1000: int,
    floor_copper_feather: int,
    ceiling_copper_feather: int,
) -> int:
    """RULE-ECON-030：单次舍入；供需只由 scarcity 计入一次"""
    multipliers = {
        "scarcity": scarcity_q1000,
        "event": event_q1000,
        "margin": margin_q1000,
        "discount": discount_q1000,
    }
    for name, value in multipliers.items():
        low, high = MULTIPLIER_RANGES_Q1000[name]
        if not (low <= value <= high):
            raise PricingError(
                "price_multiplier_out_of_range", f"{name}={value} outside [{low},{high}]"
            )
    if floor_copper_feather < 1 or ceiling_copper_feather < floor_copper_feather:
        raise PricingError(
            "price_multiplier_out_of_range", "floor>=1 and ceiling>=floor required"
        )
    numerator = base * scarcity_q1000 * event_q1000 * margin_q1000 * discount_q1000
    price = round_half_up(numerator, Q1000_NEUTRAL**4)
    return max(floor_copper_feather, min(ceiling_copper_feather, price))


# -- Canonical JSON v1（RULE-ECON-032 / hash contract） --


def _canon_string(text: str) -> str:
    out = ['"']
    for ch in text:
        code = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif code < 0x20:
            out.append(f"\\u{code:04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def canonical_json(value: object) -> str:
    """Canonical JSON v1：key 按 UTF-8 bytes 升序、无空白、整数最短十进制"""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, bool):
        raise PricingError("quote_canonical_json_invalid", "unreachable bool branch")
    if isinstance(value, int):
        return str(value)  # Python int 即最短十进制，无 -0/前导零
    if isinstance(value, float):
        raise PricingError("quote_canonical_json_invalid", "float forbidden")
    if isinstance(value, str):
        return _canon_string(value)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(canonical_json(item) for item in value) + "]"
    if isinstance(value, dict):
        keys = sorted(value.keys(), key=lambda k: k.encode("utf-8"))
        return "{" + ",".join(
            _canon_string(key) + ":" + canonical_json(value[key]) for key in keys
        ) + "}"
    raise PricingError("quote_canonical_json_invalid", type(value).__name__)


#: §5：preimage 排除字段（签名保留项在 strict v1 本就不允许出现）
_PREIMAGE_EXCLUDED = frozenset({"input_hash", "signature", "signature_algorithm"})


def quote_input_hash(quote: Dict) -> str:
    """对 preimage UTF-8 bytes 计算 SHA-256，wire 值加 sha256: 前缀"""
    preimage = {k: v for k, v in quote.items() if k not in _PREIMAGE_EXCLUDED}
    digest = hashlib.sha256(canonical_json(preimage).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


# -- Strict Quote --

QUOTE_EXACT_FIELDS = frozenset(
    {
        "schema_version", "hash_contract_id", "quote_id", "shop_id",
        "item_definition_id", "quantity", "base_unit_price_copper_feather",
        "scarcity_provenance", "multipliers_q1000", "unit_price_copper_feather",
        "floor_copper_feather", "ceiling_copper_feather", "observed_revision",
        "expires_at_game_time", "input_hash",
    }
)
SCARCITY_PROVENANCE_FIELDS = frozenset(
    {"policy_id", "policy_version", "market_snapshot_hash", "market_snapshot_revision"}
)
MULTIPLIER_FIELDS = frozenset({"scarcity", "event", "margin", "discount"})


def decode_quote(record: Dict) -> Dict:
    """strict contract：额外字段（含独立 demand）必须 Schema 失败"""
    extra = set(record) - QUOTE_EXACT_FIELDS
    if extra:
        raise PricingError(
            "quote_schema_additional_property", f"extra: {sorted(extra)}"
        )
    missing = QUOTE_EXACT_FIELDS - set(record)
    if missing:
        raise PricingError("quote_schema_missing_field", f"missing: {sorted(missing)}")
    if record["hash_contract_id"] != QUOTE_HASH_CONTRACT_ID:
        raise PricingError(
            "quote_schema_additional_property",
            f"unknown hash contract {record['hash_contract_id']}",
        )
    provenance = record["scarcity_provenance"]
    if set(provenance) != SCARCITY_PROVENANCE_FIELDS:
        raise PricingError(
            "scarcity_provenance_invalid", f"fields: {sorted(provenance)}"
        )
    multipliers = record["multipliers_q1000"]
    extra_multipliers = set(multipliers) - MULTIPLIER_FIELDS
    if extra_multipliers:
        # 独立 demand multiplier 即在此拒绝（RULE-ECON-030）
        raise PricingError(
            "quote_schema_additional_property",
            f"multipliers extra: {sorted(extra_multipliers)}",
        )
    if set(multipliers) != MULTIPLIER_FIELDS:
        raise PricingError(
            "quote_schema_missing_field", f"multipliers: {sorted(multipliers)}"
        )
    for name, value in multipliers.items():
        low, high = MULTIPLIER_RANGES_Q1000[name]
        if not (low <= value <= high):
            raise PricingError(
                "price_multiplier_out_of_range", f"{name}={value}"
            )
    for field_name in ("quantity", "base_unit_price_copper_feather", "unit_price_copper_feather"):
        if not isinstance(record[field_name], int) or record[field_name] < 1:
            raise PricingError("invalid_currency_amount", field_name)
    for field_name in ("floor_copper_feather", "ceiling_copper_feather"):
        if not isinstance(record[field_name], int) or record[field_name] < 1:
            raise PricingError("invalid_currency_amount", field_name)
    if record["ceiling_copper_feather"] < record["floor_copper_feather"]:
        raise PricingError("price_multiplier_out_of_range", "ceiling < floor")
    return record


@dataclass(frozen=True)
class DiscountEntitlement:
    """ECON-owned 折扣输入；不 import 关系维度（§5）"""

    entitlement_id: str
    band: str
    discount_q1000: int
    issued_revision: int
    expires_at_game_time: int

    def validate(self, current_game_time: int) -> None:
        low, high = MULTIPLIER_RANGES_Q1000["discount"]
        if not (low <= self.discount_q1000 <= high):
            raise PricingError(
                "discount_entitlement_invalid", f"discount {self.discount_q1000}"
            )
        if current_game_time > self.expires_at_game_time:
            raise PricingError("discount_entitlement_invalid", "entitlement expired")


def make_quote(
    shop_id: str,
    item_definition_id: str,
    quantity: int,
    base_unit_price: int,
    scarcity_q1000: int,
    event_q1000: int,
    margin_q1000: int,
    discount_q1000: int,
    floor_copper_feather: int,
    ceiling_copper_feather: int,
    scarcity_provenance: Dict,
    observed_revision: int,
    current_game_time: int,
    ttl_game_minutes: int = QUOTE_TTL_GAME_MINUTES,
) -> Dict:
    """生成带 input_hash 的 strict Quote（RULE-ECON-032）"""
    unit_price = compute_unit_price(
        base_unit_price, scarcity_q1000, event_q1000, margin_q1000,
        discount_q1000, floor_copper_feather, ceiling_copper_feather,
    )
    quote = {
        "schema_version": 1,
        "hash_contract_id": QUOTE_HASH_CONTRACT_ID,
        "quote_id": generate_ulid(),
        "shop_id": shop_id,
        "item_definition_id": item_definition_id,
        "quantity": quantity,
        "base_unit_price_copper_feather": base_unit_price,
        "scarcity_provenance": dict(scarcity_provenance),
        "multipliers_q1000": {
            "scarcity": scarcity_q1000,
            "event": event_q1000,
            "margin": margin_q1000,
            "discount": discount_q1000,
        },
        "unit_price_copper_feather": unit_price,
        "floor_copper_feather": floor_copper_feather,
        "ceiling_copper_feather": ceiling_copper_feather,
        "observed_revision": observed_revision,
        "expires_at_game_time": current_game_time + ttl_game_minutes,
    }
    quote["input_hash"] = quote_input_hash(quote)
    return decode_quote(quote)


def verify_quote_integrity(quote: Dict) -> None:
    """tamper fixture：任一被覆盖字段都使验签失败"""
    if quote_input_hash(quote) != quote.get("input_hash"):
        raise PricingError("quote_input_changed", "input hash mismatch")


def check_quote_acceptance(
    quote: Dict,
    current_game_time: int,
    maximum_unit_price: Optional[int] = None,
) -> None:
    """RULE-ECON-032：接受时仍重校验；Quote 不是已成交事实"""
    verify_quote_integrity(quote)
    if current_game_time > quote["expires_at_game_time"]:
        raise PricingError("quote_expired", "quote expired")
    if (
        maximum_unit_price is not None
        and quote["unit_price_copper_feather"] > maximum_unit_price
    ):
        raise PricingError(
            "maximum_price_exceeded",
            f"{quote['unit_price_copper_feather']} > {maximum_unit_price}",
        )
