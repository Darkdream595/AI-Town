---
doc_id: DOC-MAGIC-011
title: 魔法 VFX 与音频
version: 1.0.0
status: approved-for-implementation
owner_domain: magic
canonical_for:
  - magic-presentation-mapping
depends_on:
  - DOC-MAGIC-004
  - DOC-RENDER-008
  - DOC-RENDER-010
  - DOC-WORLD-009
requirements:
  - REQ-MAGIC-021
  - REQ-MAGIC-022
last_updated: 2026-07-26
---

# 魔法 VFX 与音频

## 1. 目的

定义 `presentation_id`（`magic.presentation.*`）到 RENDER VFX/音频注册项的映射注册表与降级链，使每个法术的表现可枚举、可替换、可降级，且表现层永远不承载规则事实。

## 2. 非目标

本文件不定义 VFX 的播放生命周期、对象池与可访问性（`DOC-RENDER-008` 拥有 `RULE-RENDER-022..024`）、音频总线与授权（`DOC-RENDER-010/011`）、美术风格裁定（`DOC-WORLD-009`）。MAGIC 不向 RENDER 导出任何 Spell/effect Schema（`DOC-RENDER-008` §5 的边界）。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| `presentation_id` | `SpellDefinition` 引用的表现注册项 ID |
| VFX 家族 | 学派级视觉前缀 `vfx.<school>.*`（`DES-MAGIC-002` `vfx_family`） |
| 施法音效 | `audio.sfx.magic.*` 的 one-shot 资产引用 |
| 降级链 | 表现缺失时的逐级替代：家族默认 → `vfx.fallback.status_ping` |

## 4. 规则与不变量

| ID | 规则 |
|---|---|
| `REQ-MAGIC-021` | 每个 `presentation_id` 声明 `cast_vfx_id/impact_vfx_id/cast_audio_id`，全部解析到 RENDER 注册表；`vfx_id` 必须属于该法术学派的 `vfx_family` 前缀，构建期校验。 |
| `REQ-MAGIC-022` | 表现只由已提交事件的 `render` projection 驱动（`RULE-RENDER-022`）；表现播放失败、降级或被 Reduced Motion 替换不影响任何已提交效果，规则层不读取表现状态。 |
| `RULE-MAGIC-059` | 视觉基调服从 `REQ-MAGIC-002` 与 `DOC-WORLD-009`：单个法术 VFX `duration_ms` 遵守 RENDER 的 `100..1500` 界限，禁止全屏遮罩类施法特效（Reduced Motion 语义之外的全屏闪光一律不注册）。 |
| `RULE-MAGIC-060` | 持续效果实例（光照、幻象、锚点）使用循环环境表现而非重复 one-shot；其表现随 `MagicEffectExpired/Dispelled` 事件终止，Client 不自行判断到期。 |
| `RULE-MAGIC-061` | 降级链固定：`presentation_id` 未注册或资产缺失 → 学派家族默认表现 `vfx.<school>.family_default` → `vfx.fallback.status_ping`；音频缺失静默跳过。降级不得吞掉原事件（对齐 `DOC-RENDER-008` §8）。 |
| `RULE-MAGIC-062` | 幻象的表现真实性边界：`veil_illusion` 的视觉呈现对感知到它的 Client 与"真实物体"同层渲染，但侦测识破后叠加识破标记；表现层不向未识破者泄露幻象标记。 |
| `RULE-MAGIC-063` | 表现注册表变更只增不改语义：已发布 `presentation_id` 的替换走版本化新增 + 引用切换，保证旧存档回放事件仍可解析表现。 |

## 5. 数据与接口

`DES-MAGIC-011`：表现注册项：

```json
{
  "presentation_schema_version": 1,
  "presentation_id": "magic.presentation.restoration.minor_mend",
  "cast_vfx_id": "vfx.restoration.gentle_weave",
  "impact_vfx_id": "vfx.restoration.mend_glow",
  "cast_audio_id": "audio.sfx.magic.restoration_chime",
  "loop_vfx_id": null,
  "reduced_motion_icon": "icon.magic.restoration"
}
```

学派家族映射（`vfx_family` 落地）：

