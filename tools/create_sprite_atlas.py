#!/usr/bin/env python3
"""
Sprite Atlas 组装脚本

将 8 方向单排图扩展为 8方向×6状态的完整 Atlas
由于只有待机姿势，其他状态暂时复用待机帧
"""

from PIL import Image
from pathlib import Path

SPRITES_DIR = Path("frontend/public/assets/sprites")

# 6 种状态（目前只有 idle，其他复用）
STATES = ["idle", "walk", "work", "talk", "cast", "hurt"]

# 角色列表
CHARACTERS = [
    "human_farmer",
    "elf_mage",
    "dwarf_blacksmith",
    "halfling_merchant",
]


def create_atlas_from_8dir(character_id: str):
    """
    从 8 方向单排图创建完整 Atlas

    输入：1536x1024 图像（8 帧横向排列）
    输出：512x384 图像（8方向×6状态）
    """
    input_path = SPRITES_DIR / f"{character_id}_8dir.png"
    output_path = SPRITES_DIR / f"{character_id}_atlas.png"

    if not input_path.exists():
        print(f"  跳过 {character_id}（未找到 8dir 图）")
        return

    print(f"处理 {character_id}...")

    # 读取 8 方向图
    src_img = Image.open(input_path)
    src_width, src_height = src_img.size
    print(f"  原始尺寸: {src_width}x{src_height}")

    # 每帧尺寸
    frame_w = src_width // 8
    frame_h = src_height

    # 创建目标 Atlas（512x384 = 8×64 x 6×64）
    atlas = Image.new('RGBA', (512, 384), (0, 0, 0, 0))

    # 提取 8 个方向
    frames = []
    for i in range(8):
        x = i * frame_w
        frame = src_img.crop((x, 0, x + frame_w, frame_h))

        # 保持宽高比缩放到 64 高度
        aspect_ratio = frame_w / frame_h
        new_h = 64
        new_w = int(new_h * aspect_ratio)
        frame = frame.resize((new_w, new_h), Image.Resampling.LANCZOS)

        # 居中到 64x64 画布
        canvas = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
        paste_x = (64 - new_w) // 2
        canvas.paste(frame, (paste_x, 0))
        frames.append(canvas)

    # 组装 Atlas：6 行（状态）× 8 列（方向）
    for state_idx in range(6):
        for dir_idx in range(8):
            # 目前所有状态都用 idle 帧（frames[dir_idx]）
            # 后续可以替换为真实的状态帧
            x = dir_idx * 64
            y = state_idx * 64
            atlas.paste(frames[dir_idx], (x, y))

    # 保存
    atlas.save(output_path, "PNG", optimize=True)
    print(f"  保存为: {output_path.name} (512x384)")


def main():
    print("开始组装 Sprite Atlas...")
    for character in CHARACTERS:
        create_atlas_from_8dir(character)
    print("\n✓ Atlas 组装完成")


if __name__ == "__main__":
    main()
