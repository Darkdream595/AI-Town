# AI Town 生图需求完整清单

**生成时间**：2026-07-27 00:30  
**目标模型**：支持多动作组合的图像生成模型（如 DALL-E 3, Midjourney, Stable Diffusion）  
**用途**：替换当前的程序化占位图

---

## 🎨 总体美术风格

**核心风格**：日式西幻（Japanese Western Fantasy）+ 手绘绘本风格  
**色调**：温暖、柔和、带有魔法感  
**参考**：宫崎骏、吉卜力工作室的世界观 + 欧洲中世纪小镇  
**分辨率要求**：  
- 地图：至少 2048×2048 像素（可切片）
- Sprite：64×64 像素/帧，但生成时建议 512×512 后缩小（保持细节）

---

## 📍 第一部分：地图底图（3 张）

### 地图 1：王冠溪镇（Crown Creek Town）

**提示词**：
```
A hand-painted top-down view of a medieval Japanese-Western fantasy town called "Crown Creek Town". The town is safe and peaceful, with a small stream running through the center. Include these buildings arranged naturally:

- Central town square with a fountain
- 3-4 wooden residential houses with thatched roofs
- 1 blacksmith forge with smoke rising
- 1 general store with colorful awnings
- 1 small tavern/inn with warm lighting
- 1 guard station
- 1 small temple/shrine
- Cobblestone paths connecting all buildings
- Green grass, flower beds, and small trees
- Wooden fences and decorative elements

Art style: Ghibli-inspired, warm colors, soft lighting, bird's-eye view, painterly textures. The map should be tile-friendly with clear walkable paths and building boundaries. 2048x2048 pixels, seamless edges.
```

**关键要求**：
- 俯视图（top-down view）
- 建筑边界清晰（用于碰撞检测）
- 道路和草地区分明显
- 无透视变形，平面正交

---

### 地图 2：暮语森林（Twilight Whisper Forest）

**提示词**：
```
A hand-painted top-down view of a magical forest called "Twilight Whisper Forest". The forest is mysterious and slightly dangerous, with twilight ambiance. Include these elements:

- Dense forest with tall ancient trees
- Winding dirt paths through the woods
- A small clearing with magical mushrooms glowing faintly
- A hidden pond with lily pads
- Scattered rocks and fallen logs
- Mysterious mist at the edges
- Some darker areas representing danger zones
- Wild flowers and ferns

Art style: Ghibli-inspired, purple and blue twilight tones, magical atmosphere, soft glowing elements, bird's-eye view, painterly textures. The map should be tile-friendly with clear walkable paths. 2048x2048 pixels, seamless edges.
```

**关键要求**：
- 可行走路径清晰（泥土路）
- 树木密集但不完全遮挡视线
- 暮色调（紫蓝色）
- 神秘感但不恐怖

---

### 地图 3：银烬矿洞（Silver Ash Mine）

**提示词**：
```
A hand-painted top-down view of an underground mine entrance and tunnels called "Silver Ash Mine". The mine is dark and industrial, with dangers lurking. Include these elements:

- Mine entrance with wooden support beams
- 2-3 branching mine tunnels with tracks
- Minecart on rails
- Ore deposits (silver veins glowing faintly)
- Wooden scaffolding and ladders
- Torches and lanterns providing light
- Rocky walls and stone floors
- Small underground pond
- Some collapsed areas (impassable)

Art style: Ghibli-inspired but darker tones, orange torch light contrasting with dark stone, industrial fantasy, bird's-eye view, painterly textures. The map should be tile-friendly with clear walkable paths. 2048x2048 pixels, seamless edges.
```

**关键要求**：
- 地下环境感（暗色调，点光源）
- 矿道和岩壁边界清晰
- 银矿脉有微光（视觉焦点）

---

## 👥 第二部分：角色 Sprite Atlas（至少 4 个种族×职业组合）

### Sprite 技术规格

**关键要求**：
- **每个 Atlas = 8 方向 × 6 状态 = 48 帧**
- **方向顺序**：N（上）、NE（右上）、E（右）、SE（右下）、S（下）、SW（左下）、W（左）、NW（左上）
- **状态顺序**：idle（待机）、walk（行走）、work（工作）、talk（交谈）、cast（施法）、hurt（受伤）
- **帧尺寸**：64×64 像素/帧
- **Atlas 布局**：横向 8 帧（方向） × 纵向 6 帧（状态）= 512×384 像素
- **透明背景**：PNG 格式，角色外完全透明
- **中心锚点**：角色脚部位于帧底部中心

**生成策略**：  
由于单张图生成 48 帧困难，建议**分两步**：
1. 生成 8 方向的待机姿势（单排 8 帧）
2. 为每个方向生成 6 种状态变体
3. 手动或脚本组合为完整 Atlas

---

### Sprite 1：人类农夫（Human Farmer）

**提示词（8 方向待机姿势）**：
```
A sprite sheet of a human farmer character for a top-down RPG game. Show the SAME character facing 8 directions in a single row: North (back view), Northeast, East (right side), Southeast, South (front view), Southwest, West (left side), Northwest. 

Character details:
- Middle-aged human male farmer
- Simple brown tunic and pants
- Straw hat
- Warm, friendly appearance
- Holding a wooden hoe or farming tool
- Standing idle pose (not walking)

Art style: Ghibli-inspired, hand-painted, soft colors, clean outlines. 64x64 pixels per frame, 8 frames in a horizontal row (512x64 total). Transparent background. Character should be centered with feet at the bottom of each frame.
```

