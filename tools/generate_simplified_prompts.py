"""
简化版 Sprite 生图提示词生成器

每个角色只生成 3 方向 × 3 状态 = 9 张图
方向：North(上), South(下), East(右)
状态：idle(静止), walk1(行走1), walk2(行走2)
"""

from pathlib import Path

OUTPUT_DIR = Path("docs/superpowers/assets/prompts_simplified")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 10 个角色的详细描述
CHARACTERS = {
    "human_farmer": {
        "name": "Human Farmer",
        "detailed_desc": """Middle-aged human male farmer with a weathered, kind face.
Character details:
- Age: Around 40-45 years old
- Build: Average height (170cm), slightly stocky build from physical labor
- Face: Round friendly face with smile lines, short brown beard neatly trimmed, warm brown eyes
- Hair: Short brown hair with slight graying at temples, slightly messy from work
- Clothing: Worn brown tunic (earth tone, #8B4513), patched beige linen pants rolled at ankles, simple rope belt
- Accessory: Wide-brimmed straw hat (golden wheat color) with small tear on brim, worn leather work boots
- Tool: Wooden hoe with weathered handle, metal blade shows signs of use
- Posture: Slightly hunched shoulders from farm work, callused hands
- Expression: Gentle smile, crow's feet around eyes from sun exposure""",
        "style": "Ghibli hand-painted, warm earthy palette (browns #8B4513, beiges #F5DEB3, greens #6B8E23)",
    },
    "elf_mage": {
        "name": "Elf Mage",
        "detailed_desc": """Graceful female elf mage with ethereal beauty.
Character details:
- Age appearance: Looks 25 but ancient, timeless grace
- Build: Tall and slender (175cm), elegant posture, long limbs
- Face: Delicate angular features, high cheekbones, almond-shaped violet eyes with inner glow
- Hair: Flowing silver-white hair reaching waist, slight wave, luminous strands
- Ears: Long pointed ears (4cm) extending upward through hair
- Clothing: Flowing robes in deep blue-purple gradient (#4B0082 to #8A2BE2), gold embroidered trim showing arcane symbols, wide sleeves
- Accessory: Thin silver circlet on forehead with sapphire gem, multiple silver rings with runes
- Tool: Tall wooden staff (her height + 20cm) with gnarled top, blue crystal orb hovering in grip, faint magical aura
- Posture: Upright and regal, movements fluid like water
- Expression: Serene wisdom, slight mysterious smile""",
        "style": "Ghibli magical fantasy, cool mystical palette (blues #4B0082, purples #8A2BE2, silver #C0C0C0, glowing effects)",
    },
    "dwarf_blacksmith": {
        "name": "Dwarf Blacksmith",
        "detailed_desc": """Sturdy male dwarf blacksmith with strong presence.
Character details:
- Age: Middle-aged (around 80 in dwarf years, appears 40s in human)
- Build: Short and broad (130cm tall, very wide shoulders), muscular arms, barrel chest
- Face: Square jaw with determination, thick brown beard braided with metal beads, deep-set brown eyes with spark
- Hair: Bald head with shine, massive beard to mid-chest in 3 braids with copper rings
- Skin: Weathered tan with soot marks, burn scars on forearms
- Clothing: Heavy leather apron (dark brown #654321) with burn marks and metal studs, thick brown work shirt with rolled sleeves showing muscular arms, worn leather pants
- Accessory: Thick leather gloves tucked in belt, tool belt with tongs and small hammers
- Tool: Large iron hammer (oversized, nearly as big as torso), well-worn oak handle, head shows forge marks
- Posture: Solid stance like mountain, feet planted wide, confident bearing
- Expression: Proud craftsman's grin, eyes gleam with passion for work""",
        "style": "Ghibli industrial fantasy, warm forge palette (browns #654321, iron grays #696969, orange glow #FF4500)",
    },
    "halfling_merchant": {
        "name": "Halfling Merchant",
        "detailed_desc": """Cheerful male halfling merchant with jovial personality.
Character details:
- Age: Young adult (around 30), youthful energy
- Build: Short and round (105cm), child-sized with slight belly, chubby cheeks
- Face: Round baby face with dimples, bright green eyes full of mischief, button nose, constant wide smile
- Hair: Curly brown hair (almost afro-like), unruly and bouncy, sideburns
- Feet: Large furry feet (barefoot as tradition), brown hair on top
- Clothing: Colorful patchwork vest (reds #DC143C, blues #4169E1, yellows #FFD700, greens #32CD32 in squares), white puffy shirt with ruffled collar, brown corduroy pants
- Accessory: Many coin pouches on belt (copper, silver, gold), small leather ledger book in pocket, golden pocket watch chain
- Tool: Leather coin purse in hand, abacus hanging from belt, merchant's scales (small brass)
- Posture: Bouncy energetic stance, often on toes with excitement, animated gestures
- Expression: Huge welcoming grin, eyes crinkled with genuine joy, very animated""",
        "style": "Ghibli cheerful bright, vibrant rainbow palette (reds #DC143C, golds #FFD700, multiple bright colors)",
    },
    "human_guard": {
        "name": "Human Guard",
        "detailed_desc": """Alert male human guard with disciplined bearing.
Character details:
- Age: Prime of life (around 30), peak physical condition
- Build: Tall and athletic (180cm), broad shoulders, visible muscle definition, trained physique
- Face: Strong square jaw, clean-shaven, steel-gray eyes with constant alertness, small scar on left cheek
- Hair: Short-cropped brown military cut, neat and practical
- Armor: Polished chain mail shirt (silver #C0C0C0 with sheen) over padded gambeson, red tabard with large gold crown emblem on chest
- Shield: Wooden kite shield on left arm (dark wood with same crown symbol), metal rim, leather straps visible
- Weapon: Iron longsword in right hand (well-maintained, sharp), leather-wrapped grip
- Legs: Chain mail leggings, sturdy leather boots
- Posture: Military at-attention stance, back straight, vigilant scanning, ready to move
- Expression: Serious and focused, eyes constantly scanning for threats, professional demeanor""",
        "style": "Ghibli military aesthetic, metallic palette (silvers #C0C0C0, reds #8B0000, gold accents #FFD700)",
    },
    "human_priest": {
        "name": "Human Priest",
        "detailed_desc": """Serene female human priest radiating peace.
Character details:
- Age: Mature (around 35-40), spiritual wisdom
- Build: Average height (165cm), slender graceful form, gentle movements
- Face: Peaceful oval face, kind hazel eyes with inner light, gentle smile, smooth complexion
- Hair: Long chestnut brown hair parted in middle, pulled back in simple bun, some strands frame face
- Clothing: Pure white robes (cream white #FFFDD0) floor-length with gold trim at hems, wide sleeves, simple cut
- Hood: White hood resting on shoulders, can be pulled up
- Accessory: Large golden holy symbol (sun with rays) on chest hanging from gold chain, simple silver ring
- Tool: Leather-bound prayer book with gold leaf pages, wooden rosary beads at belt
- Posture: Serene upright stance, hands often in prayer position, peaceful aura
- Expression: Gentle compassionate smile, eyes radiate kindness and understanding, tranquil""",
        "style": "Ghibli divine aesthetic, pure holy palette (whites #FFFDD0, golds #FFD700, soft glows)",
    },
    "human_innkeeper": {
        "name": "Human Innkeeper",
        "detailed_desc": """Jovial middle-aged male innkeeper with welcoming presence.
Character details:
- Age: Middle-aged (45-50), well-fed and content
- Build: Average height (172cm), slightly rotund belly from good food, strong arms from barrel-carrying
- Face: Round jovial face with full cheeks, thick brown mustache (handlebar style), twinkling blue eyes, laugh lines
- Hair: Thinning brown hair combed over, clean but simple style
- Clothing: Clean white linen shirt with rolled sleeves, brown leather vest (polished #8B4513), dark pants, white apron (slightly stained with ale/food)
- Accessory: Towel always on shoulder for wiping mugs, key ring with many brass keys at belt
- Tool: Wooden drinking mug (always carrying one), polishing cloth in apron pocket
- Posture: Open welcoming stance, often gesturing in friendly invitation, comfortable relaxed bearing
- Expression: Huge warm smile, genuine hospitality, eyes twinkle with friendliness, welcoming laugh""",
        "style": "Ghibli tavern warmth, cozy palette (browns #8B4513, cream #FFFDD0, warm amber tones)",
    },
    "elf_alchemist": {
        "name": "Elf Alchemist",
        "detailed_desc": """Focused female elf alchemist with scholarly air.
Character details:
- Age appearance: Looks young (early 20s) but has century of experience
- Build: Slender and petite (168cm), delicate but precise movements
- Face: Delicate features with focused intensity, sharp green eyes with analytical gaze, pointed chin
- Hair: Medium-length auburn hair tied back in practical ponytail, loose strands fall in face
- Ears: Pointed elf ears (3cm), often one exposed when hair tucked
- Clothing: Teal-green robe (#008080) with many pockets, rolled sleeves revealing pale arms, leather gloves with fingertips cut off for precision
- Apron: Leather alchemy apron with potion stains (various colors), tool loops holding vials
- Accessory: Magnifying goggles pushed up on forehead, many small vials on belt with colored liquids
- Tool: Currently holding small potion bottle (swirling purple-pink liquid with inner glow)
- Posture: Leaning forward slightly in concentration, examining potion closely, precise careful movements
- Expression: Intense focus with slight frown of concentration, scholarly curiosity, analytical""",
        "style": "Ghibli scholarly alchemy, jewel-tone palette (teals #008080, potion colors, mystical glows)",
    },
    "human_hunter": {
        "name": "Human Hunter",
        "detailed_desc": """Rugged male human hunter with wilderness skills.
Character details:
- Age: Prime hunting age (around 28-32), weathered by outdoors
- Build: Lean and athletic (178cm), wiry strong muscles, agile build
- Face: Angular face with sharp features, intense hazel eyes scanning, several days stubble, weathered tan skin
- Hair: Shaggy brown hair to collar, practical but unkempt, falls over forehead
- Clothing: Dark brown leather tunic (#5C4033) with camouflage pattern, forest green hooded cloak (#228B22), worn brown pants tucked into boots
- Hood: Green hood often up, helps blend with forest
- Gear: Leather quiver on back with 12 visible arrows (gray fletching), leather bracers on forearms
- Weapon: Wooden longbow (as tall as him) in strong hand, curved with carved notches for kills
- Boots: Tall leather hunting boots with silent soles
- Posture: Crouched slightly, ready to move silently, weight on balls of feet, alert scanning
- Expression: Serious focused intensity, eyes sharp like hawk, survival instincts visible""",
        "style": "Ghibli wilderness survival, forest palette (browns #5C4033, greens #228B22, earth tones)",
    },
    "dwarf_miner": {
        "name": "Dwarf Miner",
        "detailed_desc": """Hardworking male dwarf miner with determined spirit.
Character details:
- Age: Older working dwarf (around 100 dwarf years, looks 50s human), experienced
- Build: Short and sturdy (135cm), thick powerful arms, broad back, barrel-chested
- Face: Weathered square face with coal dust marks, thick gray-brown beard to waist (single thick braid), tired but determined brown eyes
- Hair: Hidden under helmet, beard shows gray streaking through brown
- Skin: Covered in rock dust and coal smudges, calloused hands
- Helmet: Heavy iron mining helmet with lit oil lantern mounted on front (orange flame glow), leather straps
- Clothing: Filthy brown work shirt (torn and patched), thick canvas pants with knee patches, heavy leather belt
- Boots: Steel-toed mining boots (scuffed and dented), thick leather
- Tool: Large iron pickaxe (well-used, chipped edge), sturdy oak handle worn smooth
- Gear: Coil of rope on belt, small ore pouch, water canteen
- Posture: Hunched from mine work, strong solid stance, ready to swing pickaxe
- Expression: Tired but proud, determination despite exhaustion, hardworking spirit""",
        "style": "Ghibli industrial underground, dark mining palette (browns #654321, iron grays, orange lantern glow #FF8C00)",
    },
}

