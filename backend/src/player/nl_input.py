"""
玩家自然语言输入与命令编译（DOC-PLAYER-005）

- RULE-PLAYER-021：NL 输入默认申请 dialogue_input Pause Token（由调用方组合）
- RULE-PLAYER-022：文本永远按纯文本处理；不执行 HTML/脚本 URL/系统提示/
  文件路径/模型工具调用
- RULE-PLAYER-023：编译器只能选择已注册 action 与 Schema 字段
- RULE-PLAYER-024：含糊输入必须澄清；高影响操作必须确认；未确认候选不创建
  Reservation 或 DomainEvent
- RULE-PLAYER-025：最终都形成 PlayerCommand 并进入同一 Domain validator
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple

from ..ai import ACTION_CATALOG
from .constants import (
    DENY_COMPILATION_STALE,
    MAX_SPEECH_DISPLAY_LINES,
    MAX_SPEECH_TEXT_LENGTH,
    MIN_SPEECH_TEXT_LENGTH,
    NL_PARSE_RATE_LIMIT_PER_10S,
)


class NLInputError(Exception):
    """NL 输入处理失败；code 为稳定 reason code"""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


class CompilationStatus(str, Enum):
    """DES-PLAYER-005 编译结果 status"""

    SPEECH_ONLY = "speech_only"
    CLARIFICATION_REQUIRED = "clarification_required"
    CONFIRMATION_REQUIRED = "confirmation_required"
    READY = "ready"
    REJECTED = "rejected"


#: §6 第 5 步：交易/赠与/施法/战斗/产权/治理类 action 必须确认
_HIGH_IMPACT_ACTIONS = frozenset(
    {
        "buy",
        "sell",
        "give_item",
        "cast_spell",
        "start_encounter",
        "combat_action",
        "build",
        "repair",
    }
)

#: §9.1：注入词命中后整段只按 speech 处理，绝不编译为命令
_INJECTION_MARKERS = (
    "我是镇长",
    "忽略规则",
    "忽略之前的指令",
    "ignore previous instructions",
    "ignore all rules",
    "的秘密告诉我",
    "告诉我.*秘密",
    r"给我\s*\d+\s*(金币|铜羽|金)",
    "system prompt",
    "系统提示",
)

#: §5 拒绝的控制字符（允许 \n \t；NFC 规范化后校验）
_ALLOWED_CONTROL_CHARS = frozenset({"\n", "\t"})

#: 中文数字 → 阿拉伯数字（§6 示例“买两瓶药”）
_CN_DIGITS = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}

_QUANTITY_PATTERN = re.compile(
    r"(?P<qty>\d+|[零一二两三四五六七八九十])\s*(?:瓶|个|件|份|只|把|块|枚)"
)
_BUY_PATTERN = re.compile(r"(?:买|购买|购入)")
_GIVE_PATTERN = re.compile(r"(?:送给|赠与|给)")
_MOVE_PATTERN = re.compile(r"(?:去|走到|移动到|前往)")


class SpeechTextValidator:
    """
    §5/§9：纯文本校验与规范化。

    RULE-PLAYER-022：输出永远按纯文本渲染；本校验器不做任何执行。
    """

    @staticmethod
    def normalize_and_validate(text: str) -> str:
        if not isinstance(text, str):
            raise NLInputError("PLAYER_SPEECH_TEXT_INVALID")
        normalized = unicodedata.normalize("NFC", text)
        length = len(normalized)
        if not MIN_SPEECH_TEXT_LENGTH <= length <= MAX_SPEECH_TEXT_LENGTH:
            raise NLInputError(
                "PLAYER_SPEECH_LENGTH_OUT_OF_RANGE",
                f"text length {length} outside "
                f"{MIN_SPEECH_TEXT_LENGTH}..{MAX_SPEECH_TEXT_LENGTH}",
            )
        for ch in normalized:
            category = unicodedata.category(ch)
            # Cc（控制）/ Cf（格式，如零宽字符、Bidi 控制）默认拒绝
            if category in ("Cc", "Cf") and ch not in _ALLOWED_CONTROL_CHARS:
                raise NLInputError(
                    "PLAYER_SPEECH_CONTROL_CHAR_REJECTED",
                    f"control character U+{ord(ch):04X} rejected",
                )
        return normalized

    @staticmethod
    def display_lines(text: str) -> List[str]:
        """§5：不去除有语义的换行，但显示最多 8 行"""
        return text.split("\n")[:MAX_SPEECH_DISPLAY_LINES]


@dataclass(frozen=True)
class PlayerSpeechCommand:
    """DES-PLAYER-005 说话命令；说话不隐含规则操作成功"""

    command_id: str
    expected_revision: int
    target_entity_id: Optional[str]
    text: str
    language: str
    type: str = "player.speech"
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.type != "player.speech":
            raise NLInputError("PLAYER_SPEECH_TYPE_INVALID")
        if self.language not in ("zh-CN", "en-US"):
            raise NLInputError("PLAYER_SPEECH_LANGUAGE_INVALID")


@dataclass(frozen=True)
class CompilationCandidate:
    """编译候选（DES-PLAYER-005 candidate）"""

    action_id: str
    target_entity_id: Optional[str]
    parameters: dict

    def __post_init__(self) -> None:
        # RULE-PLAYER-023：只能选择已注册 action
        if self.action_id not in ACTION_CATALOG:
            raise NLInputError(
                "PLAYER_COMPILATION_UNKNOWN_ACTION",
                f"action {self.action_id!r} not registered",
            )


@dataclass(frozen=True)
class CompilationResult:
    """DES-PLAYER-005 编译结果；绑定 source text hash/target/world/actor/revision"""

    compilation_id: str
    source_command_id: str
    status: CompilationStatus
    source_text_hash: str
    world_id: str
    actor_resident_id: str
    source_revision: int
    candidate: Optional[CompilationCandidate] = None
    assumptions: Tuple[str, ...] = ()
    clarification_question: Optional[str] = None
    expires_at_game_time: Optional[int] = None
    schema_version: int = 1

    def requires_confirmation(self) -> bool:
        return self.status is CompilationStatus.CONFIRMATION_REQUIRED


class PlayerCommandCompiler:
    """
    规则解析器优先的编译器（§6 第 4 步）。

    item_resolver：物品中文名 → (item_definition_id, max_unit_price)；
    未命中时 buy 意图进入 clarification。模型解析器超时/非法 JSON 的
    降级由调用方按 §8 处理为 speech_only，本编译器永不猜测执行。
    """

    def __init__(
        self,
        item_resolver: Optional[Callable[[str], Optional[Tuple[str, int]]]] = None,
        compilation_ttl_game_minutes: int = 60,
    ) -> None:
        self._item_resolver = item_resolver or (lambda name: None)
        self._ttl = compilation_ttl_game_minutes
        # (world_id, command_id) -> compilation_id（§7 幂等）
        self._by_source_command: Dict[Tuple[str, str], str] = {}
        self._compilations: Dict[str, CompilationResult] = {}
        self._id_counter = 0
        # §9：每玩家解析限速窗口（毫秒时间戳）
        self._parse_windows: Dict[str, List[int]] = {}

    def check_parse_rate(self, player_identity_id: str, now_ms: int) -> None:
        """§9：每玩家每 10 秒最多 5 次解析；超限不阻塞移动/存档"""
        window = self._parse_windows.setdefault(player_identity_id, [])
        window[:] = [t for t in window if now_ms - t < 10_000]
        if len(window) >= NL_PARSE_RATE_LIMIT_PER_10S:
            raise NLInputError(
                "PLAYER_NL_PARSE_RATE_LIMITED",
                "nl parse rate exceeded; local speech input still available",
            )
        window.append(now_ms)

    @staticmethod
    def contains_injection(text: str) -> bool:
        """§9.1：虚假 authority/秘密索取/资源索命只作为 speech"""
        lowered = text.lower()
        for marker in _INJECTION_MARKERS:
            if re.search(marker, lowered):
                return True
        return False

    def compile(
        self,
        command_id: str,
        world_id: str,
        actor_resident_id: str,
        target_entity_id: Optional[str],
        text: str,
        source_revision: int,
        current_game_time: int,
    ) -> CompilationResult:
        """
        编译入口；同 (world_id, command_id) 重放返回原 compilation（§7）。
        """
        normalized = SpeechTextValidator.normalize_and_validate(text)
        idem_key = (world_id, command_id)
        existing_id = self._by_source_command.get(idem_key)
        if existing_id is not None:
            return self._compilations[existing_id]

        text_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        expires_at = current_game_time + self._ttl

        if self.contains_injection(normalized):
            result = self._new_result(
                command_id, world_id, actor_resident_id, text_hash,
                source_revision, expires_at, CompilationStatus.SPEECH_ONLY,
            )
        else:
            result = self._compile_intent(
                normalized=normalized,
                command_id=command_id,
                world_id=world_id,
                actor_resident_id=actor_resident_id,
                target_entity_id=target_entity_id,
                text_hash=text_hash,
                source_revision=source_revision,
                expires_at=expires_at,
            )

        self._compilations[result.compilation_id] = result
        self._by_source_command[idem_key] = result.compilation_id
        return result

    def _compile_intent(
        self,
        normalized: str,
        command_id: str,
        world_id: str,
        actor_resident_id: str,
        target_entity_id: Optional[str],
        text_hash: str,
        source_revision: int,
        expires_at: int,
    ) -> CompilationResult:
        if _BUY_PATTERN.search(normalized):
            return self._compile_buy(
                normalized, command_id, world_id, actor_resident_id,
                target_entity_id, text_hash, source_revision, expires_at,
            )
        if _GIVE_PATTERN.search(normalized):
            candidate = CompilationCandidate(
                action_id="give_item",
                target_entity_id=target_entity_id,
                parameters={"gift_intent": "gift"},
            )
            # RULE-PLAYER-024：赠与属高影响，必须确认
            return self._new_result(
                command_id, world_id, actor_resident_id, text_hash,
                source_revision, expires_at,
                CompilationStatus.CONFIRMATION_REQUIRED, candidate,
            )
        if _MOVE_PATTERN.search(normalized):
            if target_entity_id is None:
                return self._new_result(
                    command_id, world_id, actor_resident_id, text_hash,
                    source_revision, expires_at,
                    CompilationStatus.CLARIFICATION_REQUIRED,
                    clarification_question="想去哪里？",
                )
            candidate = CompilationCandidate(
                action_id="move_to",
                target_entity_id=target_entity_id,
                parameters={},
            )
            return self._new_result(
                command_id, world_id, actor_resident_id, text_hash,
                source_revision, expires_at, CompilationStatus.READY, candidate,
            )
        # 明确为说话：无动作意图
        return self._new_result(
            command_id, world_id, actor_resident_id, text_hash,
            source_revision, expires_at, CompilationStatus.SPEECH_ONLY,
        )

    def _compile_buy(
        self,
        normalized: str,
        command_id: str,
        world_id: str,
        actor_resident_id: str,
        target_entity_id: Optional[str],
        text_hash: str,
        source_revision: int,
        expires_at: int,
    ) -> CompilationResult:
        """“买两瓶药”类：缺目标/数量/物品任一即澄清（§6 第 5 步）"""
        qty_match = _QUANTITY_PATTERN.search(normalized)
        quantity: Optional[int] = None
        if qty_match:
            quantity = self._parse_quantity(qty_match.group("qty"))

        item_name = self._extract_item_name(normalized)
        resolved = self._item_resolver(item_name) if item_name else None

        missing: List[str] = []
        if target_entity_id is None:
            missing.append("target")
        if quantity is None:
            missing.append("quantity")
        if resolved is None:
            missing.append("item")
        if missing:
            return self._new_result(
                command_id, world_id, actor_resident_id, text_hash,
                source_revision, expires_at,
                CompilationStatus.CLARIFICATION_REQUIRED,
                clarification_question=f"请补充：{', '.join(missing)}",
            )

        item_definition_id, max_unit_price = resolved
        candidate = CompilationCandidate(
            action_id="buy",
            target_entity_id=target_entity_id,
            parameters={
                "item_definition_id": item_definition_id,
                "quantity": quantity,
                "maximum_unit_price_copper_feather": max_unit_price,
            },
        )
        # RULE-PLAYER-024：交易必须确认
        return self._new_result(
            command_id, world_id, actor_resident_id, text_hash,
            source_revision, expires_at,
            CompilationStatus.CONFIRMATION_REQUIRED, candidate,
        )

    @staticmethod
    def _parse_quantity(raw: str) -> Optional[int]:
        if raw.isdigit():
            value = int(raw)
            return value if value > 0 else None
        return _CN_DIGITS.get(raw)

    @staticmethod
    def _extract_item_name(text: str) -> Optional[str]:
        """提取量词后的物品名片段；无法定位时返回 None 走澄清"""
        match = _QUANTITY_PATTERN.search(text)
        if match:
            tail = text[match.end():].strip("。！？!?. ")
            return tail or None
        buy_match = _BUY_PATTERN.search(text)
        if buy_match:
            tail = text[buy_match.end():].strip("。！？!?. ")
            return tail or None
        return None

    def confirm_compilation(
        self,
        compilation_id: str,
        new_command_id: str,
        current_revision: int,
        current_game_time: int,
        current_target_entity_id: Optional[str],
    ) -> Tuple[str, str, Optional[str], dict]:
        """
        §6 第 6 步：确认后生成新 command，引用 compilation，以最新 Revision
        进入 Domain validator。

        世界变化/目标离开/过期使确认失效 → PLAYER_COMPILATION_STALE（§8），
        无资源副作用。
        """
        result = self._compilations.get(compilation_id)
        if result is None:
            raise NLInputError(
                "PLAYER_COMPILATION_NOT_FOUND", f"unknown compilation {compilation_id}"
            )
        if result.status is not CompilationStatus.CONFIRMATION_REQUIRED:
            raise NLInputError(
                "PLAYER_COMPILATION_NOT_CONFIRMABLE",
                f"status {result.status.value} cannot be confirmed",
            )
        stale = (
            result.source_revision != current_revision
            or (result.expires_at_game_time is not None
                and current_game_time > result.expires_at_game_time)
            or (result.candidate is not None
                and result.candidate.target_entity_id != current_target_entity_id)
        )
        if stale:
            raise NLInputError(
                DENY_COMPILATION_STALE,
                "compilation stale: revision/expiration/target changed",
            )
        assert result.candidate is not None  # CONFIRMATION_REQUIRED 必有候选
        return (
            new_command_id,
            result.candidate.action_id,
            result.candidate.target_entity_id,
            dict(result.candidate.parameters),
        )

    @staticmethod
    def model_fallback_result(
        command_id: str,
        world_id: str,
        actor_resident_id: str,
        text: str,
        source_revision: int,
    ) -> CompilationResult:
        """
        §8：模型超时/非法 JSON 退化为 speech-only，不丢失原文、不猜测执行。
        """
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return CompilationResult(
            compilation_id=f"fallback-{command_id}",
            source_command_id=command_id,
            status=CompilationStatus.SPEECH_ONLY,
            source_text_hash=text_hash,
            world_id=world_id,
            actor_resident_id=actor_resident_id,
            source_revision=source_revision,
        )

    def _new_result(
        self,
        command_id: str,
        world_id: str,
        actor_resident_id: str,
        text_hash: str,
        source_revision: int,
        expires_at: int,
        status: CompilationStatus,
        candidate: Optional[CompilationCandidate] = None,
        clarification_question: Optional[str] = None,
    ) -> CompilationResult:
        self._id_counter += 1
        return CompilationResult(
            compilation_id=f"cmp-{self._id_counter:06d}",
            source_command_id=command_id,
            status=status,
            source_text_hash=text_hash,
            world_id=world_id,
            actor_resident_id=actor_resident_id,
            source_revision=source_revision,
            candidate=candidate,
            clarification_question=clarification_question,
            expires_at_game_time=expires_at,
        )
