#!/usr/bin/env python3
"""
生成所有 Sprite 的独立提示词

10 角色 × 8 方向 × 6 状态 = 480 个提示词
"""

from pathlib import Path

OUTPUT_DIR = Path("docs/superpowers/assets/prompts")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 角色定义
CHARACTERS = {
    "human_farmer": {
        "name": "Human Farmer",
        "desc": "Middle-aged human male farmer. Brown tunic, beige pants, straw hat. Wooden hoe. Short brown beard. Average build, 170cm tall.",
        "colors": "Warm earthy colors (browns, beiges, greens)",
        "actions": {
            "work": "bent over, hoe striking ground, tilling soil",
            "cast": "Resting pose (farmers don't cast spells) - standing still, hoe resting",
        }
    },
    "elf_mage": {
        "name": "Elf Mage",
        "desc": "Graceful female elf mage. Long silver hair, pointed ears. Blue-purple flowing robes with gold trim. Wooden staff with glowing blue crystal. Elegant posture, 175cm tall.",
        "colors": "Blue-purple robes, silver hair, magical glow effects",
        "actions": {
            "work": "studying scroll or meditating",
            "cast": "staff raised high, crystal glowing bright, casting spell with magical energy",
        }
    },
    "dwarf_blacksmith": {
        "name": "Dwarf Blacksmith",
        "desc": "Sturdy male dwarf blacksmith. Thick brown beard, bald head. Leather apron over brown shirt. Large iron hammer. Confident strong stance, 130cm tall.",
        "colors": "Brown leather, dark metal, earthy industrial tones",
        "actions": {
            "work": "swinging hammer down on anvil, sparks flying",
            "cast": "Resting pose - standing sturdy",
        }
    },
    "halfling_merchant": {
        "name": "Halfling Merchant",
        "desc": "Cheerful male halfling merchant. Short height (child-sized), friendly round face. Colorful patchwork vest, brown pants. Small coin pouch at belt. Welcoming expression, 105cm tall.",
        "colors": "Bright cheerful colors, colorful patchwork patterns",
        "actions": {
            "work": "counting coins or writing in ledger",
            "cast": "Resting pose - cheerful stance",
        }
    },
    "human_guard": {
        "name": "Human Guard",
        "desc": "Male human guard. Chain mail armor, red tabard with gold crown emblem. Iron sword in right hand, wooden shield on left arm. Alert stance, 175cm tall.",
        "colors": "Metallic silver, red tabard, gold emblem",
        "actions": {
            "work": "standing at attention or patrolling",
            "cast": "Resting pose - alert guard stance",
        }
    },
    "human_priest": {
        "name": "Human Priest",
        "desc": "Female human priest. White robes with gold trim, hood. Holy symbol pendant on chest. Wooden prayer book. Serene expression, 165cm tall.",
        "colors": "White and gold, holy glow effects",
        "actions": {
            "work": "praying or reading from prayer book",
            "cast": "holding holy symbol high, divine light glowing",
        }
    },
    "human_innkeeper": {
        "name": "Human Innkeeper",
        "desc": "Middle-aged male innkeeper. White shirt, brown vest, white apron. Wooden mug in hand. Jovial friendly face, 170cm tall.",
        "colors": "White, brown, warm tavern tones",
        "actions": {
            "work": "wiping mug with cloth or serving drinks",
            "cast": "Resting pose - friendly stance",
        }
    },
    "elf_alchemist": {
        "name": "Elf Alchemist",
        "desc": "Female elf alchemist. Green-teal robe, leather gloves. Holding small colorful potion bottle. Pointed ears, focused expression, 170cm tall.",
        "colors": "Green-teal robes, colorful potion liquids",
        "actions": {
            "work": "mixing potions or examining bottle closely",
            "cast": "Resting pose - holding potion",
        }
    },
    "human_hunter": {
        "name": "Human Hunter",
        "desc": "Male human hunter. Brown leather tunic, green hooded cloak. Wooden bow in hand, quiver with arrows on back. Rugged weathered face, 175cm tall.",
        "colors": "Brown leather, forest green, natural earth tones",
        "actions": {
            "work": "drawing bow, aiming arrow",
            "cast": "Resting pose - bow lowered",
        }
    },
    "dwarf_miner": {
        "name": "Dwarf Miner",
        "desc": "Male dwarf miner. Dirty brown work clothes, worn leather boots. Iron pickaxe. Metal helmet with lit lantern attached. Tired but determined face, 135cm tall.",
        "colors": "Dirty browns, metallic grays, orange lantern glow",
        "actions": {
            "work": "swinging pickaxe at rock wall",
            "cast": "Resting pose - pickaxe lowered",
        }
    },
}

DIRECTIONS = {
    "north": "View from behind (North direction)",
    "northeast": "View from back-right diagonal (Northeast direction)",
    "east": "View from right side (East direction)",
    "southeast": "View from front-right diagonal (Southeast direction)",
    "south": "View from front (South direction)",
    "southwest": "View from front-left diagonal (Southwest direction)",
    "west": "View from left side (West direction)",
    "northwest": "View from back-left diagonal (Northwest direction)",
}

STATES = {
    "idle": "Standing still (idle). Relaxed posture, weapon/tool at rest.",
    "walk": "Walking forward. One foot raised mid-step, natural gait.",
    "talk": "Talking - head turned or facing forward, one hand raised in friendly gesture.",
    "hurt": "Hurt - recoiling or stumbling, one hand on body in pain, pained expression.",
}


def generate_prompt(char_id, char_data, direction, dir_desc, state, state_desc):
    """生成单个提示词"""

    # 特殊动作
    if state == "work":
        action_desc = char_data["actions"]["work"]
    elif state == "cast":
        action_desc = char_data["actions"]["cast"]
    else:
        action_desc = state_desc

    prompt = f"""A single 1024x1024 pixel sprite for a top-down RPG game. {dir_desc}, 45-degree overhead angle.

Character: {char_data["desc"]}

Action: {action_desc}

Art style: Studio Ghibli inspired hand-painted art. {char_data["colors"]}. Clean black outlines. Soft shading.

Technical: Character centered in frame. Feet positioned at bottom 20% of image. Transparent PNG background. High detail with sharp crisp edges - NO blur or soft focus. Top-down 45-degree perspective for RPG sprite.
"""

    return prompt.strip()


def main():
    print("生成所有 Sprite 提示词...")

    total = 0
    for char_id, char_data in CHARACTERS.items():
        char_file = OUTPUT_DIR / f"{char_id}_prompts.txt"

        with open(char_file, 'w', encoding='utf-8') as f:
            f.write(f"# {char_data['name']} - All Prompts\n")
            f.write(f"# Total: 48 prompts (8 directions × 6 states)\n")
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

    print(f"\n✓ 完成！总计 {total} 个提示词")
    print(f"  输出目录: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
