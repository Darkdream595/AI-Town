#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成 Phaser 3 Sprite Atlas JSON 配置
将 extracted 目录下的裁切帧转换为 Phaser atlas 格式
"""

import json
import os
import sys
from pathlib import Path
from PIL import Image
from typing import Dict, List, Tuple

# 设置标准输出编码为 UTF-8
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
EXTRACTED_DIR = PROJECT_ROOT / "frontend/public/assets/sprites/extracted"
OUTPUT_DIR = PROJECT_ROOT / "frontend/public/assets/sprites/atlases"

# 10个角色列表
CHARACTERS = [
    "human_farmer",
    "elf_mage",
    "dwarf_blacksmith",
    "halfling_merchant",
    "human_guard",
    "human_priest",
    "human_innkeeper",
    "elf_alchemist",
    "human_hunter",
    "dwarf_miner",
]

# LPC 标准动作类型（按优先级排序）
ACTIONS = [
    "spellcast",
    "thrust",
    "walk",
    "slash",
    "shoot",
    "hurt",
    "1h_backslash",
    "1h_slash",
    "dagger_slash",
    "rapier_thrust",
]

# 四个方向
DIRECTIONS = ["north", "east", "south", "west"]


def get_frame_info(image_path: Path) -> Tuple[int, int]:
    """获取图片尺寸"""
    with Image.open(image_path) as img:
        return img.size


def scan_character_frames(character_name: str) -> Dict[str, List[str]]:
    """
    扫描角色的所有帧文件，按动作+方向分组
    返回: {
        "walk_north": ["path/to/frame0.png", "path/to/frame1.png", ...],
        "walk_south": [...],
        ...
    }
    """
    char_dir = EXTRACTED_DIR / character_name
    if not char_dir.exists():
        print(f"⚠️  角色目录不存在: {char_dir}")
        return {}

    frames_by_anim = {}

    # 遍历所有 PNG 文件
    for png_file in sorted(char_dir.glob("*.png")):
        filename = png_file.stem  # 去掉 .png 扩展名

        # 解析文件名: {character}_{action}_{direction}_{frame}.png
        parts = filename.split("_")
        if len(parts) < 4:
            continue

        # 提取动作和方向（处理多词动作名如 1h_backslash）
        # 格式: human_farmer_walk_north_0.png
        #       human_farmer_1h_backslash_east_0.png

        # 从后往前解析：最后是帧号，倒数第二是方向
        frame_num = parts[-1]
        direction = parts[-2]

        # 剩余部分去掉角色名后就是动作
        action_parts = parts[2:-2]  # 跳过 character 的两个词（如果有）或一个词

        # 修正：直接用文件名匹配
        # 找到第一个匹配的方向，之前的都是动作
        direction_found = False
        action_name = ""
        for i, part in enumerate(parts):
            if part in DIRECTIONS:
                direction = part
                action_name = "_".join(parts[2:i])  # character 名后到方向前的部分
                direction_found = True
                break

        if not direction_found or not action_name:
            continue

        # 动画键: action_direction
        anim_key = f"{action_name}_{direction}"

        if anim_key not in frames_by_anim:
            frames_by_anim[anim_key] = []

        frames_by_anim[anim_key].append(str(png_file.relative_to(PROJECT_ROOT / "frontend/public")))

    # 按帧号排序每个动画的帧列表
    for anim_key in frames_by_anim:
        frames_by_anim[anim_key] = sorted(
            frames_by_anim[anim_key],
            key=lambda p: int(Path(p).stem.split("_")[-1])
        )

    return frames_by_anim


def generate_phaser_atlas(character_name: str, frames_by_anim: Dict[str, List[str]]) -> Dict:
    """
    生成 Phaser 3 Atlas JSON 格式

    Phaser atlas 格式:
    {
        "textures": [
            {
                "image": "character_name.png",  # 虚拟，我们用单独的帧
                "format": "RGBA8888",
                "size": {"w": 64, "h": 64},
                "scale": 1,
                "frames": [
                    {
                        "filename": "walk_north_0",
                        "frame": {"x": 0, "y": 0, "w": 64, "h": 64},
                        "sourceSize": {"w": 64, "h": 64},
                        "spriteSourceSize": {"x": 0, "y": 0, "w": 64, "h": 64}
                    },
                    ...
                ]
            }
        ],
        "meta": {
            "app": "AI Town Sprite Generator",
            "version": "1.0",
            "image": "character_name.png",
            "format": "RGBA8888",
            "size": {"w": 64, "h": 64},
            "scale": 1
        }
    }
    """

    if not frames_by_anim:
        return {}

    # 获取第一帧的尺寸作为基准
    first_frame_path = PROJECT_ROOT / "frontend/public" / frames_by_anim[list(frames_by_anim.keys())[0]][0]
    frame_width, frame_height = get_frame_info(first_frame_path)

    frames = []

    for anim_key, frame_paths in frames_by_anim.items():
        for frame_path in frame_paths:
            # 帧名：去掉角色名前缀
            # 例如: assets/sprites/extracted/human_farmer/human_farmer_walk_north_0.png
            #       -> walk_north_0
            frame_name = Path(frame_path).stem.replace(f"{character_name}_", "")

            frames.append({
                "filename": frame_name,
                "frame": {"x": 0, "y": 0, "w": frame_width, "h": frame_height},
                "rotated": False,
                "trimmed": False,
                "spriteSourceSize": {"x": 0, "y": 0, "w": frame_width, "h": frame_height},
                "sourceSize": {"w": frame_width, "h": frame_height},
                "pivot": {"x": 0.5, "y": 1.0}  # 锚点在脚底中心
            })

    atlas = {
        "frames": frames,
        "meta": {
            "app": "AI Town Sprite Generator",
            "version": "1.0",
            "image": f"{character_name}.png",
            "format": "RGBA8888",
            "size": {"w": frame_width, "h": frame_height},
            "scale": 1
        }
    }

    return atlas


def generate_animation_config(character_name: str, frames_by_anim: Dict[str, List[str]]) -> Dict:
    """
    生成动画配置，供前端使用

    返回格式:
    {
        "walk_north": {
            "frames": ["walk_north_0", "walk_north_1", ...],
            "frameRate": 10,
            "repeat": -1
        },
        ...
    }
    """

    animations = {}

    for anim_key, frame_paths in frames_by_anim.items():
        frame_names = [
            Path(fp).stem.replace(f"{character_name}_", "")
            for fp in frame_paths
        ]

        # 判断是否循环动画
        # walk 是循环，其他战斗动作通常不循环
        is_loop = "walk" in anim_key or "idle" in anim_key

        animations[anim_key] = {
            "frames": frame_names,
            "frameRate": 10,  # 10 fps
            "repeat": -1 if is_loop else 0  # -1 无限循环，0 播放一次
        }

    return animations


def main():
    """主函数"""
    print("=" * 60)
    print("生成 Phaser Sprite Atlas 配置")
    print("=" * 60)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    all_manifests = {}

    for character in CHARACTERS:
        print(f"\n处理角色: {character}")

        # 扫描帧文件
        frames_by_anim = scan_character_frames(character)

        if not frames_by_anim:
            print(f"  ⚠️  未找到帧文件，跳过")
            continue

        print(f"  ✓ 找到 {len(frames_by_anim)} 个动画")
        for anim_key, frames in frames_by_anim.items():
            print(f"    - {anim_key}: {len(frames)} 帧")

        # 生成 atlas JSON
        atlas = generate_phaser_atlas(character, frames_by_anim)
        atlas_path = OUTPUT_DIR / f"{character}.json"
        with open(atlas_path, "w", encoding="utf-8") as f:
            json.dump(atlas, f, indent=2, ensure_ascii=False)
        print(f"  ✓ 生成 atlas: {atlas_path.relative_to(PROJECT_ROOT)}")

        # 生成动画配置
        animations = generate_animation_config(character, frames_by_anim)
        anim_config_path = OUTPUT_DIR / f"{character}_animations.json"
        with open(anim_config_path, "w", encoding="utf-8") as f:
            json.dump(animations, f, indent=2, ensure_ascii=False)
        print(f"  ✓ 生成动画配置: {anim_config_path.relative_to(PROJECT_ROOT)}")

        # 添加到总清单
        all_manifests[character] = {
            "atlas": str(atlas_path.relative_to(PROJECT_ROOT / "frontend/public")),
            "animations": str(anim_config_path.relative_to(PROJECT_ROOT / "frontend/public")),
            "frame_count": sum(len(frames) for frames in frames_by_anim.values()),
            "animations_list": list(frames_by_anim.keys())
        }

    # 生成总清单
    manifest_path = OUTPUT_DIR / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(all_manifests, f, indent=2, ensure_ascii=False)
    print(f"\n✓ 生成总清单: {manifest_path.relative_to(PROJECT_ROOT)}")

    print("\n" + "=" * 60)
    print(f"✅ 完成！共处理 {len(all_manifests)} 个角色")
    print("=" * 60)


if __name__ == "__main__":
    main()
