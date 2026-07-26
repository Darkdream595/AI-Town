"""
ULID 生成器

符合 DOC-FOUNDATION-006 规范：
- 26 字符 Crockford Base32（排除 I/L/O/U）
- RULE-FOUNDATION-033：Runtime ID 使用 ULID
- 格式：^[0-9A-HJKMNP-TV-Z]{26}$
"""

import re
from ulid import ULID

# RULE-FOUNDATION-033: ULID pattern (Crockford Base32, 排除 I/L/O/U)
ULID_PATTERN = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


def generate_ulid() -> str:
    """
    生成符合规范的 ULID

    Returns:
        str: 26 字符 ULID，格式为 Crockford Base32

    Examples:
        >>> ulid = generate_ulid()
        >>> len(ulid)
        26
        >>> is_valid_ulid(ulid)
        True
    """
    return str(ULID())


def is_valid_ulid(ulid_str: str) -> bool:
    """
    验证 ULID 格式是否合法

    Args:
        ulid_str: 待验证的 ULID 字符串

    Returns:
        bool: True 如果格式合法

    Examples:
        >>> is_valid_ulid("01HQVX5W6T9YZBQXRM8NPSJ9K7")
        True
        >>> is_valid_ulid("invalid")
        False
        >>> is_valid_ulid("01HQVX5W6T9YZBQXRM8NPSJ9U7")  # 包含 U
        False
    """
    if not isinstance(ulid_str, str):
        return False
    return ULID_PATTERN.match(ulid_str) is not None


def ulid_to_timestamp(ulid_str: str) -> int:
    """
    从 ULID 提取时间戳（毫秒）

    Args:
        ulid_str: ULID 字符串

    Returns:
        int: Unix 时间戳（毫秒）

    Raises:
        ValueError: 如果 ULID 格式不合法
    """
    if not is_valid_ulid(ulid_str):
        raise ValueError(f"Invalid ULID format: {ulid_str}")

    ulid_obj = ULID.from_str(ulid_str)
    # ULID.timestamp 返回的是秒，需要转换为毫秒
    return int(ulid_obj.timestamp * 1000)
