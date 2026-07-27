# 公开可商用的 RPG Sprite 资源推荐

根据你的需求（3方向 × 3状态，适配奇幻角色），我找到了以下资源：

## 🎨 推荐资源包

### 1. LPC (Liberated Pixel Cup) Character Generator
**链接**：https://sanderfrenken.github.io/Universal-LPC-Spritesheet-Character-Generator/
- **许可**：CC-BY-SA 3.0 / GPL 3.0（可商用，需署名）
- **规格**：64×64，4方向×多状态
- **优点**：
  - 可自定义角色外观（发型、服装、配饰）
  - 包含行走、攻击、施法等动画
  - 社区贡献，资源丰富
- **角色类型**：人类、精灵、兽人、矮人等
- **下载**：生成后直接下载 PNG

### 2. Kenney's Micro Roguelike
**链接**：https://www.kenney.nl/assets/micro-roguelike
- **许可**：CC0（完全免费，无需署名）
- **规格**：16×16，像素风格
- **优点**：
  - 完全免费可商用
  - 包含角色、怪物、环境
  - 风格统一
- **缺点**：分辨率较低，需放大

### 3. OpenGameArt - Universal LPC Spritesheet
**链接**：https://opengameart.org/content/liberated-pixel-cup-lpc-base-assets
- **许可**：CC-BY-SA 3.0 / GPL 3.0
- **规格**：64×64，完整动画集
- **包含**：
  - 基础人类模板
  - 服装、武器、配饰图层
  - 可自由组合
- **下载**：ZIP 打包，包含 PSD 源文件

### 4. itch.io - Top-Down Character Pack
**链接**：https://itch.io/game-assets/free/tag-characters+tag-top-down
- **许可**：多种（查看具体资源包）
- **推荐包**：
  - "RPG Characters" by GrafxKid（免费可商用）
  - "Pixel Art Top Down" by Penzilla（免费）

### 5. CraftPix - Free RPG Sprites
**链接**：https://craftpix.net/freebies/
- **许可**：Free License（可商用，限制较少）
- **规格**：多种分辨率
- **优点**：质量高，美术风格统一

---

## 📋 建议方案

基于你的需求，我推荐 **LPC Character Generator**：

### 优势：
1. ✅ 可自定义 10 个角色（农夫、法师、铁匠等）
2. ✅ 自动生成 4 方向（上下左右），你只用 3 个即可
3. ✅ 包含 idle + walk 动画（正好满足需求）
4. ✅ 64×64 分辨率（适合你的项目）
5. ✅ 可商用（需署名）

### 操作步骤：
1. 访问生成器：https://sanderfrenken.github.io/Universal-LPC-Spritesheet-Character-Generator/
2. 为每个角色选择：
   - Body（身体类型）
   - Hairstyle（发型）
   - Clothing（服装）
   - Weapon/Tool（工具）
3. 点击 "Download" 下载 PNG
4. 重命名并放入 `frontend/public/assets/sprites/raw/`

### 需要生成的角色：
- Human Farmer（选择农夫服装 + 农具）
- Elf Mage（选择法袍 + 法杖）
- Dwarf Blacksmith（选择围裙 + 锤子）
- Halfling Merchant（选择商人服装）
- Human Guard（选择盔甲 + 剑盾）
- Human Priest（选择长袍 + 圣书）
- Human Innkeeper（选择普通衣服）
- Elf Alchemist（选择法袍 + 药瓶）
- Human Hunter（选择皮甲 + 弓箭）
- Dwarf Miner（选择工作服 + 镐子）

---

## 🚨 许可注意事项

使用 LPC 资源需要：
1. 在游戏 Credits 中署名：
   ```
   Character sprites based on Universal LPC Spritesheet
   Licensed under CC-BY-SA 3.0 / GPL 3.0
   Contributors: [查看生成器页面的贡献者列表]
   ```

2. 如果不想署名，可使用 Kenney 的 CC0 资源（完全免费无限制）

---

## ❓ 我应该做什么？

**选项 A**：我帮你使用 LPC Generator 生成 10 个角色并下载（需要你提供详细的外观选择）

**选项 B**：你自己去 LPC Generator 生成并下载，我帮你重命名和组织文件

**选项 C**：我下载推荐的免费资源包并帮你提取合适的角色

你选哪个？
