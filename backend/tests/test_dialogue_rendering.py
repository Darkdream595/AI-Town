"""
TEST-DIALOGUE-019/020：中文文案与文本渲染规范（DOC-DIALOGUE-010）

- TEST-DIALOGUE-019：RULE-DIALOGUE-063 控制符/RTL/零宽剥离、审计与原文保留边界
- TEST-DIALOGUE-020：RULE-DIALOGUE-060/061/062/064 分页、CJK 避头尾、lint 与术语漂移
"""

import pytest

from src.dialogue import (
    GLOSSARY,
    RenderProjection,
    RenderingError,
    build_render_projection,
    cjk_wrap_lines,
    paginate,
    sanitize_render,
    style_lint,
)
from src.dialogue.constants import MAX_RENDER_CHARS_PER_BUBBLE

from ai_helpers import ULID_A

CONV = "01K1CVRX000000000000000001"


class TestSanitizeRender:
    """TEST-DIALOGUE-019"""

    def test_control_characters_stripped_with_audit(self):
        cleaned, audit = sanitize_render("你好\x00世界\x07。")
        assert cleaned == "你好世界。"
        assert audit.stripped_codepoints == ("U+0000", "U+0007")

    def test_rtl_override_and_zero_width_stripped(self):
        cleaned, audit = sanitize_render("abc‮def​ghi")
        assert cleaned == "abcdefghi"
        assert "U+202E" in audit.stripped_codepoints
        assert "U+200B" in audit.stripped_codepoints

    def test_newline_preserved_whitespace_normalized(self):
        cleaned, _ = sanitize_render("第一行\n第二行")
        assert cleaned == "第一行\n第二行"
        cleaned, audit = sanitize_render("很  \t 远")
        assert cleaned == "很 远"
        assert audit.whitespace_normalized is True

    def test_excess_blank_lines_collapsed(self):
        cleaned, _ = sanitize_render("上\n\n\n\n下")
        assert cleaned == "上\n\n下"

    def test_nfc_normalization(self):
        cleaned, _ = sanitize_render("é")
        assert cleaned == "é"
        assert len(cleaned) == 1

    def test_clean_text_needs_no_normalization(self):
        cleaned, audit = sanitize_render("今天集市真热闹。")
        assert cleaned == "今天集市真热闹。"
        assert audit.stripped_codepoints == ()
        assert audit.whitespace_normalized is False


class TestPaginationAndWrap:
    """TEST-DIALOGUE-020（分页与 CJK 换行部分）"""

    def test_pagination_never_truncates(self):
        text = "字" * 281
        render_text, pages = paginate(text)
        assert render_text == text  # 全文保留，分页只给页数
        assert pages == 3

    @pytest.mark.parametrize(
        "length,expected_pages",
        [(0, 1), (1, 1), (140, 1), (141, 2), (280, 2), (281, 3)],
    )
    def test_page_count_boundaries(self, length, expected_pages):
        assert MAX_RENDER_CHARS_PER_BUBBLE == 140
        _, pages = paginate("字" * length)
        assert pages == expected_pages

    def test_cjk_wrap_avoids_line_start_punctuation(self):
        lines = cjk_wrap_lines("你好世界，好", 4)
        assert lines[0] == "你好世界，"  # 避头尾：标点并入上一行
        assert lines[1] == "好"
        for line in lines[1:]:
            assert not line.startswith(("，", "。", "？", "！"))

    def test_cjk_wrap_plain_and_newline(self):
        assert cjk_wrap_lines("abcdef", 3) == ["abc", "def"]
        assert cjk_wrap_lines("ab\ncd", 5) == ["ab", "cd"]


class TestStyleLint:
    """TEST-DIALOGUE-020（lint 与术语部分）"""

    def test_halfwidth_punctuation_flagged_for_model_text(self):
        assert style_lint("你好,世界。", is_system_or_model=True) == ("halfwidth_punctuation",)

    def test_glossary_drift_flagged(self):
        assert "silver_crown" in GLOSSARY
        assert style_lint("价格是一个 silver_crown。", is_system_or_model=True) == ("glossary_drift",)

    def test_both_flags_reported(self):
        flags = style_lint("你说,silver_crown 值钱吗", is_system_or_model=True)
        assert flags == ("halfwidth_punctuation", "glossary_drift")

    def test_fullwidth_clean_text_passes(self):
        assert style_lint("你好，世界。", is_system_or_model=True) == ()

    def test_player_input_not_linted(self):
        assert style_lint("你好,world", is_system_or_model=False) == ()


class TestRenderProjection:
    """TEST-DIALOGUE-019/020（投影组装）"""

    def test_projection_pipeline(self):
        projection, audit = build_render_projection(
            CONV, 0, ULID_A, "你好\x00,世界" + "字" * 200, is_system_or_model=True
        )
        assert projection.content_kind == "plain_text"
        assert "\x00" not in projection.render_text
        assert audit.stripped_codepoints == ("U+0000",)
        assert projection.render_pages == 2
        assert "halfwidth_punctuation" in projection.style_lint_flags
        assert projection.text_encoding == "utf-8"

    def test_player_utterance_projection_skips_lint(self):
        projection, _ = build_render_projection(
            CONV, 0, ULID_A, "你好,world", is_system_or_model=False
        )
        assert projection.style_lint_flags == ()

    def test_non_plain_text_content_kind_rejected(self):
        with pytest.raises(RenderingError) as excinfo:
            RenderProjection(
                conversation_id=CONV,
                utterance_index=0,
                speaker_id=ULID_A,
                render_text="<b>hi</b>",
                render_pages=1,
                style_lint_flags=(),
                content_kind="html",
            )
        assert excinfo.value.code == "DIALOGUE_CONTENT_KIND_INVALID"
