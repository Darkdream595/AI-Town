"""
中文文案与文本渲染规范（DOC-DIALOGUE-010）

- RULE-DIALOGUE-059：Text-as-Data，不解析任何标记
- RULE-DIALOGUE-060：系统/模型文案全角标点，直角引号
- RULE-DIALOGUE-061：中英混排间距、术语原文保留
- RULE-DIALOGUE-062：术语表唯一来源
- RULE-DIALOGUE-063：Sanitized Render 固定流程；存储原文不变
- RULE-DIALOGUE-064：每气泡 140 显示字符，分页不截断
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from .constants import MAX_RENDER_CHARS_PER_BUBBLE


class RenderingError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


#: RULE-DIALOGUE-063：剥离的字符类别（C0/C1 控制、RTL/零宽格式符），保留 \n
def _is_stripped(ch: str) -> bool:
    if ch == "\n":
        return False
    category = unicodedata.category(ch)
    return category in ("Cc", "Cf")


#: DOC-FOUNDATION-004 术语表摘录（RULE-DIALOGUE-062）
GLOSSARY: Dict[str, str] = {
    "silver_crown": "银冠",
    "copper_feather": "铜羽",
    "game_minutes": "游戏分钟",
}

#: CJK 避头尾：禁止出现在行首的标点
_CJK_NO_LINE_START = set("，。？！：；」』……——、）】")

_FULLWIDTH_PUNCTUATION = set("，。？！：；「」……——『』")
_HALFWIDTH_PATTERN = re.compile(r"[,?!:;](?=[\u4e00-\u9fff])|(?<=[\u4e00-\u9fff])[,?!:;]")


@dataclass(frozen=True)
class SanitizeAudit:
    """RULE-DIALOGUE-063/§10：剥离项审计记录（存储原文不变）"""

    stripped_codepoints: Tuple[str, ...]
    whitespace_normalized: bool


@dataclass(frozen=True)
class RenderProjection:
    """DES-DIALOGUE-010 渲染投影载荷"""

    conversation_id: str
    utterance_index: int
    speaker_id: str
    render_text: str
    render_pages: int
    style_lint_flags: Tuple[str, ...]
    content_kind: str = "plain_text"
    text_encoding: str = "utf-8"
    schema_version: int = 1

    def __post_init__(self) -> None:
        # §5：任何其他 content_kind Client 必须拒绝渲染
        if self.content_kind != "plain_text":
            raise RenderingError(
                "DIALOGUE_CONTENT_KIND_INVALID",
                f"content_kind must be plain_text, got {self.content_kind!r}",
            )


def sanitize_render(text: str) -> Tuple[str, SanitizeAudit]:
    """
    RULE-DIALOGUE-063：剥离控制字符（保留换行）、归一连续空白、NFC。

    返回 (渲染文本, 审计)；处理只影响呈现，存储字节由调用方保留。
    """
    stripped: List[str] = []
    kept: List[str] = []
    for ch in unicodedata.normalize("NFC", text):
        if _is_stripped(ch):
            stripped.append(f"U+{ord(ch):04X}")
        else:
            kept.append(ch)
    cleaned = "".join(kept)
    normalized = re.sub(r"[ \t]+", " ", cleaned)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
    audit = SanitizeAudit(
        stripped_codepoints=tuple(stripped),
        whitespace_normalized=normalized != cleaned,
    )
    return normalized, audit


def paginate(text: str) -> Tuple[str, int]:
    """
    RULE-DIALOGUE-064：每气泡 140 显示字符，分页不截断丢失。

    render_text 保持全文；页数供 Client 分页显示。
    """
    if not text:
        return text, 1
    pages = (len(text) + MAX_RENDER_CHARS_PER_BUBBLE - 1) // MAX_RENDER_CHARS_PER_BUBBLE
    return text, pages


def cjk_wrap_lines(text: str, width: int) -> List[str]:
    """
    RULE-DIALOGUE-063 CJK Wrap：逐字换行，标点前不断行（避头尾）。
    """
    lines: List[str] = []
    current = ""
    for ch in text:
        if ch == "\n":
            lines.append(current)
            current = ""
            continue
        if len(current) >= width:
            if ch in _CJK_NO_LINE_START:
                # 避头尾：标点不得出现在行首，并入上一行
                current += ch
                lines.append(current)
                current = ""
                continue
            lines.append(current)
            current = ch
        else:
            current += ch
    if current:
        lines.append(current)
    return lines


def style_lint(text: str, is_system_or_model: bool) -> Tuple[str, ...]:
    """
    RULE-DIALOGUE-060..062：只告警不改写；玩家输入不 lint。
    """
    if not is_system_or_model:
        return ()
    flags: List[str] = []
    if _HALFWIDTH_PATTERN.search(text):
        flags.append("halfwidth_punctuation")
    for term in GLOSSARY:
        # 术语漂移：应出现中文术语处出现原文键
        if re.search(rf"\b{re.escape(term)}\b", text):
            flags.append("glossary_drift")
            break
    return tuple(flags)


def build_render_projection(
    conversation_id: str,
    utterance_index: int,
    speaker_id: str,
    stored_text: str,
    is_system_or_model: bool,
) -> Tuple[RenderProjection, SanitizeAudit]:
    """utterance 提交后生成渲染投影（§6 第 1 步）"""
    sanitized, audit = sanitize_render(stored_text)
    render_text, pages = paginate(sanitized)
    flags = style_lint(render_text, is_system_or_model)
    projection = RenderProjection(
        conversation_id=conversation_id,
        utterance_index=utterance_index,
        speaker_id=speaker_id,
        render_text=render_text,
        render_pages=pages,
        style_lint_flags=flags,
    )
    return projection, audit
