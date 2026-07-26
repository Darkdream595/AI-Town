# AI Town Sprite 生图提示词 - 完整版

**生成策略**：每个角色生成 8×6=48 张独立图片，手动或脚本组装成 Atlas

---

## 技术要求

- **分辨率**：每帧 **1024×1024** 像素（高清，避免糊）
- **格式**：PNG，透明背景
- **视角**：正上方俯视 45 度（top-down RPG）
- **风格**：Ghibli 手绘，清晰线条，饱和色彩
- **一致性**：同角色所有帧必须完全相同的服装、发型、体型、配色

---

## 人类农夫（Human Farmer）

### 角色描述
Middle-aged human male farmer. Brown tunic, beige pants, straw hat. Holding wooden hoe. Warm friendly face, short brown beard. Average build, 170cm height.

### North（朝北，后背）
```
A single 1024x1024 sprite of a human farmer viewed from behind (North direction), top-down 45-degree angle for RPG game.

STATE: [idle/walk/work/talk/cast/hurt]

Character: Middle-aged male, brown tunic, straw hat (back view), wooden hoe held in right hand.

Action details:
- idle: standing still, hoe resting on ground
- walk: one foot forward, mid-step
- work: bent over, hoe striking ground, tilling soil
- talk: turning head slightly, one hand raised in gesture
- cast: not applicable (show resting/idle pose)
- hurt: stumbling back, hand on lower back, pained posture

Art style: Ghibli-inspired, hand-painted, warm earthy tones, clean outlines, soft shading. Character centered, feet at bottom 20% of frame. Transparent background. High detail, sharp edges, NO blur.
```

### Northeast（右上）
```
A single 1024x1024 sprite of a human farmer viewed from Northeast (back-right diagonal), top-down 45-degree angle for RPG game.

STATE: [idle/walk/work/talk/cast/hurt]

Character: Middle-aged male, brown tunic, straw hat visible from angle, wooden hoe in right hand.

Action details:
- idle: standing still, weight on both feet
- walk: right foot forward, hoe swinging slightly
- work: bent, hoe digging at angle
- talk: head turned right, friendly gesture
- cast: idle pose
- hurt: recoiling right, hand on side

Art style: Ghibli-inspired, hand-painted, warm earthy tones, clean outlines, soft shading. Character centered, feet at bottom 20% of frame. Transparent background. High detail, sharp edges, NO blur.
```

### East（朝东，右侧）
```
A single 1024x1024 sprite of a human farmer viewed from right side (East direction), top-down 45-degree angle for RPG game.

STATE: [idle/walk/work/talk/cast/hurt]

Character: Middle-aged male, brown tunic, straw hat profile, wooden hoe visible.

Action details:
- idle: standing, facing right, hoe resting
- walk: right leg forward, natural walking
- work: bent forward, hoe motion
- talk: head turned forward, gesturing
- cast: idle pose
- hurt: stumbling right, hand on chest

Art style: Ghibli-inspired, hand-painted, warm earthy tones, clean outlines, soft shading. Character centered, feet at bottom 20% of frame. Transparent background. High detail, sharp edges, NO blur.
```

### Southeast（右下）
```
A single 1024x1024 sprite of a human farmer viewed from Southeast (front-right diagonal), top-down 45-degree angle for RPG game.

STATE: [idle/walk/work/talk/cast/hurt]

Character: Middle-aged male, brown tunic, straw hat, friendly bearded face visible at angle.

Action details:
- idle: standing, slight front-right angle
- walk: right foot forward
- work: bent, hoe hitting ground
- talk: looking slightly right, open gesture
- cast: idle pose
- hurt: recoiling, hand on chest

Art style: Ghibli-inspired, hand-painted, warm earthy tones, clean outlines, soft shading. Character centered, feet at bottom 20% of frame. Transparent background. High detail, sharp edges, NO blur.
```

