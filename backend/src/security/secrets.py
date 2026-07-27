"""
DeepSeek Key 保护（DOC-BACKEND-009）

- RULE-BACKEND-049：Key 只经 secret 路由提交；状态查询只返回 configured、
  Masked Suffix 与最近验证结果，任何响应不回显明文
- RULE-BACKEND-050：存储 = Windows Credential Manager 或 DPAPI 加密文件（二选一，
  无第三种持久化形式）；测试注入内存后端，绝不触碰真实凭据管理器
- RULE-BACKEND-052：security/ 之外只流通 opaque Credential Ref；
  AuthHeaderHandle 一次性，注入单个请求后即失效
- RULE-BACKEND-054：set/verify/delete 全审计；delete 立即使全部 ref 失效
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Protocol

from ..foundation.errors import ApiError
from .redaction import RedactionFilter, fingerprint_of

SECRET_KIND_DEEPSEEK = "deepseek_api_key"
SECRET_KINDS = frozenset({SECRET_KIND_DEEPSEEK})
WCM_TARGET = "AI-Town/deepseek-api-key"

VERIFY_RESULTS = frozenset({"ok", "unauthorized", "network_error", "not_verified"})


# ---------------------------------------------------------------------------
# Secret Store 后端（port + 各实现）
# ---------------------------------------------------------------------------


class SecretStoreBackend(Protocol):
    backend_name: str

    def write(self, target: str, plaintext: str) -> None: ...
    def read(self, target: str) -> Optional[str]: ...
    def delete(self, target: str) -> None: ...


class MemorySecretStore:
    """测试/开发后端：不落盘；生产由 bootstrap 装配 WCM → DPAPI 链"""

    backend_name = "memory"

    def __init__(self) -> None:
        self._data: Dict[str, str] = {}

    def write(self, target: str, plaintext: str) -> None:
        self._data[target] = plaintext

    def read(self, target: str) -> Optional[str]:
        return self._data.get(target)

    def delete(self, target: str) -> None:
        self._data.pop(target, None)


class WindowsCredentialManagerStore:
    """Windows Credential Manager Generic Credential（per-user）"""

    backend_name = "windows_credential_manager"

    def write(self, target: str, plaintext: str) -> None:
        _wcm_write(target, plaintext)

    def read(self, target: str) -> Optional[str]:
        return _wcm_read(target)

    def delete(self, target: str) -> None:
        _wcm_delete(target)


class DpapiFileStore:
    """DPAPI（CRYPTPROTECT_UI_FORBIDDEN, per-user）加密文件后端"""

    backend_name = "dpapi_file"

    def __init__(self, file_path: str) -> None:
        self._file_path = file_path

    def write(self, target: str, plaintext: str) -> None:
        blob = _dpapi_protect(plaintext.encode("utf-8"))
        with open(self._file_path, "wb") as handle:
            handle.write(blob)

    def read(self, target: str) -> Optional[str]:
        try:
            with open(self._file_path, "rb") as handle:
                blob = handle.read()
        except OSError:
            return None
        return _dpapi_unprotect(blob).decode("utf-8")

    def delete(self, target: str) -> None:
        import os
        try:
            os.remove(self._file_path)
        except OSError:
            pass


def _wcm_write(target: str, plaintext: str) -> None:  # pragma: no cover - 系统调用
    import ctypes
    from ctypes import wintypes

    class CREDENTIAL(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME), ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
            ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p), ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    blob = plaintext.encode("utf-16-le")
    buffer = ctypes.create_string_buffer(blob, len(blob))
    credential = CREDENTIAL(
        0, 1, target, None, wintypes.FILETIME(0, 0), len(blob),
        ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)), 2, 0, None, None, None,
    )
    if not ctypes.windll.advapi32.CredWriteW(ctypes.byref(credential), 0):
        raise OSError("CredWriteW failed")


def _wcm_read(target: str) -> Optional[str]:  # pragma: no cover - 系统调用
    import ctypes

    pointer = ctypes.c_void_p()
    if not ctypes.windll.advapi32.CredReadW(target, 1, 0, ctypes.byref(pointer)):
        return None
    try:
        size = ctypes.cast(pointer.value + 16, ctypes.POINTER(ctypes.c_uint32)).contents.value
        blob_pointer = ctypes.cast(pointer.value + 24, ctypes.POINTER(ctypes.c_void_p)).contents.value
        blob = ctypes.string_at(blob_pointer, size)
        return blob.decode("utf-16-le")
    finally:
        ctypes.windll.advapi32.CredFree(pointer)


def _wcm_delete(target: str) -> None:  # pragma: no cover - 系统调用
    import ctypes
    ctypes.windll.advapi32.CredDeleteW(target, 1, 0)


def _dpapi_protect(data: bytes) -> bytes:  # pragma: no cover - 系统调用
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.c_void_p)]

    in_blob = DATA_BLOB(len(data), ctypes.cast(ctypes.create_string_buffer(data, len(data)),
                                              ctypes.c_void_p))
    out_blob = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(in_blob), None, None, None, None, 0x10,
            ctypes.byref(out_blob)):  # CRYPTPROTECT_UI_FORBIDDEN
        raise OSError("CryptProtectData failed")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def _dpapi_unprotect(blob: bytes) -> bytes:  # pragma: no cover - 系统调用
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.c_void_p)]

    in_blob = DATA_BLOB(len(blob), ctypes.cast(ctypes.create_string_buffer(blob, len(blob)),
                                              ctypes.c_void_p))
    out_blob = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(in_blob), None, None, None, None, 0x10,
            ctypes.byref(out_blob)):
        raise OSError("CryptUnprotectData failed")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


class ChainedSecretStore:
    """首选 WCM，不可用降级 DPAPI 文件；双后端均不可用 → BACKEND_STORAGE_FAILURE"""

    def __init__(self, backends: List[SecretStoreBackend]) -> None:
        self._backends = list(backends)
        self._active: Optional[SecretStoreBackend] = None

    def _pick(self) -> SecretStoreBackend:
        if self._active is not None:
            return self._active
        errors = []
        for backend in self._backends:
            try:
                backend.write("__probe__", "probe")
                backend.delete("__probe__")
                self._active = backend
                return backend
            except Exception as exc:  # noqa: BLE001 - 后端探测失败尝试下一个
                errors.append(f"{backend.backend_name}: {exc}")
        raise ApiError("BACKEND_STORAGE_FAILURE",
                       {"reason_code": "secret_store_unavailable"})

    @property
    def backend_name(self) -> str:
        return self._pick().backend_name

    def write(self, target: str, plaintext: str) -> None:
        self._pick().write(target, plaintext)

    def read(self, target: str) -> Optional[str]:
        return self._pick().read(target)

    def delete(self, target: str) -> None:
        self._pick().delete(target)


# ---------------------------------------------------------------------------
# Credential Ref 与一次性 AuthHeaderHandle
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CredentialRef:
    ref_id: str
    kind: str
    generation: int


class AuthHeaderHandle:
    """一次性对象：header() 调用一次后即失效（RULE-BACKEND-052 单请求持有）"""

    def __init__(self, header_factory: Callable[[], Dict[str, str]]) -> None:
        self._factory = header_factory
        self._used = False

    def header(self) -> Dict[str, str]:
        if self._used:
            raise ApiError("BACKEND_INTERNAL_INVARIANT",
                           {"reason_code": "auth_header_handle_reused"})
        self._used = True
        return self._factory()


# ---------------------------------------------------------------------------
# Secret Service
# ---------------------------------------------------------------------------


@dataclass
class _SecretEntry:
    kind: str
    masked_suffix: str
    fingerprint: str
    generation: int = 0
    last_verified_at: Optional[str] = None
    last_verify_result: str = "not_verified"


class SecretService:
    def __init__(self, store: SecretStoreBackend,
                 redaction: RedactionFilter,
                 id_factory: Callable[[], str],
                 audit: Optional[Callable[[dict], None]] = None,
                 utc_now: Optional[Callable[[], str]] = None) -> None:
        self._store = store
        self._redaction = redaction
        self._id_factory = id_factory
        self._audit = audit or (lambda _event: None)
        self._utc_now = utc_now or (lambda: "")
        self._entries: Dict[str, _SecretEntry] = {}

    def _target(self, kind: str) -> str:
        return f"AI-Town/{kind.replace('_', '-')}"

    def _emit(self, action: str, entry: Optional[_SecretEntry], result: str) -> None:
        self._audit({
            "action": action,
            "masked_suffix": entry.masked_suffix if entry else None,
            "fingerprint": entry.fingerprint if entry else None,
            "result": result,
            "timestamp": self._utc_now(),
        })

    # -- 生命周期 ---------------------------------------------------------------

    def set_secret(self, kind: str, plaintext: str) -> dict:
        if kind not in SECRET_KINDS:
            raise ApiError("BACKEND_SCHEMA_INVALID", {"reason_code": "secret_kind_unknown"})
        trimmed = (plaintext or "").strip()
        if not trimmed:
            raise ApiError("BACKEND_SCHEMA_INVALID", {"reason_code": "secret_empty"})
        self._store.write(self._target(kind), trimmed)
        fingerprint = self._redaction.register_secret_value(trimmed)
        previous = self._entries.get(kind)
        entry = _SecretEntry(
            kind=kind,
            masked_suffix=trimmed[-4:],
            fingerprint=fingerprint,
            generation=(previous.generation + 1) if previous else 1,
        )
        self._entries[kind] = entry
        self._emit("set", entry, "ok")
        return self.status(kind)

    def get_credential_ref(self, kind: str) -> Optional[CredentialRef]:
        entry = self._entries.get(kind)
        if entry is None:
            return None
        return CredentialRef(ref_id=self._id_factory(), kind=kind,
                             generation=entry.generation)

    def resolve_for_request(self, ref: CredentialRef) -> AuthHeaderHandle:
        """仅 ModelProvider adapter 调用；ref 失效（delete/换 Key）即拒绝"""
        entry = self._entries.get(ref.kind)
        if entry is None or entry.generation != ref.generation:
            raise ApiError("BACKEND_FORBIDDEN", {"reason_code": "credential_ref_stale"})
        store = self._store
        target = self._target(ref.kind)

        def build_header() -> Dict[str, str]:
            plaintext = store.read(target)
            if plaintext is None:
                raise ApiError("BACKEND_STORAGE_FAILURE",
                               {"reason_code": "secret_read_failed"})
            return {"Authorization": f"Bearer {plaintext}"}

        return AuthHeaderHandle(build_header)

    def record_verify(self, kind: str, result: str) -> dict:
        if result not in VERIFY_RESULTS - {"not_verified"}:
            raise ApiError("BACKEND_SCHEMA_INVALID", {"reason_code": "verify_result_invalid"})
        entry = self._entries.get(kind)
        if entry is None:
            raise ApiError("BACKEND_NOT_FOUND", {"reason_code": "secret_not_configured"})
        entry.last_verify_result = result
        entry.last_verified_at = self._utc_now()
        self._emit("verify", entry, result)
        return self.status(kind)

    def delete_secret(self, kind: str) -> dict:
        entry = self._entries.pop(kind, None)
        self._store.delete(self._target(kind))
        self._emit("delete", entry, "ok")
        return self.status(kind)

    # -- 状态 ----------------------------------------------------------------

    def status(self, kind: str) -> dict:
        entry = self._entries.get(kind)
        return {
            "schema_version": 1,
            "secret_kind": kind,
            "configured": entry is not None,
            "storage_backend": self._store.backend_name if entry else None,
            "masked_suffix": entry.masked_suffix if entry else None,
            "last_verified_at": entry.last_verified_at if entry else None,
            "last_verify_result": entry.last_verify_result if entry else "not_verified",
        }
