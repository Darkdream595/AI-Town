---
doc_id: DOC-WORLD-009
title: 日式西幻视觉风格
version: 1.0.0
status: approved-for-implementation
owner_domain: world
canonical_for:
  - japanese-western-fantasy-direction
  - world-palette-families
  - material-vocabulary
  - imitation-boundaries
depends_on:
  - DOC-FOUNDATION-001
  - DOC-WORLD-004
  - DOC-WORLD-005
requirements:
  - REQ-WORLD-028
  - REQ-WORLD-029
  - REQ-WORLD-030
  - REQ-WORLD-031
last_updated: 2026-07-26
---

# 日式西幻视觉风格

## 1. 目的

把“中世纪剑与魔法的日式西幻手绘绘本”转化为可生产、可审查的构图、色板、材质和角色表现方向，同时明确地图为视觉主角、UI 材料克制使用及禁止直接模仿。

## 2. 非目标

本文件不定义 Phaser 渲染代码、Asset 尺寸、Sprite 帧数、Shader、UI 组件或音频实现；不指定任何特定作品、工作室或在世艺术家作为临摹目标，也不要求 AI 生成工具一次输出最终可用规则地图。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| 日式西幻 | 以清晰角色轮廓、克制装饰、可读冒险场景和情绪化自然光表现西方幻想母题的设计语言 |
| 手绘绘本 | 可见笔触、轻微纸感、形状概括和色块层次，而非照片写实或塑料 3D |
| 地图主角 | 大部分画面关注区域、路径、建筑与自然状态，UI 作为低对比信息容器 |
| 材质词汇 | 用于资产 Brief 的木、石、布、纸、金属等统一描述 |
| 色板家族 | 按功能和地区分组的颜色范围，不是每像素强制值 |
| 直接模仿 | 以特定创作者/作品名字要求复刻其可识别线条、构图、角色或纹理 |

## 4. 规则与不变量

| ID | 规则 |
|---|---|
| `REQ-WORLD-028` | 三个 Region 必须共享正交俯视、柔和手绘边缘、中等饱和度与统一光照逻辑，同时保留地区色彩身份。 |
| `REQ-WORLD-029` | Ground Art 必须无角色、文字、标签、UI 和可拆建筑，且道路边界可由 MAP 结构清晰对齐。 |
| `REQ-WORLD-030` | UI 仅使用羊皮纸、深木、旧黄铜作为克制容器，不能以大面积高反射玻璃或重纹理遮挡地图。 |
| `REQ-WORLD-031` | 所有生成与外包 Brief 必须禁止直接模仿特定在世艺术家、受保护角色、Logo 或作品构图。 |
| `RULE-WORLD-036` | 视觉不可作为 Walkability、Collision、法律状态、Secret 或交互成功的唯一事实来源。 |
| `RULE-WORLD-037` | 角色轮廓、重要交互对象和危险边缘在目标缩放下必须先于表面纹理可读。 |
| `RULE-WORLD-038` | 暗黑氛围通过色温、空旷、损耗与天气表达，不通过持续压黑导致路径和角色不可辨。 |
| `RULE-WORLD-039` | 族裔特征保持尊重与个体差异，禁止宠物化、怪物化或用单一服饰编码道德阵营。 |
| `RULE-WORLD-040` | 所有正式 Asset 必须记录来源、生成参数/作者、修改记录和许可证。 |

## 5. 数据与接口

`DES-WORLD-009`：世界层发布以下 palette family 和 material vocabulary，RENDER owner 可细化为 token：

| Family ID | 主色示例 | 用途 |
|---|---|---|
| `palette.parchment` | `#E8D7AE`, `#C9AD79`, `#7A6245` | 少量面板、地图注记容器 |
| `palette.deep_wood` | `#49362F`, `#2F2728` | 框体、梁柱、深色分隔 |
| `palette.old_brass` | `#A27C43`, `#D0AD68` | 焦点、图标边缘、少量高光 |
| `palette.crown_creek` | `#7A5947`, `#55706B`, `#A58A5D` | 红褐屋顶、溪水蓝绿、道路暖灰 |
| `palette.twilight_forest` | `#355B4B`, `#718052`, `#685B7B` | 深绿、苔色、暮紫 |
| `palette.silver_ash` | `#565B64`, `#8C8377`, `#8BA5B2` | 石墨、灰褐、魔晶冷蓝 |
| `palette.danger` | `#8E3F38`, `#D08A4B` | 受限危险强调，不作大面积底色 |