### South（朝南，正面）
```
A single 1024x1024 sprite of a human farmer viewed from front (South direction), top-down 45-degree angle for RPG game.

STATE: [idle/walk/work/talk/cast/hurt]

Character: Middle-aged male, brown tunic, straw hat, warm friendly bearded face, wooden hoe.

Action details:
- idle: standing, facing viewer, hoe resting
- walk: one foot forward toward viewer
- work: bent over, hoe striking ground
- talk: friendly smile, one hand gesturing
- cast: idle pose
- hurt: recoiling, both hands on chest, pain expression

Art style: Ghibli-inspired, hand-painted, warm earthy tones, clean outlines, soft shading. Character centered, feet at bottom 20% of frame. Transparent background. High detail, sharp edges, NO blur.
```

### Southwest（左下）
```
A single 1024x1024 sprite of a human farmer viewed from Southwest (front-left diagonal), top-down 45-degree angle for RPG game.

STATE: [idle/walk/work/talk/cast/hurt]

Character: Middle-aged male, brown tunic, straw hat, face visible at angle.

Action details:
- idle: standing, slight front-left angle
- walk: left foot forward
- work: bent, hoe digging
- talk: looking slightly left, gesture
- cast: idle pose
- hurt: recoiling left, hand on side

Art style: Ghibli-inspired, hand-painted, warm earthy tones, clean outlines, soft shading. Character centered, feet at bottom 20% of frame. Transparent background. High detail, sharp edges, NO blur.
```

### West（朝西，左侧）
```
A single 1024x1024 sprite of a human farmer viewed from left side (West direction), top-down 45-degree angle for RPG game.

STATE: [idle/walk/work/talk/cast/hurt]

Character: Middle-aged male, brown tunic, straw hat profile, wooden hoe.

Action details:
- idle: standing, facing left, hoe resting
- walk: left leg forward
- work: bent, hoe motion
- talk: head turned, gesture
- cast: idle pose
- hurt: stumbling left, hand on chest

Art style: Ghibli-inspired, hand-painted, warm earthy tones, clean outlines, soft shading. Character centered, feet at bottom 20% of frame. Transparent background. High detail, sharp edges, NO blur.
```

### Northwest（左上）
```
A single 1024x1024 sprite of a human farmer viewed from Northwest (back-left diagonal), top-down 45-degree angle for RPG game.

STATE: [idle/walk/work/talk/cast/hurt]

Character: Middle-aged male, brown tunic, straw hat back view, wooden hoe.

Action details:
- idle: standing, back-left view
- walk: left foot forward
- work: bent, hoe digging
- talk: head turned left, gesture
- cast: idle pose
- hurt: recoiling left, hand on back

Art style: Ghibli-inspired, hand-painted, warm earthy tones, clean outlines, soft shading. Character centered, feet at bottom 20% of frame. Transparent background. High detail, sharp edges, NO blur.
```

---

## 精灵魔法师（Elf Mage）

### 角色描述
Graceful female elf mage. Long silver hair, pointed ears. Blue-purple flowing robes with gold trim. Wooden staff with glowing blue crystal. Elegant posture, 175cm height.

### North（朝北，后背）
```
A single 1024x1024 sprite of an elf mage viewed from behind (North direction), top-down 45-degree angle for RPG game.

STATE: [idle/walk/work/talk/cast/hurt]

Character: Female elf, long silver hair (back view), blue-purple robes, wooden staff with glowing crystal.

Action details:
- idle: standing gracefully, staff upright
- walk: flowing robe, staff in hand, one foot forward
- work: not applicable (show idle or studying pose)
- talk: head turned slightly, elegant gesture
- cast: staff raised high, crystal glowing bright, magical energy
- hurt: stumbling, one hand on back, pained but composed

Art style: Ghibli-inspired, magical fantasy aesthetic, glowing effects on crystal, elegant flowing lines. Character centered, feet at bottom 20% of frame. Transparent background. High detail, sharp edges, NO blur.
```

