#!/usr/bin/env python3
"""
资源后处理脚本

处理生成的图像：
1. 重命名中文文件名为英文
2. 缩放地图到 2048x2048
3. 切割 Sprite 为 Atlas（如果是单排的话）
"""

from PIL import Image
from pathlib import Path
import shutil

ASSETS_DIR = Path("frontend/public/assets")
MAPS_DIR = ASSETS_DIR / "maps"
SPRITES_DIR = ASSETS_DIR / "sprites"


def process_maps():
    """处理地图：重命名 + 缩放到 2048x2048"""
    print("处理地图...")

    rename_map = {
        "王冠溪镇（Crown Creek Town）.png": "crown_creek_town_base.png",
        "暮语森林（Twilight Whisper Forest）.png": "twilight_whisper_forest_base.png",
        "银烬矿洞（Silver Ash Mine）.png": "silver_ash_mine_base.png",
    }

    for old_name, new_name in rename_map.items():
        old_path = MAPS_DIR / old_name
        new_path = MAPS_DIR / new_name

        if old_path.exists():
            print(f"  处理: {old_name}")
            img = Image.open(old_path)
            print(f"    原始尺寸: {img.size}")

            # 缩放到 2048x2048
            if img.size != (2048, 2048):
                img = img.resize((2048, 2048), Image.Resampling.LANCZOS)
                print(f"    缩放到: {img.size}")

            # 保存
            img.save(new_path, "PNG", optimize=True)
            print(f"    保存为: {new_name}")

            # 删除旧文件
            old_path.unlink()
        else:
            print(f"  跳过（未找到）: {old_name}")


def process_sprites():
    """处理 Sprite：重命名"""
    print("\n处理 Sprite...")

    # 这些是 8 方向单排的，暂时只重命名
    # 后续如果需要切割成 Atlas，再手动处理
    rename_map = {
        "人类农夫（Human Farmer 8 方向待机姿势）.png": "human_farmer_8dir.png",
        "精灵魔法师（Elf Mage 8 方向待机姿势）.png": "elf_mage_8dir.png",
        "矮人铁匠（Dwarf Blacksmith 8 方向待机姿势）.png": "dwarf_blacksmith_8dir.png",
        "半身人商人（Halfling Merchant 8 方向待机姿势）.png": "halfling_merchant_8dir.png",
        "人类农夫（Human Farmer 6 状态变体 - 以朝南为例）.png": "human_farmer_6states_south.png",
    }

    for old_name, new_name in rename_map.items():
        old_path = SPRITES_DIR / old_name
        new_path = SPRITES_DIR / new_name

        if old_path.exists():
            print(f"  重命名: {old_name} -> {new_name}")
            img = Image.open(old_path)
            print(f"    尺寸: {img.size}")
            img.save(new_path, "PNG", optimize=True)
            old_path.unlink()
        else:
            print(f"  跳过（未找到）: {old_name}")


if __name__ == "__main__":
    print("开始处理资源...")
    process_maps()
    process_sprites()
    print("\n✓ 处理完成")
