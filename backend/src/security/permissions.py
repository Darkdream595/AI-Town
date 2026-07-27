"""
角色权限执行点（DOC-BACKEND-008 RULE-BACKEND-046）

- 执行点唯一在后端：命令 type 前缀与 Role State 的映射
- 权限矩阵内容由 DOC-PLAYER-007..009 拥有；本模块只执行映射
- observer 无任何命令权限；admin 须显式启用
"""

from __future__ import annotations

from typing import Dict

from ..foundation.errors import ApiError

ROLE_ORDER = {"observer": 0, "player": 1, "mayor": 2, "admin": 3}

#: 命令 type 前缀 → 最低角色（system.* 逐类型登记，见 DEFAULT_SYSTEM_COMMAND_ROLES）
PREFIX_MIN_ROLE: Dict[str, str] = {
    "player.": "player",
    "mayor.": "mayor",
    "admin.": "admin",
}

DEFAULT_SYSTEM_COMMAND_ROLES: Dict[str, str] = {
    "system.world.pause": "player",
    "system.world.resume": "player",
    "system.world.speed": "player",
}


def min_role_for(command_type: str,
                 system_roles: Dict[str, str] = DEFAULT_SYSTEM_COMMAND_ROLES) -> str:
    for prefix, role in PREFIX_MIN_ROLE.items():
        if command_type.startswith(prefix):
            return role
    if command_type in system_roles:
        return system_roles[command_type]
    # 未登记前缀一律按 admin 处理（fail closed）
    return "admin"


def enforce_role(role_state: str, command_type: str,
                 system_roles: Dict[str, str] = DEFAULT_SYSTEM_COMMAND_ROLES) -> None:
    required = min_role_for(command_type, system_roles)
    if ROLE_ORDER.get(role_state, -1) < ROLE_ORDER[required]:
        raise ApiError("BACKEND_FORBIDDEN", {
            "command_type": command_type,
            "reason_code": "role_insufficient",
        })


#: REST 管理端点最低角色（world-admin/save/settings/secret/destructive/diagnostics）
REST_ADMIN_ACTION_MIN_ROLE: Dict[str, str] = {
    "world-admin": "player",
    "save": "player",
    "settings": "player",
    "secret": "player",
    "destructive": "player",
    "diagnostics": "player",
    "ticket": "player",
    "session": "observer",
    "health": "observer",
}


def enforce_rest_role(role_state: str, route_class: str) -> None:
    required = REST_ADMIN_ACTION_MIN_ROLE.get(route_class, "admin")
    if ROLE_ORDER.get(role_state, -1) < ROLE_ORDER[required]:
        raise ApiError("BACKEND_FORBIDDEN", {
            "route_class": route_class,
            "reason_code": "role_insufficient",
        })
