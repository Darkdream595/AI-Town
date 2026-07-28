"""
确定性重放与 upcaster（DOC-RELEASE-003）

- RULE-RELEASE-023：Replay 是确定性纯函数：只消费 Snapshot 状态与 Event tail；
  不调模型、不联网、不取系统时间与进程随机数；两次 Replay 逐字节相同哈希
- RULE-RELEASE-024：旧版本事件读取时经注册 upcaster 转换，原始行字节不变；
  upcaster 必须对输入输出执行 strict validation
"""

from __future__ import annotations

import copy
import json

from .constants import ReleaseError
from .snapshots import canonical_json_bytes
from hashlib import sha256

#: 事件应用器注册表：event_type -> callable(state: dict, payload: dict) -> None
#: 应用器必须确定性（RULE-RELEASE-023）；AI 结果经 AI Replay Record 还原
EVENT_APPLIERS: dict[str, object] = {}

#: upcaster 注册表：event_type -> {from_schema_version: callable(payload)->payload}
UPCASTERS: dict[str, dict[int, object]] = {}

#: upcaster 输出校验器（strict validation）：event_type -> callable(payload)->bool
UPCAST_VALIDATORS: dict[str, object] = {}

#: 当前事件 schema 版本：event_type -> version
EVENT_SCHEMA_CURRENT: dict[str, int] = {}


def register_event(event_type: str, schema_version: int, applier,
                   validators=None) -> None:
    EVENT_APPLIERS[event_type] = applier
    EVENT_SCHEMA_CURRENT[event_type] = schema_version
    if validators is not None:
        UPCAST_VALIDATORS[event_type] = validators


def register_upcaster(event_type: str, from_version: int, fn) -> None:
    UPCASTERS.setdefault(event_type, {})[from_version] = fn


def upcast_payload(event_type: str, from_version: int, payload: dict) -> dict:
    """RULE-RELEASE-024：读取时转换到当前形状；校验失败即停止，不跳过"""
    current = EVENT_SCHEMA_CURRENT.get(event_type)
    if current is None:
        raise ReleaseError("RELEASE_REPLAY_UNKNOWN_EVENT",
                           {"event_type": event_type})
    validator = UPCAST_VALIDATORS.get(event_type)
    if validator is not None and not validator(payload):
        raise ReleaseError("RELEASE_REPLAY_UPCAST_FAILED",
                           {"event_type": event_type, "stage": "input"})
    version = from_version
    result = payload
    while version < current:
        fn = UPCASTERS.get(event_type, {}).get(version)
        if fn is None:
            raise ReleaseError("RELEASE_REPLAY_UPCAST_FAILED",
                               {"event_type": event_type,
                                "from_version": version})
        result = fn(result)
        version += 1
    if validator is not None and not validator(result):
        raise ReleaseError("RELEASE_REPLAY_UPCAST_FAILED",
                           {"event_type": event_type, "stage": "output"})
    return result


def state_hash(state: dict) -> str:
    """规范化状态哈希：两次 Replay 相同输入必须逐字节相同（RULE-RELEASE-023）"""
    return sha256(canonical_json_bytes(state)).hexdigest()


def replay(snapshot: dict, event_tail: list[dict]) -> dict:
    """DES-RELEASE-007：从 Snapshot 状态起按 Revision 升序重放 Event tail

    纯函数：不修改入参；未知事件类型/upcast 失败即抛错停止（§7/§8：
    禁止跳过坏事件继续）。
    """
    state = {
        "state_tables": copy.deepcopy(snapshot["state_tables"]),
        "domain_projections": copy.deepcopy(snapshot.get("domain_projections", {})),
        "revision": snapshot["anchor_revision"],
        "game_time": snapshot["game_time"],
    }
    expected = snapshot["anchor_revision"] + 1
    for row in event_tail:
        if row["revision"] != expected:
            raise ReleaseError("RELEASE_EVENT_GAP_DETECTED",
                               {"expected": expected, "got": row["revision"]})
        event_type = row["event_type"]
        applier = EVENT_APPLIERS.get(event_type)
        if applier is None:
            raise ReleaseError("RELEASE_REPLAY_UNKNOWN_EVENT",
                               {"event_type": event_type})
        payload = json.loads(row["payload_json"])
        payload = upcast_payload(event_type, row["event_schema_version"], payload)
        applier(state, payload)
        state["revision"] = row["revision"]
        state["game_time"] = row["game_time"]
        expected += 1
    return state
