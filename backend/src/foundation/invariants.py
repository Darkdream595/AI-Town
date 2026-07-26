"""
全局不变量验证器

符合 DOC-FOUNDATION-005 规范：
- RULE-FOUNDATION-019: 权威后端验证所有状态变更
- RULE-FOUNDATION-020: 居民不能穿墙或凭空获得物品
- RULE-FOUNDATION-021: 金钱守恒（交易前后总和不变）
"""

from typing import Any, Callable, List
from dataclasses import dataclass


@dataclass
class InvariantViolation:
    """不变量违反记录"""
    rule_id: str
    message: str
    context: dict


class InvariantValidator:
    """
    全局不变量验证器

    验证跨系统的不变量约束
    """

    def __init__(self):
        self._validators: List[Callable] = []

    def register(self, validator_fn: Callable) -> None:
        """注册一个验证器函数"""
        self._validators.append(validator_fn)

    def validate(self, context: dict) -> List[InvariantViolation]:
        """
        执行所有已注册的验证器

        Args:
            context: 验证上下文（包含世界状态等）

        Returns:
            List[InvariantViolation]: 违反的不变量列表（空列表表示通过）
        """
        violations = []

        for validator_fn in self._validators:
            try:
                result = validator_fn(context)
                if isinstance(result, InvariantViolation):
                    violations.append(result)
                elif isinstance(result, list):
                    violations.extend(result)
            except Exception as e:
                violations.append(InvariantViolation(
                    rule_id="VALIDATOR_ERROR",
                    message=f"Validator raised exception: {str(e)}",
                    context={"validator": validator_fn.__name__}
                ))

        return violations


# 全局验证器实例
_global_validator = InvariantValidator()


def register_invariant(validator_fn: Callable) -> None:
    """注册全局不变量验证器"""
    _global_validator.register(validator_fn)


def validate_invariants(context: dict) -> List[InvariantViolation]:
    """
    验证全局不变量

    Args:
        context: 验证上下文

    Returns:
        List[InvariantViolation]: 违反的不变量列表

    Raises:
        ValueError: 如果存在不变量违反
    """
    violations = _global_validator.validate(context)

    if violations:
        messages = [f"[{v.rule_id}] {v.message}" for v in violations]
        raise ValueError(f"Invariant violations detected:\n" + "\n".join(messages))

    return violations


# 内置不变量验证器

def validate_position_legality(context: dict) -> List[InvariantViolation]:
    """
    RULE-FOUNDATION-020: 验证位置合法性

    居民只能在 Walkable 区域移动
    """
    violations = []

    # TODO: 实现位置合法性检查（依赖 Map 系统）

    return violations


def validate_money_conservation(context: dict) -> List[InvariantViolation]:
    """
    RULE-FOUNDATION-021: 验证金钱守恒

    交易前后总金额不变
    """
    violations = []

    # TODO: 实现金钱守恒检查（依赖 Economy 系统）

    return violations


# 注册内置验证器
register_invariant(validate_position_legality)
register_invariant(validate_money_conservation)