材质固定描述为：刀削深木、风化浅石、锤纹旧黄铜、粗织亚麻、染色羊毛、低对比羊皮纸、苔痕与雨蚀、银灰结晶。

## 6. 正常流程

1. Brief 先选择 RegionIdentity、时间/天气、资产层和玩家可读目标。
2. 生成或绘制 Ground Art 时移除可拆建筑、角色、文字、标签和 UI。
3. Structure 与交互对象按稳定 Asset ID 单独生产，轮廓与入口方向先通过灰度审查。
4. 应用地区 palette family，并以共同的暖光/冷影逻辑保持三地区统一。
5. RENDER 将 Walkability、Collision 和 Semantic overlay 与画面叠加验证，不以视觉猜规则。
6. 进行目标分辨率 Visual QA、来源/许可证审计和禁止模仿检查后入 Manifest。

## 7. 边界情况

- 夜晚、雾和矿洞仍需保留站立面、出口和角色轮廓；可降低色彩，不得隐藏规则反馈。
- 受损建筑可有焦黑、裂缝和支架，但 Damage State 仍由结构化状态驱动。
- 生成图出现伪文字、签名、Logo 或角色时必须重制或清除，不作为“氛围细节”保留。
- fallback 资产需保持碰撞代理尺寸和交互轮廓，不要求与正式资产同等细节。
- UI 在 1280×720 下优先压缩装饰和纹理，不缩小关键信息到不可读。

## 8. 错误与降级

资产缺少 provenance、许可证或包含禁止模仿提示时不得进入正式 Manifest。地区色板缺失时使用共享 parchment/deep_wood 中性 fallback，但不能把镇区 Asset 冒充森林/矿洞 Canon。特效失败只降级表现，不能吞掉已提交事件反馈。

## 9. 安全与性能

生成输入不得包含 Secret、玩家文本、现实个人肖像或受保护角色引用。纹理、纸感与天气层需支持分辨率降级和批处理；地图层级数量与显存预算由 RENDER owner 细化。安全提示、危险轮廓和交互可读性不能在低画质关闭。

## 10. 验收标准

- 三地区缩略图在遮住名称后仍可凭色板和地貌区分，同时能辨认为同一作品。
- Ground Art 自动/人工审计均无角色、文字、标签、UI 和可拆建筑。
- 1920×1080 与 1280×720 下地图仍为主要视觉面积，UI 不遮挡关键通路。
- 夜晚、雾、受损与 fallback 场景中出口、角色和危险边缘可读。
- Asset Manifest 的来源、许可证和禁止模仿审计为零缺失。

## 11. 测试追踪

| 测试 ID | 覆盖项 | 方法与断言 |
|---|---|---|
| `TEST-WORLD-028` | `REQ-WORLD-028`, `RULE-WORLD-037..039` | 三地区 Visual QA 与灰度轮廓检查 |
| `TEST-WORLD-029` | `REQ-WORLD-029`, `RULE-WORLD-036` | Ground Art 内容审计和规则 overlay 对齐 |
| `TEST-WORLD-030` | `REQ-WORLD-030` | 两种目标分辨率 UI 占比与可读性检查 |
| `TEST-WORLD-031` | `REQ-WORLD-031`, `RULE-WORLD-040` | Prompt、provenance、license Manifest 审计 |

## 12. 关联文档

- `DOC-WORLD-004`：三个 Region 的视觉身份输入
- `DOC-WORLD-005`：族裔与文化表现边界
- `DOC-WORLD-010`：黑暗内容的视觉强度
- `DOC-RENDER-003`：地图合成的下游实现
- `DOC-RENDER-009`：羊皮纸 UI token 的下游实现