| 学派 | `vfx_family` | 家族默认 | 音效前缀 |
|---|---|---|---|
| Elemental | `vfx.elemental.*` | `vfx.elemental.family_default` | `audio.sfx.magic.elemental_*` |
| Restoration | `vfx.restoration.*` | `vfx.restoration.family_default` | `audio.sfx.magic.restoration_*` |
| Warding | `vfx.warding.*` | `vfx.warding.family_default` | `audio.sfx.magic.warding_*` |
| Illusion | `vfx.illusion.*` | `vfx.illusion.family_default` | `audio.sfx.magic.illusion_*` |
| Spirit | `vfx.spirit.*` | `vfx.spirit.family_default` | `audio.sfx.magic.spirit_*` |
| Arcane | `vfx.arcane.*` | `vfx.arcane.family_default` | `audio.sfx.magic.arcane_*` |

事件映射：`SpellCastCommitted.render` 携带 `{presentation_id, attach_points, revision}`；Backend/Orchestrator 展开为 `DOC-RENDER-008` 的 VFX payload 与 `DOC-RENDER-010` 的音频触发，RENDER 只见展开结果。

## 6. 正常流程

1. 构建期审计：12 条法术的 `presentation_id`、家族前缀、资产引用与 license（`RULE-RENDER-030`）全部可解析。
2. 施法提交后，render projection 依次触发 cast 表现（施法者锚点）与 impact 表现（目标/地面锚点）。
3. 持续实例创建时启动 loop 表现，到期/驱散事件终止。
4. Reduced Motion 环境下按 `reduced_motion_icon` 走边框/图标提示（`RULE-RENDER-024`）。

## 7. 边界情况

- 同帧多次施法：表现合并遵守 RENDER 每 Scene 活跃 VFX 上限 96 与合并策略，命中/状态优先。
- 目标在表现播放中离场：RENDER 立即回收（`DOC-RENDER-008` §7），MAGIC 无补播义务。
- ritual 长施法：检查点期间使用低强度 loop 表现，完成时才播放 impact，避免把"进行中"渲染成"已生效"。
- 旧存档回放遇到已下线资产：按降级链渲染，事件本身不变。

## 8. 错误与降级

映射解析失败按 `RULE-MAGIC-061` 逐级降级并记录一次性诊断（同一 `presentation_id` 不重复刷屏）。音频总线不可用不影响 VFX；两者都失败时至少保留 `vfx.fallback.status_ping` 的可读反馈，保证玩家能确认施法已发生。

## 9. 安全与性能

表现注册表构建期不可变、按 ID 索引。`render` projection 不含目标 HP、Secret 或效果数值明细——表现强度分级（minor/major）由注册项静态声明，不从结算结果动态推导敏感信息。首版法术全部 one-shot 资产预加载，持续 loop 资产按 Scene 惰性加载。

## 10. 验收标准

- 12 条法术 + 12 个 handler 的表现引用全部解析成功，家族前缀审计零违例。
- 拔除任意资产后表现按降级链呈现且事件流无丢失。
- Reduced Motion 截图回归：无闪光/抖动/全屏遮罩。
- 回放旧事件（含已替换 presentation 版本）表现可解析。

## 11. 测试追踪

| 测试 ID | 覆盖项 | 方法与断言 |
|---|---|---|
| `TEST-MAGIC-024` | `REQ-MAGIC-021..022`, `RULE-MAGIC-059`, `RULE-MAGIC-063` | 映射闭合与家族前缀审计；表现失败不影响提交的注入测试；版本化替换回放 |
| `TEST-MAGIC-025` | `RULE-MAGIC-060..062` | 持续表现随事件终止、降级链逐级拔除、幻象识破标记访问控制 |

## 12. 关联文档

- `DOC-RENDER-008`：VFX 注册、生命周期与可访问性的唯一权威
- `DOC-RENDER-010/011`：音频状态与资产授权
- `DOC-MAGIC-004`：`presentation_id` 引用来源
- `DOC-MAGIC-009`：持续效果实例的创建与到期
- `DOC-WORLD-009`：日式西幻视觉方向