### Northeast（右上）
```
A single 1024x1024 sprite of an elf mage viewed from Northeast (back-right diagonal), top-down 45-degree angle for RPG game.

STATE: [idle/walk/work/talk/cast/hurt]

Character: Female elf, silver hair visible, blue-purple robes, staff with glowing crystal.

Action details:
- idle: graceful stance
- walk: right foot forward, robe flowing
- work: idle or reading pose
- talk: head turned right, elegant gesture
- cast: staff raised, crystal bright, spell motion
- hurt: recoiling right, hand raised defensively

Art style: Ghibli-inspired, magical fantasy aesthetic, glowing effects on crystal, elegant flowing lines. Character centered, feet at bottom 20% of frame. Transparent background. High detail, sharp edges, NO blur.
```

### East（朝东，右侧）
```
A single 1024x1024 sprite of an elf mage viewed from right side (East direction), top-down 45-degree angle for RPG game.

STATE: [idle/walk/work/talk/cast/hurt]

Character: Female elf, silver hair profile, pointed ear visible, blue-purple robes, staff.

Action details:
- idle: standing, staff resting
- walk: right leg forward, graceful
- work: idle or contemplating
- talk: facing right, gentle gesture
- cast: staff extended right, casting spell
- hurt: stumbling right, hand on side

Art style: Ghibli-inspired, magical fantasy aesthetic, glowing effects on crystal, elegant flowing lines. Character centered, feet at bottom 20% of frame. Transparent background. High detail, sharp edges, NO blur.
```

### Southeast（右下）
```
A single 1024x1024 sprite of an elf mage viewed from Southeast (front-right diagonal), top-down 45-degree angle for RPG game.

STATE: [idle/walk/work/talk/cast/hurt]

Character: Female elf, silver hair, elegant face visible, blue-purple robes, staff.

Action details:
- idle: graceful stance, slight angle
- walk: right foot forward
- work: idle
- talk: looking right, serene expression
- cast: staff forward, crystal glowing, spell effect
- hurt: recoiling, protective gesture

Art style: Ghibli-inspired, magical fantasy aesthetic, glowing effects on crystal, elegant flowing lines. Character centered, feet at bottom 20% of frame. Transparent background. High detail, sharp edges, NO blur.
```

### South（朝南，正面）
```
A single 1024x1024 sprite of an elf mage viewed from front (South direction), top-down 45-degree angle for RPG game.

STATE: [idle/walk/work/talk/cast/hurt]

Character: Female elf, long silver hair, pointed ears, serene face, blue-purple robes, staff with glowing crystal.

Action details:
- idle: standing gracefully, staff upright
- walk: one foot forward toward viewer
- work: idle
- talk: gentle smile, one hand gesture
- cast: staff raised forward, crystal bright, casting spell at viewer
- hurt: recoiling, both hands protective, pained expression

Art style: Ghibli-inspired, magical fantasy aesthetic, glowing effects on crystal, elegant flowing lines. Character centered, feet at bottom 20% of frame. Transparent background. High detail, sharp edges, NO blur.
```

### Southwest（左下）
```
A single 1024x1024 sprite of an elf mage viewed from Southwest (front-left diagonal), top-down 45-degree angle for RPG game.

STATE: [idle/walk/work/talk/cast/hurt]

Character: Female elf, silver hair, face visible at angle, blue-purple robes, staff.

Action details:
- idle: graceful stance
- walk: left foot forward
- work: idle
- talk: looking left, gesture
- cast: staff forward, spell effect
- hurt: recoiling left, defensive

Art style: Ghibli-inspired, magical fantasy aesthetic, glowing effects on crystal, elegant flowing lines. Character centered, feet at bottom 20% of frame. Transparent background. High detail, sharp edges, NO blur.
```