**提示词（6 状态变体 - 以朝南为例）**：
```
A sprite sheet showing a human farmer character in 6 different action states, all facing SOUTH (front view). Arrange in a horizontal row:

1. Idle - standing still with hoe
2. Walk - one foot forward, walking pose
3. Work - bent over, using hoe to till soil
4. Talk - gesturing with one hand, friendly expression
5. Cast - not applicable (farmer doesn't cast spells, show resting pose)
6. Hurt - recoiling, hand on chest, pained expression

Same character: middle-aged human male, brown tunic, straw hat. Art style: Ghibli-inspired, hand-painted. 64x64 pixels per frame, 6 frames horizontal (384x64 total). Transparent background.
```

**重复此过程生成其他 7 个方向的 6 状态变体**

---

### Sprite 2：精灵魔法师（Elf Mage）

**提示词（8 方向待机姿势）**：
```
A sprite sheet of an elf mage character for a top-down RPG game. Show the SAME character facing 8 directions in a single row: North, Northeast, East, Southeast, South, Southwest, West, Northwest.

Character details:
- Graceful female elf mage
- Long silver hair, pointed ears
- Blue/purple flowing robes with gold trim
- Holding a wooden staff with a glowing crystal
- Elegant standing pose
- Slight magical aura around the staff

Art style: Ghibli-inspired, hand-painted, magical fantasy aesthetic. 64x64 pixels per frame, 8 frames horizontal. Transparent background.
```

---

### Sprite 3：矮人铁匠（Dwarf Blacksmith）

**提示词（8 方向待机姿势）**：
```
A sprite sheet of a dwarf blacksmith character for a top-down RPG game. Show the SAME character facing 8 directions in a single row: North, Northeast, East, Southeast, South, Southwest, West, Northwest.

Character details:
- Sturdy male dwarf blacksmith
- Short height, broad shoulders
- Thick brown beard, bald head or short hair
- Leather apron over simple shirt
- Holding a large hammer
- Confident, strong stance

Art style: Ghibli-inspired, hand-painted, warm earthy tones. 64x64 pixels per frame, 8 frames horizontal. Transparent background.
```

---

### Sprite 4：半身人商人（Halfling Merchant）

**提示词（8 方向待机姿势）**：
```
A sprite sheet of a halfling merchant character for a top-down RPG game. Show the SAME character facing 8 directions in a single row: North, Northeast, East, Southeast, South, Southwest, West, Northwest.

Character details:
- Cheerful male halfling merchant
- Short height (child-sized), friendly round face
- Colorful vest and pants
- Carrying a small coin pouch or ledger
- Welcoming, jovial expression

Art style: Ghibli-inspired, hand-painted, bright cheerful colors. 64x64 pixels per frame, 8 frames horizontal. Transparent background.
```

---

## 🔄 生成后处理流程

### 步骤 1：生成原始图像
- 使用上述提示词生成高分辨率图像（建议 2048×2048 或更高）
- 确保方向/状态在单张图中排列整齐

### 步骤 2：切割和缩放
- 使用 Python 脚本或图像编辑器切割为单帧
- 缩放至 64×64 像素
- 确保透明背景保留

### 步骤 3：组装 Atlas
- 按照 8 方向 × 6 状态的顺序组装为 512×384 Atlas
- 保存为 PNG 格式

### 步骤 4：更新 Manifest
- 修改 `frontend/public/assets/manifests/assets.json`
- 添加帧坐标信息

---

## 📝 注意事项

### 关键一致性要求

1. **同一角色的所有帧必须视觉一致**
   - 服装颜色、发型、体型完全相同
   - 建议使用 seed 固定或 reference image

2. **透明背景是强制要求**
   - 角色外部必须完全透明
   - 无阴影延伸到帧外

3. **朝向正确性**
   - 朝北 = 看到后背
   - 朝南 = 看到正面
   - 左右对称需镜像翻转

4. **动作幅度适中**
   - Walk 状态仅一步，非跑步
   - Cast 状态举起法杖或工具，非夸张动作

### 可选扩展

如果时间充足，可额外生成：
- 守卫（Guard）Sprite
- 牧师（Priest）Sprite
- 猎人（Hunter）Sprite

---

## 💬 生成时的沟通建议

当你在多个 GPT 会话中生成时，**每个会话的提示词需包含**：

1. **总体风格声明**（放在最前面）：
   ```
   This is for an AI Town game with Ghibli-inspired Japanese Western Fantasy aesthetic. All assets should maintain consistent warm, hand-painted style.
   ```

2. **当前任务上下文**：
   ```
   Current task: Generate [地图名称/角色名称] for a top-down 2D RPG.
   ```

3. **完整的单项提示词**（从上面复制）

4. **一致性参考**（如果模型支持）：
   ```
   Reference previous generation: [描述之前生成的内容特征]
   ```

---

## ✅ 验收标准

生成的资源应满足：
- [ ] 地图可行走区域清晰可辨
- [ ] 建筑边界适合碰撞检测（轮廓分明）
- [ ] Sprite 8 方向视觉区分明显
- [ ] Sprite 6 状态动作合理
- [ ] 透明背景无瑕疵
- [ ] 整体风格统一（Ghibli 手绘感）
- [ ] 颜色温暖柔和，符合日式西幻调性

---

**准备就绪！你可以将上述提示词分配到多个 GPT 会话中并行生成。** 🎨