# 3 个方向
DIRECTIONS = {
    "north": "back view (character facing away from viewer)",
    "south": "front view (character facing toward viewer)",
    "east": "right side view (character's right side visible)",
}

# 3 个状态
STATES = {
    "idle": "standing completely still in relaxed neutral pose, weight evenly distributed",
    "walk1": "mid-walking pose with RIGHT foot forward (lifted slightly off ground), LEFT foot back on ground, natural walking motion captured",
    "walk2": "mid-walking pose with LEFT foot forward (lifted slightly off ground), RIGHT foot back on ground, opposite phase of walk1",
}


def generate_prompt(char_id, char_data, direction, dir_desc, state, state_desc):
    """生成单个详细提示词"""

    prompt = f"""A single high-quality 1024x1024 pixel sprite for a top-down RPG game.

CHARACTER: {char_data["name"]} - {direction.upper()} view ({dir_desc})

DETAILED APPEARANCE:
{char_data["detailed_desc"]}

CURRENT POSE: {state.upper()}
{state_desc}

VIEWING ANGLE:
- Top-down perspective at 45-degree overhead angle
- {dir_desc}
- Character should appear as they would in a classic 2D RPG

ART STYLE:
Studio Ghibli inspired hand-painted illustration
{char_data["style"]}
- Soft painterly shading with clear black outlines (NOT thick, just defining)
- Warm organic textures, avoid digital/plastic look
- Expressive but not caricatured

TECHNICAL REQUIREMENTS:
- Character perfectly centered in 1024x1024 frame
- Character feet positioned at bottom 20% of image (leaving space above head)
- TRANSPARENT background (PNG with alpha channel, NO white/colored background)
- Consistent lighting (soft daylight from upper left)
- High detail with SHARP CRISP edges (NO blur, NO soft focus, NO motion blur)
- Character should maintain exact same clothing/colors/features across all poses
- Shadows cast directly below character (slightly darker ground shadow)

CONSISTENCY CRITICAL:
- Exact same clothing colors, patterns, accessories in every image
- Same face features, hair style, body proportions
- Same weathering/dirt marks, tool appearance
- This character will be animated - perfect visual consistency required
"""

    return prompt.strip()


def main():
    print("生成简化版提示词（每角色 9 张）...")

    total = 0
    for char_id, char_data in CHARACTERS.items():
        char_file = OUTPUT_DIR / f"{char_id}_simplified.txt"

        with open(char_file, 'w', encoding='utf-8') as f:
            f.write(f"# {char_data['name']} - Simplified Prompts\n")
            f.write(f"# Total: 9 prompts (3 directions × 3 states)\n")
            f.write(f"# Naming: {char_id}_{{direction}}_{{state}}.png\n\n")
            f.write("="*80 + "\n\n")

            for direction, dir_desc in DIRECTIONS.items():
                for state, state_desc in STATES.items():
                    prompt = generate_prompt(char_id, char_data, direction, dir_desc, state, state_desc)

                    f.write(f"## {char_id}_{direction}_{state}.png\n\n")
                    f.write(f"```\n{prompt}\n```\n\n")
                    f.write("-"*80 + "\n\n")

                    total += 1

        print(f"  ✓ {char_data['name']}: {char_file.name}")

    print(f"\n✓ 完成！总计 {total} 个提示词（每角色 9 张）")
    print(f"  输出目录: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