### West（朝西，左侧）
```
A single 1024x1024 sprite of an elf mage viewed from left side (West direction), top-down 45-degree angle for RPG game.

STATE: [idle/walk/work/talk/cast/hurt]

Character: Female elf, silver hair profile, pointed ear, blue-purple robes, staff.

Action details:
- idle: standing gracefully
- walk: left leg forward
- work: idle
- talk: facing left, gesture
- cast: staff extended left, casting
- hurt: stumbling left, hand on side

Art style: Ghibli-inspired, magical fantasy aesthetic, glowing effects on crystal, elegant flowing lines. Character centered, feet at bottom 20% of frame. Transparent background. High detail, sharp edges, NO blur.
```

### Northwest（左上）
```
A single 1024x1024 sprite of an elf mage viewed from Northwest (back-left diagonal), top-down 45-degree angle for RPG game.

STATE: [idle/walk/work/talk/cast/hurt]

Character: Female elf, silver hair back view, blue-purple robes, staff.

Action details:
- idle: graceful back-left stance
- walk: left foot forward, robe flowing
- work: idle
- talk: head turned left, gesture
- cast: staff raised, crystal glowing
- hurt: recoiling left, hand on back

Art style: Ghibli-inspired, magical fantasy aesthetic, glowing effects on crystal, elegant flowing lines. Character centered, feet at bottom 20% of frame. Transparent background. High detail, sharp edges, NO blur.
```

---

## 矮人铁匠（Dwarf Blacksmith）

### 角色描述
Sturdy male dwarf blacksmith. Thick brown beard, bald head. Leather apron over brown shirt, rolled-up sleeves. Large iron hammer. Confident strong stance, 130cm height.

### North（朝北，后背）
```
A single 1024x1024 sprite of a dwarf blacksmith viewed from behind (North direction), top-down 45-degree angle for RPG game.

STATE: [idle/walk/work/talk/cast/hurt]

Character: Male dwarf, short stature, broad shoulders, leather apron (back view), large hammer in hand.

Action details:
- idle: standing sturdy, hammer resting on shoulder
- walk: heavy step, one foot forward
- work: swinging hammer down on anvil, sparks flying
- talk: head turned, strong gesture
- cast: not applicable (show resting pose)
- hurt: stumbling, hand on lower back, tough expression

Art style: Ghibli-inspired, warm earthy tones, strong industrial feel, detailed textures on apron. Character centered, feet at bottom 20% of frame. Transparent background. High detail, sharp edges, NO blur.
```

### Northeast（右上）
```
A single 1024x1024 sprite of a dwarf blacksmith viewed from Northeast (back-right diagonal), top-down 45-degree angle for RPG game.

STATE: [idle/walk/work/talk/cast/hurt]

Character: Male dwarf, beard visible, leather apron, hammer.

Action details:
- idle: sturdy stance
- walk: right foot forward, heavy step
- work: hammer raised, striking motion
- talk: head turned right, strong gesture
- cast: resting
- hurt: recoiling right, hand on side

Art style: Ghibli-inspired, warm earthy tones, strong industrial feel, detailed textures on apron. Character centered, feet at bottom 20% of frame. Transparent background. High detail, sharp edges, NO blur.
```

### East（朝东，右侧）
```
A single 1024x1024 sprite of a dwarf blacksmith viewed from right side (East direction), top-down 45-degree angle for RPG game.

STATE: [idle/walk/work/talk/cast/hurt]

Character: Male dwarf, thick beard profile, leather apron, hammer.

Action details:
- idle: standing, hammer on shoulder
- walk: right leg forward, heavy gait
- work: hammer swinging down, arm extended
- talk: facing right, confident gesture
- cast: resting
- hurt: stumbling right, hand on chest

Art style: Ghibli-inspired, warm earthy tones, strong industrial feel, detailed textures on apron. Character centered, feet at bottom 20% of frame. Transparent background. High detail, sharp edges, NO blur.
```

