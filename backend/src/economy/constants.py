"""
经济域共享常量（DOC-ECON-001..012 的数值与封闭枚举真源）
"""

from enum import Enum

#: RULE-ECON-001：int64 上下界
INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1

#: DOC-ECON-001 §3：1 银冠 = 100 铜羽（仅显示层）
COPPER_PER_SILVER = 100

#: RULE-ECON-009：首版单班最长游戏分钟
MAX_SHIFT_MINUTES = 720

#: DOC-ECON-003 §9：单次 credit 最大游戏分钟
MAX_CREDIT_INTERVAL_MINUTES = 1440

#: RULE-ECON-035：供需滚动窗口与 bucket
MARKET_WINDOW_MINUTES = 1440
MARKET_BUCKET_MINUTES = 60
MARKET_BUCKET_COUNT = MARKET_WINDOW_MINUTES // MARKET_BUCKET_MINUTES  # 24

#: DOC-ECON-006 §9：单 Transaction legs 上限
MAX_ITEM_LEGS = 64
MAX_CURRENCY_LEGS = 16

#: DOC-ECON-005 §9：单 Command 最多涉及 item/batch
MAX_ITEMS_PER_COMMAND = 64

#: RULE-ECON-018：容器嵌套最大深度
MAX_CONTAINER_DEPTH = 2

#: DOC-ECON-010 §7：单 Order 最多 Recipe 份数
MAX_CRAFT_BATCH_SIZE = 32

#: RULE-ECON-032：Quote 默认有效游戏分钟
QUOTE_TTL_GAME_MINUTES = 10

#: DOC-ECON-008：Q1000 定点倍率中性值
Q1000_NEUTRAL = 1000

#: RULE-ECON-031：multiplier 注册范围
MULTIPLIER_RANGES_Q1000 = {
    "scarcity": (700, 2000),
    "event": (500, 2000),
    "margin": (1000, 1600),
    "discount": (700, 1000),
}

#: DOC-ECON-008 §5：canonical hash contract
QUOTE_HASH_CONTRACT_ID = "quote_input_hash.sha256_canonical_json.v1"


class AccountKind(str, Enum):
    """DOC-ECON-001 §5 封闭枚举"""

    RESIDENT = "resident"
    SHOP = "shop"
    ORGANIZATION = "organization"
    PUBLIC_BUDGET = "public_budget"
    ESCROW = "escrow"
    SYSTEM_SOURCE = "system_source"
    SYSTEM_SINK = "system_sink"


class AccountState(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


class ContractState(str, Enum):
    """DOC-ECON-002 §5 封闭枚举"""

    OFFERED = "offered"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    ENDED = "ended"
    REJECTED = "rejected"


class ItemKind(str, Enum):
    """RULE-ECON-013 五种主存储形态"""

    STACKABLE = "stackable"
    UNIQUE = "unique"
    CONTAINER = "container"
    PROPERTY_DEED = "property_deed"
    MAGICAL = "magical"


class ItemState(str, Enum):
    """active 之外为 tombstone（RULE-ECON-014/DES-ECON-004）"""

    ACTIVE = "active"
    CONSUMED = "consumed"
    DESTROYED = "destroyed"


class PropertySubjectKind(str, Enum):
    LAND_PARCEL = "land_parcel"
    BUILDING = "building"
    OPERATING_RIGHT = "operating_right"


class InventoryKind(str, Enum):
    """DOC-ECON-005 §5 封闭枚举"""

    RESIDENT = "resident"
    SHOP = "shop"
    ORGANIZATION = "organization"
    PUBLIC = "public"
    CONTAINER = "container"
    WORKPLACE = "workplace"
    ESCROW = "escrow"


class InventoryState(str, Enum):
    ACTIVE = "active"
    SEALED = "sealed"
    DECOMMISSIONED = "decommissioned"


class ResourceKind(str, Enum):
    """DOC-ECON-005 §5 Reservation resource 封闭枚举"""

    CURRENCY_AMOUNT = "currency_amount"
    UNIQUE_ITEM = "unique_item"
    ITEM_QUANTITY = "item_quantity"
    INVENTORY_SLOT = "inventory_slot"
    INVENTORY_WEIGHT = "inventory_weight"
    WORKPLACE_CAPACITY = "workplace_capacity"
    CRAFT_STATION = "craft_station"
    PROPERTY_DEED = "property_deed"


class ReservationState(str, Enum):
    """RULE-ECON-020 封闭状态机"""

    ACTIVE = "active"
    CONSUMED = "consumed"
    RELEASED = "released"
    EXPIRED = "expired"


class TransactionState(str, Enum):
    """DOC-ECON-006 §5 状态机"""

    DRAFTED = "drafted"
    RESERVED = "reserved"
    COMMITTED = "committed"
    REJECTED = "rejected"
    EXPIRED = "expired"
    ROLLED_BACK = "rolled_back"


class ShopState(str, Enum):
    """DOC-ECON-007 §5 封闭枚举"""

    OPEN = "open"
    TEMPORARILY_CLOSED = "temporarily_closed"
    SUSPENDED = "suspended"
    DECOMMISSIONED = "decommissioned"


class ShortageState(str, Enum):
    """DOC-ECON-009 §5 两 bucket 滞回状态机"""

    NORMAL = "normal"
    WATCH = "watch"
    ACTIVE = "active"
    RECOVERING = "recovering"


class SessionState(str, Enum):
    """DOC-ECON-003 §5 WorkSession 状态机"""

    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    MISSED = "missed"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    SETTLED = "settled"


class CraftOrderState(str, Enum):
    """DOC-ECON-010 §5 封闭枚举"""

    DRAFTED = "drafted"
    RESERVED = "reserved"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RECOVERY_REQUIRED = "recovery_required"


class AppropriationState(str, Enum):
    """DOC-ECON-011 §5 封闭枚举"""

    DRAFT = "draft"
    ACTIVE = "active"
    EXHAUSTED = "exhausted"
    EXPIRED = "expired"
    REVOKED = "revoked"


class EncumbranceState(str, Enum):
    """DOC-ECON-011 §5 封闭枚举"""

    ACTIVE = "active"
    CONSUMED = "consumed"
    RELEASED = "released"
    EXPIRED = "expired"


#: RULE-ECON-005：首版 Profession Catalog 必需 11 项
REQUIRED_PROFESSION_IDS = (
    "profession.blacksmith",
    "profession.apothecary",
    "profession.tavern_keeper",
    "profession.merchant",
    "profession.town_guard",
    "profession.miner",
    "profession.gatherer",
    "profession.carpenter",
    "profession.mage",
    "profession.healer",
    "profession.adventurer",
)

#: RULE-ECON-033：首版生产链必需覆盖的 Region 资源/产品集合
REQUIRED_PRODUCTION_SETS = {
    "region.duskwood_forest": frozenset(
        {"material.timber", "material.herb", "material.food_ingredient"}
    ),
    "region.boulder_mine": frozenset(
        {"material.ore", "material.magic_crystal", "material.stone"}
    ),
    "region.crown_creek_town": frozenset(
        {
            "product.tool",
            "product.weapon",
            "product.potion",
            "product.food",
            "product.magic_item",
            "product.building_material",
        }
    ),
}

#: DOC-ECON-012 §5：Crash Boundary 注册注入点
CRASH_BOUNDARIES = (
    "after_reservations",
    "after_state_writes_before_events",
    "after_events_before_idempotency",
    "after_database_commit_before_outbox",
)
