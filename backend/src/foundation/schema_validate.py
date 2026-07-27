"""
JSON Schema 校验基元（foundation；api 与 orchestrator 共用）

- strict 模式：additionalProperties=false 未注册字段即拒绝，不忽略、不透传
- 全部数值必须有限（RULE-FOUNDATION-045 数值有限性）
- schema_version 顶层必含且为 uint ≥ 1
"""

from __future__ import annotations

import math
from typing import Optional

import jsonschema

SCHEMA_DRAFT = jsonschema.Draft202012Validator


class SchemaValidationError(Exception):
    def __init__(self, reason_code: str, message: str = "") -> None:
        super().__init__(message or reason_code)
        self.reason_code = reason_code


def _check_finite(value: object, path: str = "$") -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise SchemaValidationError("number_not_finite", path)
    elif isinstance(value, dict):
        for key, item in value.items():
            _check_finite(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _check_finite(item, f"{path}[{index}]")


def validate_payload(instance: object, schema: dict,
                     check_schema_version: bool = True) -> None:
    """校验失败抛 SchemaValidationError（reason_code 取首个字段路径）"""
    if check_schema_version:
        if not isinstance(instance, dict):
            raise SchemaValidationError("payload_not_object")
        version = instance.get("schema_version")
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise SchemaValidationError("schema_version_invalid")
    try:
        SCHEMA_DRAFT(schema).validate(instance)
    except jsonschema.ValidationError as exc:
        path = ".".join(str(part) for part in exc.absolute_path) or "$"
        raise SchemaValidationError(f"schema_violation:{path}") from None
    except jsonschema.SchemaError as exc:
        raise SchemaValidationError("schema_definition_invalid", str(exc)) from None
    _check_finite(instance)


def make_object_schema(properties: dict, required: tuple,
                       additional: bool = False) -> dict:
    """严格对象 Schema 便捷构造（additionalProperties=false 默认）"""
    return {
        "type": "object",
        "properties": dict(properties),
        "required": list(required),
        "additionalProperties": additional,
    }