### Southeast（右下）
```
A single 1024x1024 sprite of a dwarf blacksmith viewed from Southeast (front-right diagonal), top-down 45-degree angle for RPG game.

STATE: [idle/walk/work/talk/cast/hurt]

Character: Male dwarf, thick brown beard, confident face, leather apron, hammer.

Action details:
- idle: sturdy stance, slight angle
- walk: right foot forward
- work: hammer striking, sparks
- talk: looking right, strong gesture
- cast: resting
- hurt: recoiling, protective

Art style: Ghibli-inspired, warm earthy tones, strong industrial feel, detailed textures on apron. Character centered, feet at bottom 20% of frame. Transparent background. High detail, sharp edges, NO blur.
```

### South（朝南，正面）
```
A single 1024x1024 sprite of a dwarf blacksmith viewed from front (South direction), top-down 45-degree angle for RPG game.

STATE: [idle/walk/work/talk/cast/hurt]

Character: Male dwarf, thick brown beard, bald head, confident face, leather apron, large hammer.

Action details:
- idle: standing sturdy, hammer resting
- walk: one foot forward toward viewer
- work: hammer raised high, about to strike
- talk: confident smile, one hand gesture
- cast: resting
- hurt: recoiling, both hands up, tough expression

Art style: Ghibli-inspired, warm earthy tones, strong industrial feel, detailed textures on apron. Character centered, feet at bottom 20% of frame. Transparent background. High detail, sharp edges, NO blur.
```

### Southwest（左下）
```
A single 1024x1024 sprite of a dwarf blacksmith viewed from Southwest (front-left diagonal), top-down 45-degree angle for RPG game.

STATE: [idle/walk/work/talk/cast/hurt]

Character: Male dwarf, beard, apron, hammer.

Action details:
- idle: sturdy stance
- walk: left foot forward
- work: hammer striking
- talk: looking left, gesture
- cast: resting
- hurt: recoiling left

Art style: Ghibli-inspired, warm earthy tones, strong industrial feel, detailed textures on apron. Character centered, feet at bottom 20% of frame. Transparent background. High detail, sharp edges, NO blur.
```

### West（朝西，左侧）
```
A single 1024x1024 sprite of a dwarf blacksmith viewed from left side (West direction), top-down 45-degree angle for RPG game.

STATE: [idle/walk/work/talk/cast/hurt]

Character: Male dwarf, beard profile, apron, hammer.

Action details:
- idle: standing, hammer on shoulder
- walk: left leg forward
- work: hammer swinging
- talk: facing left, gesture
- cast: resting
- hurt: stumbling left

Art style: Ghibli-inspired, warm earthy tones, strong industrial feel, detailed textures on apron. Character centered, feet at bottom 20% of frame. Transparent background. High detail, sharp edges, NO blur.
```

### Northwest（左上）
```
A single 1024x1024 sprite of a dwarf blacksmith viewed from Northwest (back-left diagonal), top-down 45-degree angle for RPG game.

STATE: [idle/walk/work/talk/cast/hurt]

Character: Male dwarf, back-left view, apron, hammer.

Action details:
- idle: sturdy back stance
- walk: left foot forward
- work: hammer raised
- talk: head turned left
- cast: resting
- hurt: recoiling left

Art style: Ghibli-inspired, warm earthy tones, strong industrial feel, detailed textures on apron. Character centered, feet at bottom 20% of frame. Transparent background. High detail, sharp edges, NO blur.
```

---

## 半身人商人（Halfling Merchant）

### 角色描述
Cheerful male halfling merchant. Child-sized height, friendly round face. Colorful patchwork vest, brown pants. Carrying small coin pouch or ledger. Welcoming expression, 105cm height.

### North（朝北，后背）
```
A single 1024x1024 sprite of a halfling merchant viewed from behind (North direction), top-down 45-degree angle for RPG game.

STATE: [idle/walk/work/talk/cast/hurt]

Character: Male halfling, short height (child-sized), colorful vest (back view), coin pouch at belt.

Action details:
- idle: standing cheerfully, hands on hips
- walk: quick light step, one foot forward
- work: counting coins or writing in ledger
- talk: head turned, animated gesture
- cast: not applicable (show resting)
- hurt: stumbling, hand on back, surprised expression

Art style: Ghibli-inspired, bright cheerful colors, warm friendly tones, soft round features. Character centered, feet at bottom 20% of frame. Transparent background. High detail, sharp edges, NO blur.
```

