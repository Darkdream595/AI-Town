---
doc_id: DOC-DIALOGUE-010
title: 中文文案与文本渲染规范
version: 1.0.0
status: approved-for-implementation
owner_domain: dialogue
canonical_for:
  - dialogue-chinese-style
  - dialogue-text-as-data-rendering
depends_on:
  - DOC-FOUNDATION-004
  - DOC-DIALOGUE-005
  - DOC-PLAYER-005
requirements:
  - REQ-DIALOGUE-010
last_updated: 2026-07-26
---

# 中文文案与文本渲染规范

## 1. 目的

`REQ-DIALOGUE-010`：定义对话文本的中文书写规范（标点、术语、数字与单位、英文夹用）与「文本永远作为数据渲染」的强制策略，保证任何来源的对话文本——玩家输入、模型输出、系统文案——都以统一风格呈现且不可能作为标记语言或代码执行。

## 2. 非目标

本文不定义注入检测与恶意输入处置（`DOC-DIALOGUE-011`）、全局术语表内容（`DOC-FOUNDATION-004` 是 canonical owner）、UI 布局与字体资产（ART/UI 域）或玩家输入编译（`DOC-PLAYER-005`）。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Text-as-Data | 文本仅作为不可执行的字符串数据流经存储、传输与渲染的策略 |
| Sanitized Render | 渲染前的规范化处理：控制字符剥离、换行归一，不含任何标记解析 |
| Style Lint | 对系统文案与模型输出做的中文风格检查（标点、术语），只告警或修正呈现，不改写已提交 utterance |
| CJK Wrap | 中文逐字换行策略，禁止在标点前断行（避头尾规则） |

## 4. 规则与不变量

- `RULE-DIALOGUE-059`：全部对话文本按 Text-as-Data 渲染为纯文本节点：不解析 HTML、Markdown、BBCode、URL scheme 或转义序列，不执行任何脚本（与 `RULE-PLAYER-022` 同一立场，本条是对话渲染侧 canonical）。富文本效果（气泡、颜色、表情立绘）只能由结构化字段驱动（`DOC-DIALOGUE-006`），永不由文本内容触发。
- `RULE-DIALOGUE-060`：系统文案与模型输出的中文标点使用全角：`，。？！：；「」……——`；引语用直角引号「」，嵌套用『』；省略号用 `……` 不用 `...`；玩家输入不强制改写，仅在渲染时做 Sanitized Render。
- `RULE-DIALOGUE-061`：中英文混排在呈现层于中英边界插入间隔（渲染间距而非改写存储文本）；英文技术名、专有名词保留原文；数字与单位遵循 `RULE-FOUNDATION-045` 的字段单位规范，呈现层使用中文单位词（如「3 银冠」「10 游戏分钟」）。
- `RULE-DIALOGUE-062`：游戏内术语呈现以 `DOC-FOUNDATION-004` 术语表为唯一来源（如 silver_crown → 银冠、copper_feather → 铜羽）；Prompt 模板向模型声明同一术语表摘录，Style Lint 对模型输出中的术语漂移告警。
- `RULE-DIALOGUE-063`：Sanitized Render 固定为：剥离 C0/C1 控制字符（保留换行）、归一连续空白、按 NFC 归一化 Unicode、CJK Wrap 避头尾；处理只影响呈现，已提交 utterance 的存储字节不变（审计需要原文）。
- `RULE-DIALOGUE-064`：文本长度与显示约束：utterance 呈现每气泡上限 `140` 显示字符，超长文本分页显示不截断丢失；居民姓名、地名等标识文本不参与换行断字。

## 5. 数据与接口

`DES-DIALOGUE-010`：渲染投影载荷（WebSocket 推送给 Client 的对白帧）。

