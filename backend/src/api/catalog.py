"""
REST 路由目录（DOC-BACKEND-004 DES-BACKEND-004）

- 端点目录与实现路由一一对应，无未登记路由（CI 路由清单比对）
- auth 列 canonical：anonymous_bootstrap / session_required / session_and_csrf_required
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

AUTH_BOOTSTRAP = "anonymous_bootstrap"
AUTH_SESSION = "session_required"
AUTH_SESSION_CSRF = "session_and_csrf_required"


@dataclass(frozen=True)
class RouteEntry:
    method: str
    path: str
    purpose: str
    request_schema: Optional[str]
    response_schema: str
    auth: str
    route_class: str


ROUTE_CATALOG: Tuple[RouteEntry, ...] = (
    RouteEntry("GET", "/api/v1/health", "进程健康与 Recovery Barrier 状态",
               None, "HealthStatusV1", AUTH_BOOTSTRAP, "health"),
    RouteEntry("GET", "/api/v1/meta", "应用版本、protocol_version、构建指纹",
               None, "AppMetaV1", AUTH_BOOTSTRAP, "health"),
    RouteEntry("POST", "/api/v1/session", "建立/刷新本地 Session Cookie",
               "SessionRequestV1", "SessionInfoV1", AUTH_BOOTSTRAP, "session"),
    RouteEntry("POST", "/api/v1/ws-tickets", "颁发单次 WebSocket Ticket",
               "WsTicketRequestV1", "WsTicketV1", AUTH_SESSION_CSRF, "ticket"),
    RouteEntry("GET", "/api/v1/worlds", "世界列表与元数据",
               None, "WorldListV1", AUTH_SESSION, "world-admin"),
    RouteEntry("POST", "/api/v1/worlds", "创建世界（Seed、模板）",
               "WorldCreateV1", "WorldSummaryV1", AUTH_SESSION_CSRF, "world-admin"),
    RouteEntry("GET", "/api/v1/worlds/{world_id}", "单世界详情",
               None, "WorldDetailV1", AUTH_SESSION, "world-admin"),
    RouteEntry("POST", "/api/v1/worlds/{world_id}/open", "打开世界（触发恢复序列）",
               "WorldOpenV1", "WorldRuntimeStateV1", AUTH_SESSION_CSRF, "world-admin"),
    RouteEntry("POST", "/api/v1/worlds/{world_id}/close", "关闭世界（Graceful Drain）",
               "WorldCloseV1", "WorldRuntimeStateV1", AUTH_SESSION_CSRF, "world-admin"),
    RouteEntry("DELETE", "/api/v1/worlds/{world_id}", "删除世界（需 Confirmation Token）",
               "WorldDeleteV1", "WorldDeleteResultV1", AUTH_SESSION_CSRF, "destructive"),
    RouteEntry("GET", "/api/v1/worlds/{world_id}/saves", "存档槽列表",
               None, "SaveSlotListV1", AUTH_SESSION, "save"),
    RouteEntry("POST", "/api/v1/worlds/{world_id}/saves", "写手动存档槽（覆盖需 Token）",
               "SaveWriteV1", "SaveSlotV1", AUTH_SESSION_CSRF, "save"),
    RouteEntry("POST", "/api/v1/worlds/{world_id}/saves/{save_id}/load",
               "从槽位加载（分支语义见 DOC-RELEASE-004）",
               "SaveLoadV1", "WorldRuntimeStateV1", AUTH_SESSION_CSRF, "save"),
    RouteEntry("GET", "/api/v1/settings", "非敏感设置读取",
               None, "SettingsV1", AUTH_SESSION, "settings"),
    RouteEntry("PUT", "/api/v1/settings", "非敏感设置写入",
               "SettingsV1", "SettingsV1", AUTH_SESSION_CSRF, "settings"),
    RouteEntry("PUT", "/api/v1/secrets/deepseek-api-key", "提交/替换 DeepSeek Key",
               "SecretPutV1", "SecretStatusV1", AUTH_SESSION_CSRF, "secret"),
    RouteEntry("GET", "/api/v1/secrets/deepseek-api-key/status", "Key 状态（masked）",
               None, "SecretStatusV1", AUTH_SESSION, "secret"),
    RouteEntry("DELETE", "/api/v1/secrets/deepseek-api-key", "删除 Key（需 Confirmation Token）",
               "SecretDeleteV1", "SecretStatusV1", AUTH_SESSION_CSRF, "destructive"),
    RouteEntry("POST", "/api/v1/confirmations", "颁发破坏性操作 Confirmation Token",
               "ConfirmationRequestV1", "ConfirmationTokenV1",
               AUTH_SESSION_CSRF, "destructive"),
    RouteEntry("POST", "/api/v1/diagnostics/package", "生成脱敏诊断包（Job）",
               "DiagnosticsRequestV1", "JobResourceV1", AUTH_SESSION_CSRF, "diagnostics"),
    RouteEntry("GET", "/api/v1/diagnostics/jobs/{job_id}", "轮询诊断 Job",
               None, "JobResourceV1", AUTH_SESSION, "diagnostics"),
    RouteEntry("GET", "/api/v1/diagnostics/metrics", "本地指标快照",
               None, "MetricsSnapshotV1", AUTH_SESSION, "diagnostics"),
)

#: 破坏性操作 → Confirmation action 名
DESTRUCTIVE_ACTIONS = {
    ("DELETE", "/api/v1/worlds/{world_id}"): "world.delete",
    ("DELETE", "/api/v1/secrets/deepseek-api-key"): "secret.delete",
}


def find_route(method: str, path: str) -> Optional[RouteEntry]:
    """路径模板匹配（{param} 单段通配）"""
    for entry in ROUTE_CATALOG:
        if entry.method != method:
            continue
        entry_parts = entry.path.strip("/").split("/")
        path_parts = path.strip("/").split("/")
        if len(entry_parts) != len(path_parts):
            continue
        if all(ep.startswith("{") or ep == pp for ep, pp in zip(entry_parts, path_parts)):
            return entry
    return None


def path_params(template: str, path: str) -> dict:
    params = {}
    for tp, pp in zip(template.strip("/").split("/"), path.strip("/").split("/")):
        if tp.startswith("{"):
            params[tp.strip("{}")] = pp
    return params


def audit_catalog() -> List[str]:
    """目录完整性：无重复、auth/Route Class 合法、Schema 命名一致"""
    gaps: List[str] = []
    seen = set()
    for entry in ROUTE_CATALOG:
        key = (entry.method, entry.path)
        if key in seen:
            gaps.append(f"duplicate:{key}")
        seen.add(key)
        if entry.auth not in (AUTH_BOOTSTRAP, AUTH_SESSION, AUTH_SESSION_CSRF):
            gaps.append(f"auth_invalid:{entry.path}")
        if not entry.path.startswith("/api/v1/"):
            gaps.append(f"path_prefix:{entry.path}")
        if not entry.response_schema.endswith("V1"):
            gaps.append(f"response_schema_version:{entry.path}")
    return gaps
