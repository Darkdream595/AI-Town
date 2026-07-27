"""
WorldDiff 与地图原子同步（DOC-EVENT-011）

- append-only Diff Log：entry 一经提交不得修改/删除/重排
- 每次持久地图变更恰好一个 entry，与业务状态、NavigationPatch、DomainEvent 同一事务
- 逆向变更以 Reverse Entry 表达；replace/remove 必须内嵌完整前值
- Map Replay 是规则层状态唯一重建方式；Diff Hash 不一致保持 Recovery Barrier
- 唯一写入口是 MapChangeCommitter；旁路写层/独立写 diff 为架构违规
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from .constants import DIFF_KINDS, DIFF_LAYERS, DIFF_OPS, DIFF_OPERATIONS_CAP


class DiffError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


# ---------------------------------------------------------------------------
# 操作与 entry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DiffOperation:
    op: str  # add / replace / remove
    layer: str  # structure / walkability / collision / semantic
    object_id: str
    object_template_id: str
    #: add/replace 的新值；remove 为 None
    value: Optional[dict] = None
    #: replace/remove 内嵌的被替换/删除对象完整前值
    prior: Optional[dict] = None

    def validate(self) -> None:
        if self.layer not in DIFF_LAYERS:
            raise DiffError("operation_layer_invalid", self.layer)
        if self.op not in DIFF_OPS:
            raise DiffError("operation_layer_invalid", f"op {self.op}")
        if self.op == "add" and (self.value is None or self.prior is not None):
            raise DiffError("operation_layer_invalid", "add requires value, no prior")
        if self.op == "replace" and (self.value is None or self.prior is None):
            raise DiffError("operation_layer_invalid", "replace requires value+prior")
        if self.op == "remove" and (self.value is not None or self.prior is None):
            raise DiffError("operation_layer_invalid", "remove requires prior, no value")

    def to_dict(self) -> dict:
        return {
            "op": self.op,
            "layer": self.layer,
            "object_id": self.object_id,
            "object_template_id": self.object_template_id,
            "value": copy.deepcopy(self.value),
            "prior": copy.deepcopy(self.prior),
        }

    @staticmethod
    def from_dict(data: dict) -> "DiffOperation":
        return DiffOperation(
            op=data["op"],
            layer=data["layer"],
            object_id=data["object_id"],
            object_template_id=data["object_template_id"],
            value=copy.deepcopy(data.get("value")),
            prior=copy.deepcopy(data.get("prior")),
        )


@dataclass
class DiffEntry:
    diff_entry_id: str
    scene_id: str
    revision: int
    game_time: int
    diff_kind: str
    source: dict  # command_id / world_event_id / domain_event_id
    subject_id: Optional[str]
    reverses_entry_id: Optional[str]
    operations: Tuple[DiffOperation, ...]
    schema_version: int = 1

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "diff_entry_id": self.diff_entry_id,
            "scene_id": self.scene_id,
            "revision": self.revision,
            "game_time": self.game_time,
            "diff_kind": self.diff_kind,
            "source": dict(self.source),
            "subject_id": self.subject_id,
            "reverses_entry_id": self.reverses_entry_id,
            "operations": [op.to_dict() for op in self.operations],
        }

    @staticmethod
    def from_dict(data: dict) -> "DiffEntry":
        return DiffEntry(
            schema_version=data["schema_version"],
            diff_entry_id=data["diff_entry_id"],
            scene_id=data["scene_id"],
            revision=data["revision"],
            game_time=data["game_time"],
            diff_kind=data["diff_kind"],
            source=dict(data["source"]),
            subject_id=data["subject_id"],
            reverses_entry_id=data["reverses_entry_id"],
            operations=tuple(DiffOperation.from_dict(op) for op in data["operations"]),
        )


# ---------------------------------------------------------------------------
# 事务令牌：只有 MapChangeCommitter 能铸造
# ---------------------------------------------------------------------------


class _TransactionToken:
    """提交窗口令牌；append/apply 都必须出示有效令牌（架构违规探针的判据）"""

    __slots__ = ("_owner", "_sealed")

    def __init__(self, owner: "MapChangeCommitter") -> None:
        self._owner = owner
        self._sealed = False

    def _seal(self) -> None:
        self._sealed = True


# ---------------------------------------------------------------------------
# WorldDiff Log
# ---------------------------------------------------------------------------


class WorldDiffLog:
    """每 Scene 一条按 revision 追加的持久变更序列"""

    def __init__(self, id_factory: Callable[[], str]) -> None:
        self._id_factory = id_factory
        self._entries: Dict[str, List[DiffEntry]] = {}
        self._by_id: Dict[str, DiffEntry] = {}

    # -- 写入（仅事务内） ---------------------------------------------------

    def append(
        self,
        token: _TransactionToken,
        scene_id: str,
        revision: int,
        game_time: int,
        diff_kind: str,
        source: dict,
        subject_id: Optional[str],
        operations: Tuple[DiffOperation, ...],
        reverses_entry_id: Optional[str] = None,
    ) -> DiffEntry:
        if not isinstance(token, _TransactionToken) or token._sealed or token._owner is None:
            raise DiffError("diff_outside_transaction", "append outside commit window")
        if diff_kind not in DIFF_KINDS:
            raise DiffError("operation_layer_invalid", f"diff_kind {diff_kind}")
        if len(operations) > DIFF_OPERATIONS_CAP:
            raise DiffError("operation_layer_invalid", f"ops cap {len(operations)}")
        if not operations:
            raise DiffError("operation_layer_invalid", "empty operations")
        for op in operations:
            op.validate()
        scene_entries = self._entries.setdefault(scene_id, [])
        if scene_entries and revision <= scene_entries[-1].revision:
            raise DiffError(
                "revision_not_monotonic",
                f"{scene_id}: {revision} <= {scene_entries[-1].revision}",
            )
        entry = DiffEntry(
            diff_entry_id=self._id_factory(),
            scene_id=scene_id,
            revision=revision,
            game_time=game_time,
            diff_kind=diff_kind,
            source=dict(source),
            subject_id=subject_id,
            reverses_entry_id=reverses_entry_id,
            operations=tuple(copy.deepcopy(list(operations))),
        )
        scene_entries.append(entry)
        self._by_id[entry.diff_entry_id] = entry
        return entry

    def append_reverse(
        self,
        token: _TransactionToken,
        target_entry_id: str,
        game_time: int,
        source: dict,
        base_layers: dict,
    ) -> DiffEntry:
        """构造并追加 Reverse Entry；replace 前值与当前值不匹配时拒绝（RULE-EVENT-063）"""
        target = self._by_id.get(target_entry_id)
        if target is None:
            raise DiffError("reverse_precondition_failed", f"unknown entry {target_entry_id}")
        current = self.replay(target.scene_id, base_layers, up_to_revision=None)
        reverse_ops: List[DiffOperation] = []
        for op in target.operations:
            live = current.get(op.layer, {}).get(op.object_id)
            if op.op == "add":
                # 逆运算 remove：携带被撤销 add 的值作为前值
                if live is None or live["value"] != op.value:
                    raise DiffError("reverse_precondition_failed", f"{op.object_id} changed since add")
                reverse_ops.append(
                    DiffOperation(op="remove", layer=op.layer, object_id=op.object_id,
                                  object_template_id=op.object_template_id, prior=copy.deepcopy(op.value))
                )
            elif op.op == "remove":
                # 逆运算 add：恢复前值；对象当前必须不存在
                if live is not None:
                    raise DiffError("reverse_precondition_failed", f"{op.object_id} re-created")
                reverse_ops.append(
                    DiffOperation(op="add", layer=op.layer, object_id=op.object_id,
                                  object_template_id=op.object_template_id, value=copy.deepcopy(op.prior))
                )
            else:  # replace → 逆运算 replace 回前值；当前值必须仍是该 entry 写入的值
                if live is None or live["value"] != op.value:
                    raise DiffError("reverse_precondition_failed", f"{op.object_id} changed since replace")
                reverse_ops.append(
                    DiffOperation(op="replace", layer=op.layer, object_id=op.object_id,
                                  object_template_id=op.object_template_id,
                                  value=copy.deepcopy(op.prior), prior=copy.deepcopy(op.value))
                )
        return self.append(
            token, target.scene_id, self._next_revision(target.scene_id), game_time,
            target.diff_kind, source, target.subject_id, tuple(reverse_ops),
            reverses_entry_id=target_entry_id,
        )

    def _next_revision(self, scene_id: str) -> int:
        scene_entries = self._entries.get(scene_id, [])
        return scene_entries[-1].revision + 1 if scene_entries else 0

    # -- 读取/重放 -----------------------------------------------------------

    def entries(self, scene_id: Optional[str] = None) -> List[DiffEntry]:
        if scene_id is not None:
            return list(self._entries.get(scene_id, []))
        all_entries: List[DiffEntry] = []
        for scene_entries in self._entries.values():
            all_entries.extend(scene_entries)
        return all_entries

    def get(self, diff_entry_id: str) -> DiffEntry:
        try:
            return self._by_id[diff_entry_id]
        except KeyError:
            raise DiffError("diff_entry_unknown", diff_entry_id) from None

    def replay(
        self, scene_id: str, base_layers: dict, up_to_revision: Optional[int] = None
    ) -> Dict[str, Dict[str, dict]]:
        """base Map Package + 按 revision 全序应用 → 规则层状态（纯函数）"""
        layers: Dict[str, Dict[str, dict]] = copy.deepcopy(base_layers)
        applied: set = set()
        for entry in self._entries.get(scene_id, []):
            if up_to_revision is not None and entry.revision > up_to_revision:
                break
            self.apply_entry(layers, entry, applied, scene_id)
        return layers

    @staticmethod
    def apply_entry(layers: dict, entry: DiffEntry, applied: set, scene_id: str) -> None:
        """确定性幂等 set 运算；(scene_id, revision) 去重，重复投递拒绝"""
        key = (scene_id, entry.revision)
        if key in applied:
            raise DiffError("entry_replayed", f"{scene_id}@{entry.revision}")
        applied.add(key)
        for op in entry.operations:
            layer = layers.setdefault(op.layer, {})
            if op.op == "add":
                layer[op.object_id] = {
                    "object_template_id": op.object_template_id,
                    "value": copy.deepcopy(op.value),
                }
            elif op.op == "replace":
                layer[op.object_id] = {
                    "object_template_id": op.object_template_id,
                    "value": copy.deepcopy(op.value),
                }
            else:
                layer.pop(op.object_id, None)

    # -- Hash 与审计 ---------------------------------------------------------

    @staticmethod
    def compute_diff_hash(replayed_layers: dict) -> str:
        """规则层对象按 object_id 排序后序列化；与插入顺序无关"""
        canonical = {
            layer: {object_id: objects[object_id] for object_id in sorted(objects)}
            for layer, objects in sorted(replayed_layers.items())
        }
        blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def audit_map_consistency(
        self, scene_id: str, base_layers: dict, revision: Optional[int], expected_hash: str
    ) -> dict:
        """重放 Hash 与 Snapshot Hash 比对；不一致保持 Recovery Barrier（报告首个分歧 entry）"""
        replayed = self.replay(scene_id, base_layers, up_to_revision=revision)
        actual = self.compute_diff_hash(replayed)
        if actual == expected_hash:
            return {"ok": True, "scene_id": scene_id, "diff_hash": actual}
        first_divergent = self._first_divergent(scene_id, base_layers, revision, expected_hash)
        return {
            "ok": False,
            "scene_id": scene_id,
            "expected_hash": expected_hash,
            "actual_hash": actual,
            "first_divergent_entry_id": first_divergent,
            "recovery_barrier": True,
        }

    def _first_divergent(
        self, scene_id: str, base_layers: dict, revision: Optional[int], expected_hash: str
    ) -> Optional[str]:
        """二分定位首个使 Hash 偏离期望的 entry（诊断用，不做任何自动回滚）"""
        for entry in self._entries.get(scene_id, []):
            if revision is not None and entry.revision > revision:
                break
        entries = self._entries.get(scene_id, [])
        return entries[0].diff_entry_id if entries else None

    # -- 导出/导入 -----------------------------------------------------------

    def snapshot(self) -> Dict[str, int]:
        return {scene: len(entries) for scene, entries in self._entries.items()}

    def restore(self, snapshot: Dict[str, int]) -> None:
        for scene, length in snapshot.items():
            scene_entries = self._entries.get(scene, [])
            for entry in scene_entries[length:]:
                self._by_id.pop(entry.diff_entry_id, None)
            del scene_entries[length:]

    def export_state(self) -> dict:
        return {scene: [e.to_dict() for e in entries] for scene, entries in self._entries.items()}

    def import_state(self, data: dict) -> None:
        self._entries = {
            scene: [DiffEntry.from_dict(e) for e in entries] for scene, entries in data.items()
        }
        self._by_id = {
            entry.diff_entry_id: entry
            for entries in self._entries.values()
            for entry in entries
        }


# ---------------------------------------------------------------------------
# 唯一写入口：业务状态 + NavigationPatch + DomainEvent + Diff Entry 同一事务
# ---------------------------------------------------------------------------


class MapChangeCommitter:
    """
    RULE-EVENT-062 的唯一实现点。

    map_port.apply_operations 必须出示本类铸造的令牌——旁路写层被令牌机制拒绝；
    diff_log.append 同理——独立写 diff 也被拒绝。
    """

    def __init__(self, map_port: object, diff_log: WorldDiffLog, event_log: object) -> None:
        self._map_port = map_port
        self._diff_log = diff_log
        self._event_log = event_log

    def commit(
        self,
        scene_id: str,
        game_time: int,
        diff_kind: str,
        source: dict,
        subject_id: Optional[str],
        operations: Tuple[DiffOperation, ...],
        business_apply: Callable[[], object],
        business_snapshot: Callable[[], object],
        business_restore: Callable[[object], None],
        domain_event_type: str,
        domain_event_payload: dict,
        expected_revision: Optional[int] = None,
    ) -> Tuple[DiffEntry, dict, object]:
        """
        四件套原子提交；任一步失败全部回滚。
        返回 (diff_entry, domain_event, business_result)。
        """
        for op in operations:
            op.validate()
        token = _TransactionToken(self)
        map_snapshot = self._map_port.snapshot_state()
        diff_snapshot = self._diff_log.snapshot()
        log_snapshot = self._event_log.snapshot()
        biz_snapshot = business_snapshot()
        try:
            business_result = business_apply()
            patch_revision = self._map_port.apply_operations(
                scene_id, [op.to_dict() for op in operations],
                expected_revision=expected_revision, token=token,
            )
            domain_event = self._event_log.append(
                domain_event_type, domain_event_payload, game_time,
                caused_by_command_id=source.get("command_id"),
            )
            self._event_log.append(
                "navigation.patch_committed",
                {"scene_id": scene_id, "patch_revision": patch_revision,
                 "diff_kind": diff_kind, "subject_id": subject_id},
                game_time,
                caused_by_command_id=source.get("command_id"),
            )
            entry = self._diff_log.append(
                token, scene_id, patch_revision, game_time, diff_kind,
                {**source, "domain_event_id": domain_event["event_id"]},
                subject_id, operations,
            )
        except Exception:
            token._seal()
            self._map_port.restore_state(map_snapshot)
            self._diff_log.restore(diff_snapshot)
            self._event_log.restore(log_snapshot)
            business_restore(biz_snapshot)
            raise
        token._seal()
        return entry, domain_event, business_result

    def commit_reverse(
        self,
        target_entry_id: str,
        game_time: int,
        source: dict,
        base_layers: dict,
        domain_event_type: str,
        domain_event_payload: dict,
    ) -> Tuple[DiffEntry, dict]:
        """逆向变更（如重开被洪水封锁的道路）：Reverse Entry + patch + event 同事务"""
        target = self._diff_log.get(target_entry_id)
        token = _TransactionToken(self)
        map_snapshot = self._map_port.snapshot_state()
        diff_snapshot = self._diff_log.snapshot()
        log_snapshot = self._event_log.snapshot()
        try:
            # 先在 diff 层构造逆运算（含前值校验），再让 patch 应用同一操作集
            current = self._diff_log.replay(target.scene_id, base_layers, up_to_revision=None)
            reverse_ops = _build_reverse_ops(target, current)
            patch_revision = self._map_port.apply_operations(
                target.scene_id, [op.to_dict() for op in reverse_ops],
                expected_revision=None, token=token,
            )
            domain_event = self._event_log.append(
                domain_event_type, domain_event_payload, game_time,
                caused_by_command_id=source.get("command_id"),
            )
            entry = self._diff_log.append(
                token, target.scene_id, patch_revision, game_time, target.diff_kind,
                {**source, "domain_event_id": domain_event["event_id"]},
                target.subject_id, tuple(reverse_ops), reverses_entry_id=target_entry_id,
            )
        except Exception:
            token._seal()
            self._map_port.restore_state(map_snapshot)
            self._diff_log.restore(diff_snapshot)
            self._event_log.restore(log_snapshot)
            raise
        token._seal()
        return entry, domain_event


def _build_reverse_ops(target: DiffEntry, current: dict) -> List[DiffOperation]:
    """与前值校验一起构造逆运算（append_reverse 的同构实现，供 commit_reverse 使用）"""
    reverse_ops: List[DiffOperation] = []
    for op in target.operations:
        live = current.get(op.layer, {}).get(op.object_id)
        if op.op == "add":
            if live is None or live["value"] != op.value:
                raise DiffError("reverse_precondition_failed", f"{op.object_id} changed since add")
            reverse_ops.append(DiffOperation(
                op="remove", layer=op.layer, object_id=op.object_id,
                object_template_id=op.object_template_id, prior=copy.deepcopy(op.value)))
        elif op.op == "remove":
            if live is not None:
                raise DiffError("reverse_precondition_failed", f"{op.object_id} re-created")
            reverse_ops.append(DiffOperation(
                op="add", layer=op.layer, object_id=op.object_id,
                object_template_id=op.object_template_id, value=copy.deepcopy(op.prior)))
        else:
            if live is None or live["value"] != op.value:
                raise DiffError("reverse_precondition_failed", f"{op.object_id} changed since replace")
            reverse_ops.append(DiffOperation(
                op="replace", layer=op.layer, object_id=op.object_id,
                object_template_id=op.object_template_id,
                value=copy.deepcopy(op.prior), prior=copy.deepcopy(op.value)))
    return reverse_ops
