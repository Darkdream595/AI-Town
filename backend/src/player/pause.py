"""
Pause Token Ledger（PLAYER 编排侧的最小组合实现）

DOC-PLAYER-003/005 引用 DOC-TIME-002 的 Pause Token Ledger；TIME 域尚未提供
可复用实现，因此这里实现 PLAYER 需要的组合语义：token 按 (owner, reason)
归属，世界在任一 blocking token 存续期间保持暂停；释放只针对持有者自己的
token（RULE-PLAYER-013/021）。当 TIME 域提供 canonical ledger 时，此实现
应被替换为对 TIME 的调用，PLAYER 不拥有暂停规则本身。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..foundation import generate_ulid


class PauseTokenError(Exception):
    """Pause token 操作失败；message 为稳定 reason code"""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True)
class PauseToken:
    """Pause Token（DOC-TIME-002 语义子集）"""

    token_id: str
    world_id: str
    owner: str  # player / dialogue / combat / shutdown ...
    reason: str  # mayor_management / dialogue_input ...
    acquired_by_command_id: str
    acquired_revision: int


@dataclass
class PauseTokenLedger:
    """
    每世界一个 ledger；blocking token 的并集决定世界是否暂停。

    幂等键为 (world_id, command_id)：重复 acquire 返回原 token，
    不同 owner/reason 的同 key 请求视为冲突。
    """

    world_id: str
    _tokens: Dict[str, PauseToken] = field(default_factory=dict)
    _acquire_idempotency: Dict[Tuple[str, str], str] = field(default_factory=dict)
    _release_idempotency: Dict[Tuple[str, str], str] = field(default_factory=dict)

    def acquire(
        self,
        command_id: str,
        owner: str,
        reason: str,
        revision: int,
    ) -> PauseToken:
        """获取 blocking token；同 (world_id, command_id) 重放返回原 token"""
        key = (self.world_id, command_id)
        existing_id = self._acquire_idempotency.get(key)
        if existing_id is not None:
            existing = self._tokens.get(existing_id)
            if existing is None:
                # token 已释放：重放 acquire 不复活已释放的暂停
                raise PauseTokenError(
                    "PAUSE_TOKEN_ALREADY_RELEASED",
                    f"token for command {command_id} was released",
                )
            if existing.owner != owner or existing.reason != reason:
                raise PauseTokenError(
                    "PAUSE_ACQUIRE_PAYLOAD_CONFLICT",
                    "same command_id with different owner/reason",
                )
            return existing

        token = PauseToken(
            token_id=generate_ulid(),
            world_id=self.world_id,
            owner=owner,
            reason=reason,
            acquired_by_command_id=command_id,
            acquired_revision=revision,
        )
        self._tokens[token.token_id] = token
        self._acquire_idempotency[key] = token.token_id
        return token

    def release(self, command_id: str, token_id: str, owner: str) -> PauseToken:
        """
        释放 token；只有持有者 owner 可以释放（RULE-PLAYER-013）。

        重复 release（同 command_id）幂等返回原 token。
        """
        key = (self.world_id, command_id)
        if key in self._release_idempotency:
            prior_token_id = self._release_idempotency[key]
            if prior_token_id != token_id:
                raise PauseTokenError(
                    "PAUSE_RELEASE_PAYLOAD_CONFLICT",
                    "same command_id releasing different token",
                )
            # 已释放：幂等成功，返回历史 token 快照不可得时构造最小应答
            token = self._tokens.get(token_id)
            if token is not None:
                return token
            return PauseToken(
                token_id=token_id,
                world_id=self.world_id,
                owner=owner,
                reason="",
                acquired_by_command_id="",
                acquired_revision=0,
            )

        token = self._tokens.get(token_id)
        if token is None:
            raise PauseTokenError(
                "PAUSE_TOKEN_NOT_FOUND", f"unknown token {token_id}"
            )
        if token.owner != owner:
            # 不能解除 Dialogue/Combat/Shutdown 或其他 owner 的 token
            raise PauseTokenError(
                "PAUSE_TOKEN_OWNER_MISMATCH",
                f"token owned by {token.owner}, not {owner}",
            )

        del self._tokens[token_id]
        self._release_idempotency[key] = token_id
        return token

    def force_release_orphan(self, token_id: str) -> Optional[PauseToken]:
        """
        Recovery Barrier 审计后按 owner 证据释放孤儿 token（DOC-PLAYER-003 §8）。

        只有恢复编排可调用；返回被释放的 token。
        """
        return self._tokens.pop(token_id, None)

    def is_paused(self) -> bool:
        """任一 blocking token 存续即暂停"""
        return bool(self._tokens)

    def active_tokens(self) -> List[PauseToken]:
        return list(self._tokens.values())

    def has_token(self, token_id: str) -> bool:
        return token_id in self._tokens

    def tokens_by_owner(self, owner: str) -> List[PauseToken]:
        return [t for t in self._tokens.values() if t.owner == owner]
