"""
提取 LPC Sprite Sheet 中需要的帧

从完整的 LPC sprite sheet（832x1344）中提取：
- 3 个方向：North(上), South(下), East(右)
- 每个方向 3 帧：idle, walk1, walk2
"""

from PIL import Image
from pathlib import Path

INPUT_DIR = Path("frontend/public/assets/sprites/raw")
OUTPUT_DIR = Path("frontend/public/assets/sprites/extracted")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# LPC Sprite Sheet 格式
TILE_SIZE = 64
SHEET_COLS = 13
SHEET_ROWS = 21

# 方向对应的行
DIRECTIONS = {
    "north": 8,   # 朝上
    "south": 10,  # 朝下
    "east": 9,    # 朝右
}

# 每个方向的帧（列索引）
# LPC 行走周期：idle(col 0), walk1(col 1), walk2(col 2), ...
FRAMES = {
    "idle": 0,
    "walk1": 1,
    "walk2": 2,
}


def extract_frame(sheet_path, row, col):
    """从 sprite sheet 中提取一帧"""
    try:
        sheet = Image.open(sheet_path)

        # 计算位置
        x = col * TILE_SIZE
        y = row * TILE_SIZE

        # 提取
        frame = sheet.crop((x, y, x + TILE_SIZE, y + TILE_SIZE))

        return frame
    except Exception as e:
        print(f"  ✗ 提取失败: {e}")
        return None


def process_character(sprite_path):
    """处理单个角色的 sprite sheet"""
    char_name = sprite_path.stem
    print(f"\n处理: {char_name}")

    extracted_count = 0

    for direction, row in DIRECTIONS.items():
        for state, col in FRAMES.items():
            frame = extract_frame(sprite_path, row, col)

            if frame:
                output_name = f"{char_name}_{direction}_{state}.png"
                output_path = OUTPUT_DIR / output_name

                frame.save(output_path)
                extracted_count += 1
                print(f"  ✓ {output_name}")

    print(f"  总计: {extracted_count}/9 帧")
    return extracted_count


def main():
    print("="*80)
    print("LPC Sprite Sheet 提取工具")
    print("="*80)

    sprite_files = list(INPUT_DIR.glob("*.png"))

    if not sprite_files:
        print("✗ 未找到 sprite sheet 文件")
        return

    print(f"找到 {len(sprite_files)} 个 sprite sheets\n")

    total_frames = 0

    for sprite_file in sorted(sprite_files):
        count = process_character(sprite_file)
        total_frames += count

    print(f"\n{'='*80}")
    print(f"✓ 完成！总计提取 {total_frames} 帧")
    print(f"输出目录: {OUTPUT_DIR}")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
