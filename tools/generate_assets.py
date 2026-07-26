#!/usr/bin/env python3
"""
资源生成管线

用途：
- 调用图像模型 API 生成地图底图
- 生成角色 Sprite Atlas（8 方向 × 6 状态）
- 生成 Asset Manifest JSON

使用方法：
    # 生成地图
    python tools/generate_assets.py --type map --region crown_creek_town

    # 生成角色 Sprite
    python tools/generate_assets.py --type sprite --character human_farmer

    # 生成所有资源
    python tools/generate_assets.py --all
"""

import argparse
import json
import os
from pathlib import Path
from typing import Dict, List, Optional
import hashlib


# 资源输出目录
ASSETS_DIR = Path(__file__).parent.parent / "frontend" / "public" / "assets"
MAPS_DIR = ASSETS_DIR / "maps"
SPRITES_DIR = ASSETS_DIR / "sprites"
MANIFESTS_DIR = ASSETS_DIR / "manifests"


# Sprite 规格（符合 DOC-RENDER-004）
SPRITE_SPEC = {
    "frame_width": 64,
    "frame_height": 64,
    "directions": ["N", "NE", "E", "SE", "S", "SW", "W", "NW"],  # 8 方向
    "states": ["idle", "walk", "work", "talk", "cast", "hurt"],  # 6 状态
    "atlas_layout": "horizontal",  # 横向排列
    "atlas_width": 64 * 8,   # 512px (8 帧宽)
    "atlas_height": 64 * 6,  # 384px (6 帧高)
}


# 地图切片规格（符合 DOC-RENDER-003）
MAP_SLICE_SPEC = {
    "slice_size": 512,  # 512×512 像素
    "tile_size": 32,    # 每瓦片 32 像素
    "tiles_per_slice": 16,  # 16×16 瓦片
    "lod_levels": [0, 1, 2],  # LOD 0/1/2（原始、50%、25%）
}


def generate_map_placeholder(region_id: str, output_dir: Path) -> Dict:
    """
    生成地图占位图（纯色 + 网格）

    真实实现应调用图像模型 API
    """
    print(f"生成地图占位图：{region_id}")

    # TODO: 调用图像模型 API
    # 目前生成程序化占位图
    import PIL.Image
    import PIL.ImageDraw

    # 创建 1024×1024 占位图
    size = 1024
    img = PIL.Image.new('RGB', (size, size), color=(120, 150, 80))  # 草绿色
    draw = PIL.ImageDraw.Draw(img)

    # 绘制网格（每 32 像素）
    for x in range(0, size, 32):
        draw.line([(x, 0), (x, size)], fill=(100, 130, 70), width=1)
    for y in range(0, size, 32):
        draw.line([(0, y), (size, y)], fill=(100, 130, 70), width=1)

    # 保存
    output_path = output_dir / f"{region_id}_base.png"
    img.save(output_path)

    return {
        "region_id": region_id,
        "path": f"assets/maps/{region_id}_base.png",
        "width": size,
        "height": size,
        "tile_size": 32,
    }


def generate_sprite_placeholder(character_id: str, output_dir: Path) -> Dict:
    """
    生成角色 Sprite 占位 Atlas（纯色块）

    真实实现应调用图像模型 API
    """
    print(f"生成 Sprite 占位图：{character_id}")

    # TODO: 调用图像模型 API
    # 目前生成程序化占位图
    import PIL.Image
    import PIL.ImageDraw

    width = SPRITE_SPEC["atlas_width"]
    height = SPRITE_SPEC["atlas_height"]
    frame_w = SPRITE_SPEC["frame_width"]
    frame_h = SPRITE_SPEC["frame_height"]

    img = PIL.Image.new('RGBA', (width, height), color=(0, 0, 0, 0))  # 透明背景
    draw = PIL.ImageDraw.Draw(img)

    # 为每个状态绘制不同颜色的简单形状
    colors = {
        "idle": (100, 100, 255),    # 蓝
        "walk": (100, 255, 100),    # 绿
        "work": (255, 200, 100),    # 橙
        "talk": (255, 100, 255),    # 紫
        "cast": (100, 255, 255),    # 青
        "hurt": (255, 100, 100),    # 红
    }

    for state_idx, state in enumerate(SPRITE_SPEC["states"]):
        for dir_idx in range(8):
            x = dir_idx * frame_w
            y = state_idx * frame_h
            color = colors[state]

            # 绘制圆形占位符
            padding = 10
            draw.ellipse(
                [x + padding, y + padding, x + frame_w - padding, y + frame_h - padding],
                fill=color,
                outline=(0, 0, 0)
            )

    # 保存
    output_path = output_dir / f"{character_id}_atlas.png"
    img.save(output_path)

    return {
        "character_id": character_id,
        "path": f"assets/sprites/{character_id}_atlas.png",
        "frame_width": frame_w,
        "frame_height": frame_h,
        "frames": {
            state: {
                direction: {
                    "x": dir_idx * frame_w,
                    "y": state_idx * frame_h,
                    "w": frame_w,
                    "h": frame_h
                }
                for dir_idx, direction in enumerate(SPRITE_SPEC["directions"])
            }
            for state_idx, state in enumerate(SPRITE_SPEC["states"])
        }
    }


def generate_asset_manifest(maps: List[Dict], sprites: List[Dict], output_path: Path):
    """生成 Asset Manifest JSON"""
    manifest = {
        "version": "1.0.0",
        "generated_at": "2026-07-26T23:00:00Z",
        "maps": maps,
        "sprites": sprites,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"✓ Manifest 已生成：{output_path}")


def main():
    parser = argparse.ArgumentParser(description="AI Town 资源生成管线")
    parser.add_argument('--type', choices=['map', 'sprite'], help="资源类型")
    parser.add_argument('--region', help="地图区域 ID（如 crown_creek_town）")
    parser.add_argument('--character', help="角色 ID（如 human_farmer）")
    parser.add_argument('--all', action='store_true', help="生成所有默认资源")
    parser.add_argument('--style', default="hand-painted japanese western fantasy", help="美术风格提示词")

    args = parser.parse_args()

    # 创建输出目录
    MAPS_DIR.mkdir(parents=True, exist_ok=True)
    SPRITES_DIR.mkdir(parents=True, exist_ok=True)
    MANIFESTS_DIR.mkdir(parents=True, exist_ok=True)

    maps = []
    sprites = []

    if args.all:
        # 生成所有默认资源
        print("生成所有默认资源...")

        # 3 个地图
        for region in ["crown_creek_town", "twilight_whisper_forest", "silver_ash_mine"]:
            maps.append(generate_map_placeholder(region, MAPS_DIR))

        # 10 个角色
        for character in ["human_farmer", "elf_mage", "dwarf_blacksmith", "halfling_merchant"]:
            sprites.append(generate_sprite_placeholder(character, SPRITES_DIR))

    elif args.type == 'map' and args.region:
        maps.append(generate_map_placeholder(args.region, MAPS_DIR))

    elif args.type == 'sprite' and args.character:
        sprites.append(generate_sprite_placeholder(args.character, SPRITES_DIR))

    else:
        parser.print_help()
        return

    # 生成 Manifest
    if maps or sprites:
        generate_asset_manifest(maps, sprites, MANIFESTS_DIR / "assets.json")
        print("\n✓ 资源生成完成")


if __name__ == "__main__":
    main()
