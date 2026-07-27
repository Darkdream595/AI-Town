"""
wire Schema 注册表与 Upcaster（DOC-BACKEND-007 RULE-BACKEND-037..041）

- 三层版本：protocol_version / payload schema_version / REST path major
- Registry 是唯一登记处：name/version/owner_doc_id/status/kind/Golden Sample
- Compatible Change 白名单 vs Breaking Change 静态比对（CI diff）
- Upcaster 纯函数单版本步进；链长上限 16；高版本持久化拒绝加载
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from ..foundation.errors import ApiError
from ..foundation.schema_validate import SchemaValidationError, validate_payload

SCHEMA_STATUSES = frozenset({"active", "deprecated", "frozen"})
SCHEMA_KINDS = frozenset(
    {"command_payload", "event_payload", "rest_resource", "ws_frame", "persisted_record"})

UPCAST_CHAIN_MAX = 16
CURRENT_PROTOCOL_VERSION = 1


@dataclass
class SchemaEntry:
    name: str
    version: int
    owner_doc_id: str
    status: str
    kind: str
    schema: dict
    golden_sample: dict
    introduced_protocol_version: int = 1
    frozen_hash: Optional[str] = None

    def freeze_fingerprint(self) -> str:
        import hashlib
        import json
        canonical = json.dumps(
            {"schema": self.schema, "golden_sample": self.golden_sample},
            sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class SchemaRegistry:
    def __init__(self) -> None:
        self._entries: Dict[Tuple[str, int], SchemaEntry] = {}
        self._upcasters: Dict[Tuple[str, int], Callable[[dict], dict]] = {}

    # -- 登记 ----------------------------------------------------------------

    def register(self, entry: SchemaEntry) -> None:
        if entry.status not in SCHEMA_STATUSES:
            raise ApiError("BACKEND_INTERNAL_INVARIANT",
                           {"reason_code": "schema_status_invalid"})
        if entry.kind not in SCHEMA_KINDS:
            raise ApiError("BACKEND_INTERNAL_INVARIANT",
                           {"reason_code": "schema_kind_invalid"})
        key = (entry.name, entry.version)
        if key in self._entries:
            raise ApiError("BACKEND_INTERNAL_INVARIANT",
                           {"reason_code": f"schema_duplicate:{entry.name}v{entry.version}"})
        # Golden Sample 必须自验（WS 帧 Envelope 的 schema_version 在 payload 内，
        # 顶层只有 protocol_version，故豁免顶层 schema_version 检查）
        check_sv = entry.kind != "ws_frame"
        try:
            validate_payload(entry.golden_sample, entry.schema,
                             check_schema_version=check_sv)
        except SchemaValidationError as exc:
            raise ApiError("BACKEND_INTERNAL_INVARIANT",
                           {"reason_code": f"golden_sample_invalid:{entry.name}:{exc.reason_code}"}) from None
        if entry.status == "frozen":
            entry.frozen_hash = entry.freeze_fingerprint()
        self._entries[key] = entry

    def register_upcaster(self, name: str, from_version: int,
                          fn: Callable[[dict], dict]) -> None:
        if (name, from_version + 1) not in self._entries:
            raise ApiError("BACKEND_INTERNAL_INVARIANT",
                           {"reason_code": f"upcaster_target_missing:{name}v{from_version + 1}"})
        self._upcasters[(name, from_version)] = fn

    # -- 查询/校验 ---------------------------------------------------------------

    def contains(self, name: str, version: int) -> bool:
        return (name, version) in self._entries

    def lookup(self, name: str, version: int) -> SchemaEntry:
        entry = self._entries.get((name, version))
        if entry is None:
            raise ApiError("BACKEND_PROTOCOL_MISMATCH",
                           {"reason_code": f"schema_not_registered:{name}v{version}"})
        return entry

    def latest_version(self, name: str) -> int:
        versions = [version for (n, version) in self._entries if n == name]
        if not versions:
            raise ApiError("BACKEND_PROTOCOL_MISMATCH",
                           {"reason_code": f"schema_unknown:{name}"})
        return max(versions)

    def validate_wire(self, name: str, version: int, obj: dict) -> None:
        entry = self.lookup(name, version)
        try:
            validate_payload(obj, entry.schema)
        except SchemaValidationError as exc:
            raise ApiError("BACKEND_SCHEMA_INVALID",
                           {"reason_code": f"{name}:{exc.reason_code}"}) from None

    # -- Upcast ----------------------------------------------------------------

    def upcast_chain(self, name: str, from_version: int, obj: dict,
                     to_version: Optional[int] = None) -> dict:
        """逐版升级为当前版本；高版本（降级安装）拒绝；链缺一环 → 内部错误"""
        target = to_version if to_version is not None else self.latest_version(name)
        if from_version > target:
            raise ApiError("BACKEND_PROTOCOL_MISMATCH", {
                "reason_code": "persisted_version_too_new",
                "expected": target, "received": from_version})
        result = copy.deepcopy(obj)
        version = from_version
        steps = 0
        while version < target:
            steps += 1
            if steps > UPCAST_CHAIN_MAX:
                raise ApiError("BACKEND_INTERNAL_INVARIANT",
                               {"reason_code": "upcast_chain_too_long"})
            upcaster = self._upcasters.get((name, version))
            if upcaster is None:
                raise ApiError("BACKEND_INTERNAL_INVARIANT",
                               {"reason_code": f"upcast_chain_broken:{name}v{version}"})
            result = upcaster(result)
            version += 1
        # 升级结果必须通过当前版本 Schema（无损性断言）
        self.validate_wire(name, target, result)
        return result

    # -- 审计 ----------------------------------------------------------------

    def audit_integrity(self) -> List[str]:
        """Registry 完整性：frozen 未被修改、golden 自验、upcast 链连续"""
        gaps: List[str] = []
        for (name, version), entry in sorted(self._entries.items()):
            if entry.status == "frozen" and entry.frozen_hash != entry.freeze_fingerprint():
                gaps.append(f"frozen_modified:{name}v{version}")
            try:
                validate_payload(entry.golden_sample, entry.schema,
                                 check_schema_version=entry.kind != "ws_frame")
            except SchemaValidationError:
                gaps.append(f"golden_invalid:{name}v{version}")
            latest = self.latest_version(name)
            for step in range(1, latest):
                if (name, step) in self._entries and (name, step + 1) in self._entries:
                    if (name, step) not in self._upcasters and entry.status != "frozen":
                        gaps.append(f"upcast_missing:{name}v{step}→v{step + 1}")
        return gaps

    def all_entries(self) -> List[SchemaEntry]:
        return [self._entries[key] for key in sorted(self._entries)]


# ---------------------------------------------------------------------------
# Compatible / Breaking Change 静态比对（CI diff）
# ---------------------------------------------------------------------------


def detect_breaking_changes(old_schema: dict, new_schema: dict) -> List[str]:
    """
    Breaking：删除或重命名字段、改变类型/语义、optional 变必填、closed enum 增删值。
    Compatible（白名单）：新增 optional 字段、open enum 新增取值、新增类型。
    """
    breaks: List[str] = []
    if old_schema.get("type") != new_schema.get("type"):
        breaks.append("type_changed")
        return breaks
    old_props = old_schema.get("properties", {})
    new_props = new_schema.get("properties", {})
    for field_name in old_props:
        if field_name not in new_props:
            breaks.append(f"field_removed:{field_name}")
    old_required = set(old_schema.get("required", []))
    new_required = set(new_schema.get("required", []))
    for field_name in new_required - old_required:
        if field_name in old_props:
            breaks.append(f"optional_to_required:{field_name}")
        # 新字段直接必填也属 Breaking（旧数据无此字段）
        else:
            breaks.append(f"new_field_required:{field_name}")
    for field_name in old_props.keys() & new_props.keys():
        old_field = old_props[field_name]
        new_field = new_props[field_name]
        if old_field.get("type") != new_field.get("type"):
            breaks.append(f"field_type_changed:{field_name}")
        old_enum = old_field.get("enum")
        new_enum = new_field.get("enum")
        if old_enum is not None and new_enum is not None:
            open_enum = old_field.get("x-open-enum", False)
            if not open_enum and set(old_enum) != set(new_enum):
                breaks.append(f"closed_enum_changed:{field_name}")
            if open_enum and not set(new_enum) >= set(old_enum):
                breaks.append(f"open_enum_value_removed:{field_name}")
        if set(old_field.get("properties", {})) != set(new_field.get("properties", {})):
            breaks.extend(f"{field_name}.{sub}" for sub in detect_breaking_changes(
                old_field, new_field))
    if old_schema.get("additionalProperties") != new_schema.get("additionalProperties"):
        breaks.append("additional_properties_changed")
    return breaks


def assert_versioning_policy(old_entry: SchemaEntry, new_entry: SchemaEntry) -> None:
    """CI 拦截：Breaking 变更未 bump 版本即失败"""
    breaks = detect_breaking_changes(old_entry.schema, new_entry.schema)
    if breaks and new_entry.version <= old_entry.version:
        raise ApiError("BACKEND_INTERNAL_INVARIANT", {
            "reason_code": f"breaking_without_bump:{old_entry.name}:{breaks[0]}"})