```json
{
  "schema_version": 1,
  "conversation_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "utterance_index": 7,
  "speaker_id": "01K1AB2CD3EF4GH5JK6MNP7QRV",
  "render_text": "这批矿石的成色不错……三十枚铜羽，成交吗？",
  "render_pages": 1,
  "text_encoding": "utf-8",
  "content_kind": "plain_text",
  "style_lint_flags": []
}
```

`content_kind` 恒为 `plain_text`（封闭单值枚举，为未来版本升级保留字段位，任何其他值 Client 必须拒绝渲染）；`style_lint_flags` 为告警码数组（如 `halfwidth_punctuation / glossary_drift`），仅供观测，不影响渲染。Client 渲染契约：`render_text` 只能进入文本节点 API（如 `textContent`），禁止进入任何 HTML 解析路径。

## 6. 正常流程

1. utterance 提交后，服务器执行 Sanitized Render 与 Style Lint，生成渲染投影。
2. Client 以纯文本节点渲染气泡，按 CJK Wrap 断行、按 `render_pages` 分页。
3. Prompt 模板（`resident-dialogue/v1`）内置中文风格指示与术语摘录，从源头降低 lint 告警率。
4. lint 告警进入观测面板，驱动 Prompt 模板迭代（发新版本，`RULE-AI-015`），不热改线上文本。

## 7. 边界情况

- 玩家输入半角标点或 emoji：原样存储、原样呈现（经 Sanitized Render）；风格规范只约束系统与模型文案。
- 模型输出夹带 `<b>`、`[url]`、`javascript:` 等标记：不违反 Schema（是合法字符串），按纯文本原样显示为字面字符——显示出来本身就是无害化。
- RTL 控制符、零宽字符（U+200B/U+200E/U+202E 等）：属 Sanitized Render 剥离范围，防止视觉欺骗（如伪装名字）。
- 超长单行无标点文本（刷屏攻击的温和形态）：强制按显示宽度断行分页，长度上限由 `RULE-DIALOGUE-031`（居民 280）与 `DOC-PLAYER-005` 玩家输入上限兜底。
- 术语表未收录的新名词：lint 不告警（开放世界文本自由），仅登记高频候选供术语表演进。

## 8. 错误与降级

- Style Lint 服务异常：跳过 lint 直接渲染（lint 是观测不是闸门）；Sanitized Render 异常则该 utterance 以占位气泡「（这段话无法显示）」呈现并告警，原文仍在存储中可审计。
- Client 收到未知 `content_kind`：拒绝渲染该帧并上报，不猜测降级为 HTML。

## 9. 安全与性能

- Text-as-Data 是 XSS/标记注入的结构性防御：不存在"过滤不全"问题，因为根本没有解析器；此策略与 `DOC-DIALOGUE-011` 的注入抵抗互为纵深。
- Sanitized Render 为单遍线性扫描，每 utterance 一次，服务器侧完成，Client 不重复实现规范化逻辑（避免两套实现分歧）。

## 10. 验收标准

- 含 HTML/脚本/控制符/RTL 的 fixture 全部以字面纯文本呈现，DOM 中无新增元素。
- 全角标点、直角引号、中英间距、避头尾在快照测试中稳定。
- 存储原文与渲染文本可逆对照：剥离项有审计记录。

## 11. 测试追踪

| 测试 ID | 覆盖规则 |
|---|---|
| `TEST-DIALOGUE-019` | `RULE-DIALOGUE-059`, `RULE-DIALOGUE-063..064` Text-as-Data、Sanitized Render、分页 |
| `TEST-DIALOGUE-020` | `RULE-DIALOGUE-060..062` 标点、混排、术语一致性 lint |

## 12. 关联文档

- `DOC-DIALOGUE-005`（文本来源与上限）、`DOC-DIALOGUE-006`（结构化呈现字段）、`DOC-DIALOGUE-011`（注入与内容边界）
- `DOC-FOUNDATION-004`（术语表 canonical）、`DOC-PLAYER-005`（玩家输入上限与纯文本约束）
