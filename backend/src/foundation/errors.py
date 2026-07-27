"""
BACKEND 错误码注册表与统一错误对象（DOC-BACKEND-011）

- RULE-BACKEND-060：wire 上允许的 BACKEND_* 码以本注册表为唯一 canonical 列表
- RULE-BACKEND-061：错误对象统一 Schema：{schema_version, code, message,
  retryable, retry_after_ms, details}；message 面向用户、不含堆栈/路径/内部配置
"""

from __future__ import annotations

from typing import Dict, Optional


#: category ∈ protocol/auth/limit/conflict/backpressure/upstream/storage/internal/lifecycle
class ErrorSpec:
    __slots__ = ("code", "category", "http_status", "ws_behavior", "retryable",
                 "log_level", "message")

    def __init__(self, code: str, category: str, http_status: Optional[int],
                 ws_behavior: str, retryable: bool, log_level: str,
                 message: str) -> None:
        self.code = code
        self.category = category
        self.http_status = http_status
        #: ws_behavior ∈ error_frame / error_frame_close / close / none
        self.ws_behavior = ws_behavior
        self.retryable = retryable
        self.log_level = log_level
        self.message = message


ERROR_REGISTRY: Dict[str, ErrorSpec] = {spec.code: spec for spec in (
    ErrorSpec("BACKEND_BIND_REFUSED", "lifecycle", None, "none", False, "error",
              "绑定地址被拒绝。"),
    ErrorSpec("BACKEND_SCHEMA_INVALID", "protocol", 400, "error_frame", False, "info",
              "请求格式不正确。"),
    ErrorSpec("BACKEND_PROTOCOL_MISMATCH", "protocol", 400, "error_frame_close", False,
              "info", "协议版本不匹配，请刷新页面。"),
    ErrorSpec("BACKEND_NOT_FOUND", "protocol", 404, "error_frame", False, "info",
              "资源不存在。"),
    ErrorSpec("BACKEND_BODY_TOO_LARGE", "limit", 413, "error_frame_close", False,
              "info", "请求体过大。"),
    ErrorSpec("BACKEND_RATE_LIMITED", "limit", 429, "error_frame", True, "info",
              "请求过于频繁，请稍后重试。"),
    ErrorSpec("BACKEND_ORIGIN_REJECTED", "auth", 403, "close", False, "warning",
              "来源被拒绝。"),
    ErrorSpec("BACKEND_CSRF_REJECTED", "auth", 403, "none", False, "warning",
              "请求校验失败。"),
    ErrorSpec("BACKEND_SESSION_INVALID", "auth", 401, "error_frame_close", True,
              "info", "会话已失效，请重新进入。"),
    ErrorSpec("BACKEND_TICKET_INVALID", "auth", 401, "close", True, "info",
              "连接凭据无效。"),
    ErrorSpec("BACKEND_FORBIDDEN", "auth", 403, "error_frame", False, "warning",
              "没有执行该操作的权限。"),
    ErrorSpec("BACKEND_CONFIRMATION_REQUIRED", "auth", 428, "none", False, "info",
              "该操作需要二次确认。"),
    ErrorSpec("BACKEND_STALE_REVISION", "conflict", 409, "error_frame", False, "info",
              "世界状态已变化，请刷新后重试。"),
    ErrorSpec("BACKEND_IDEMPOTENCY_CONFLICT", "conflict", 409, "error_frame", False,
              "warning", "请求标识冲突。"),
    ErrorSpec("BACKEND_CONFLICT_STATE", "conflict", 409, "error_frame", True, "info",
              "当前状态不允许该操作。"),
    ErrorSpec("BACKEND_WS_SUPERSEDED", "lifecycle", None, "close", False, "info",
              "连接已被新连接取代。"),
    ErrorSpec("BACKEND_SNAPSHOT_REQUIRED", "lifecycle", None, "error_frame", True,
              "info", "需要全量同步。"),
    ErrorSpec("BACKEND_QUEUE_FULL", "backpressure", 503, "error_frame", True, "info",
              "服务器繁忙，请稍后重试。"),
    ErrorSpec("BACKEND_OVERLOADED", "backpressure", 503, "error_frame", True,
              "warning", "服务器负载过高。"),
    ErrorSpec("BACKEND_MODEL_UNAVAILABLE", "upstream", 503, "error_frame", True,
              "warning", "模型服务暂不可用。"),
    ErrorSpec("BACKEND_STORAGE_FAILURE", "storage", 503, "error_frame", False,
              "error", "存储暂时不可用。"),
    ErrorSpec("BACKEND_SHUTDOWN", "lifecycle", 503, "error_frame_close", True, "info",
              "服务器正在关闭。"),
    ErrorSpec("BACKEND_INTERNAL_INVARIANT", "internal", 500, "error_frame_close",
              False, "error", "服务器内部错误。"),
)}


def spec_of(code: str) -> ErrorSpec:
    spec = ERROR_REGISTRY.get(code)
    if spec is None:
        # 未注册码出现在构造路径属内部错误；对外统一兜底
        return ERROR_REGISTRY["BACKEND_INTERNAL_INVARIANT"]
    return spec


class ApiError(Exception):
    """携带注册错误码的异常；message 一律取注册表文案，不自由插值"""

    def __init__(self, code: str, details: Optional[dict] = None,
                 retry_after_ms: Optional[int] = None) -> None:
        spec = spec_of(code)
        super().__init__(spec.message)
        self.code = spec.code
        self.spec = spec
        self.details = dict(details) if details else None
        self.retry_after_ms = retry_after_ms

    def to_error_object(self) -> dict:
        obj = {
            "schema_version": 1,
            "code": self.code,
            "message": self.spec.message,
            "retryable": self.spec.retryable,
            "retry_after_ms": self.retry_after_ms,
            "details": self.details,
        }
        return obj

    def to_envelope(self) -> dict:
        return {"schema_version": 1, "error": self.to_error_object()}


def error_envelope(code: str, details: Optional[dict] = None,
                   retry_after_ms: Optional[int] = None) -> dict:
    return ApiError(code, details, retry_after_ms).to_envelope()


#: 预构造常量响应（错误对象自身序列化失败时的兜底，RULE-BACKEND-011 §7）
INTERNAL_INVARIANT_ENVELOPE = error_envelope("BACKEND_INTERNAL_INVARIANT")