### Northeast（右上）
```
A single 1024x1024 sprite of a halfling merchant viewed from Northeast (back-right diagonal), top-down 45-degree angle for RPG game.

STATE: [idle/walk/work/talk/cast/hurt]

Character: Male halfling, colorful vest, friendly face partially visible, coin pouch.

Action details:
- idle: cheerful stance
- walk: right foot forward, bouncy step
- work: handling coins or ledger
- talk: head turned right, friendly gesture
- cast: resting
- hurt: recoiling right, surprised

Art style: Ghibli-inspired, bright cheerful colors, warm friendly tones, soft round features. Character centered, feet at bottom 20% of frame. Transparent background. High detail, sharp edges, NO blur.
```

### East（朝东，右侧）
```
A single 1024x1024 sprite of a halfling merchant viewed from right side (East direction), top-down 45-degree angle for RPG game.

STATE: [idle/walk/work/talk/cast/hurt]

Character: Male halfling, colorful vest profile, round friendly face, coin pouch.

Action details:
- idle: standing, hands near pouch
- walk: right leg forward, quick step
- work: counting coins
- talk: facing right, welcoming gesture
- cast: resting
- hurt: stumbling right, hand on side

Art style: Ghibli-inspired, bright cheerful colors, warm friendly tones, soft round features. Character centered, feet at bottom 20% of frame. Transparent background. High detail, sharp edges, NO blur.
```

### Southeast（右下）
```
A single 1024x1024 sprite of a halfling merchant viewed from Southeast (front-right diagonal), top-down 45-degree angle for RPG game.

STATE: [idle/walk/work/talk/cast/hurt]

Character: Male halfling, colorful vest, friendly round face, coin pouch.

Action details:
- idle: cheerful stance
- walk: right foot forward
- work: handling coins
- talk: looking right, jolly expression
- cast: resting
- hurt: recoiling, protective

Art style: Ghibli-inspired, bright cheerful colors, warm friendly tones, soft round features. Character centered, feet at bottom 20% of frame. Transparent background. High detail, sharp edges, NO blur.
```

### South（朝南，正面）
```
A single 1024x1024 sprite of a halfling merchant viewed from front (South direction), top-down 45-degree angle for RPG game.

STATE: [idle/walk/work/talk/cast/hurt]

Character: Male halfling, short height, friendly round face with big smile, colorful patchwork vest, brown pants, coin pouch.

Action details:
- idle: standing cheerfully, welcoming posture
- walk: one foot forward toward viewer
- work: counting coins or writing
- talk: big smile, both hands gesturing welcomingly
- cast: resting
- hurt: recoiling, hands up, surprised expression

Art style: Ghibli-inspired, bright cheerful colors, warm friendly tones, soft round features. Character centered, feet at bottom 20% of frame. Transparent background. High detail, sharp edges, NO blur.
```

### Southwest（左下）
```
A single 1024x1024 sprite of a halfling merchant viewed from Southwest (front-left diagonal), top-down 45-degree angle for RPG game.

STATE: [idle/walk/work/talk/cast/hurt]

Character: Male halfling, colorful vest, friendly face, coin pouch.

Action details:
- idle: cheerful stance
- walk: left foot forward
- work: handling coins
- talk: looking left, gesture
- cast: resting
- hurt: recoiling left

Art style: Ghibli-inspired, bright cheerful colors, warm friendly tones, soft round features. Character centered, feet at bottom 20% of frame. Transparent background. High detail, sharp edges, NO blur.
```

### West（朝西，左侧）
```
A single 1024x1024 sprite of a halfling merchant viewed from left side (West direction), top-down 45-degree angle for RPG game.

STATE: [idle/walk/work/talk/cast/hurt]

Character: Male halfling, colorful vest profile, coin pouch.

Action details:
- idle: standing cheerfully
- walk: left leg forward
- work: counting coins
- talk: facing left, gesture
- cast: resting
- hurt: stumbling left

Art style: Ghibli-inspired, bright cheerful colors, warm friendly tones, soft round features. Character centered, feet at bottom 20% of frame. Transparent background. High detail, sharp edges, NO blur.
```

### Northwest（左上）
```
A single 1024x1024 sprite of a halfling merchant viewed from Northwest (back-left diagonal), top-down 45-degree angle for RPG game.

STATE: [idle/walk/work/talk/cast/hurt]

Character: Male halfling, back-left view, colorful vest, coin pouch.

Action details:
- idle: cheerful back stance
- walk: left foot forward
- work: handling items
- talk: head turned left
- cast: resting
- hurt: recoiling left

Art style: Ghibli-inspired, bright cheerful colors, warm friendly tones, soft round features. Character centered, feet at bottom 20% of frame. Transparent background. High detail, sharp edges, NO blur.
```

---

## 守卫（Guard）

### 角色描述
Male human guard. Chain mail armor, red tabard with crown symbol. Iron sword and wooden shield. Alert stance, 175cm height.

### 8 方向 × 6 状态
（提示词结构同上，替换角色描述）

Character: Male human guard, chain mail armor visible, red tabard with gold crown emblem, iron sword in right hand, wooden shield on left arm.

work 状态改为：patrolling or standing at attention

---

## 牧师（Priest）

### 角色描述
Female human priest. White and gold robes, hood. Holy symbol pendant. Wooden prayer book. Serene expression, 165cm height.

### 8 方向 × 6 状态
（提示词结构同上）

Character: Female human priest, white robes with gold trim, hood, holy symbol pendant, wooden prayer book.

cast 状态：holding holy symbol high, divine light glowing

---

## 旅店老板（Innkeeper）

### 角色描述
Middle-aged human male innkeeper. White shirt, brown vest, apron. Holding wooden mug or plate. Jovial face, 170cm height.

### 8 方向 × 6 状态
（提示词结构同上）

Character: Male human innkeeper, white shirt, brown vest, white apron, holding wooden mug.

work 状态：wiping mug with cloth or serving

---

## 炼金术士（Alchemist）

### 角色描述
Female elf alchemist. Green-teal robe, leather gloves. Holding small potion bottle. Focused expression, 170cm height.

### 8 方向 × 6 状态
（提示词结构同上）

Character: Female elf alchemist, green-teal robe, leather gloves, holding colorful potion bottle.

work 状态：mixing potions or examining bottle

---

## 猎人（Hunter）

### 角色描述
Male human hunter. Brown leather tunic, green cloak. Wooden bow and quiver on back. Rugged face, 175cm height.

### 8 方向 × 6 状态
（提示词结构同上）

Character: Male human hunter, brown leather tunic, green cloak, wooden bow in hand, quiver on back.

work 状态：drawing bow, aiming

---

## 矿工（Miner）

### 角色描述
Male dwarf miner. Dirty brown clothes, worn leather boots. Pickaxe and helmet with lantern. Tired but determined face, 135cm height.

### 8 方向 × 6 状态
（提示词结构同上）

Character: Male dwarf miner, dirty work clothes, helmet with lit lantern, pickaxe.

work 状态：swinging pickaxe at rock

---

## 组装说明

生成后将 48 张图按以下顺序排列：

```
第1行（idle）：  N NE E SE S SW W NW
第2行（walk）：  N NE E SE S SW W NW
第3行（work）：  N NE E SE S SW W NW
第4行（talk）：  N NE E SE S SW W NW
第5行（cast）：  N NE E SE S SW W NW
第6行（hurt）：  N NE E SE S SW W NW
```

每帧缩放到 64×64，组装为 512×384 Atlas。
