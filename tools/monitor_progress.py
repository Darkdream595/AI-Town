"""
实时监控 Sprite 生成进度

在终端显示进度条和统计信息
"""

import time
import json
from pathlib import Path
import sys

PROGRESS_FILE = Path("sprite_generation_progress.json")
OUTPUT_DIR = Path("frontend/public/assets/sprites/raw")
TOTAL = 90  # 简化版只有 90 张


def get_progress():
    """获取当前进度"""
    completed = 0
    if PROGRESS_FILE.exists():
        try:
            with open(PROGRESS_FILE, 'r') as f:
                data = json.load(f)
                completed = len(data.get("completed", []))
        except:
            pass

    # 同时统计实际生成的文件数
    actual_files = 0
    if OUTPUT_DIR.exists():
        actual_files = len(list(OUTPUT_DIR.glob("*.png")))

    return completed, actual_files


def draw_progress_bar(current, total, width=50):
    """绘制进度条"""
    percent = current / total
    filled = int(width * percent)
    bar = '█' * filled + '░' * (width - filled)
    return f"[{bar}] {percent*100:.1f}%"


def main():
    print("Sprite 生成进度监控")
    print("按 Ctrl+C 退出")
    print("="*70)

    last_count = -1
    start_time = time.time()

    try:
        while True:
            completed, actual_files = get_progress()

            # 清屏（简单版）
            if last_count != completed:
                sys.stdout.write('\r' + ' ' * 70 + '\r')

            # 显示进度
            progress_bar = draw_progress_bar(completed, TOTAL)
            elapsed = time.time() - start_time

            if completed > 0:
                rate = completed / elapsed
                remaining = (TOTAL - completed) / rate if rate > 0 else 0
                eta_min = int(remaining / 60)
                eta_sec = int(remaining % 60)
            else:
                rate = 0
                eta_min = eta_sec = 0

            # 打印信息
            sys.stdout.write(
                f"\r进度: {completed}/{TOTAL} {progress_bar} | "
                f"文件: {actual_files} | "
                f"速度: {rate:.2f} 张/秒 | "
                f"预计剩余: {eta_min:02d}:{eta_sec:02d}"
            )
            sys.stdout.flush()

            last_count = completed

            # 完成检测
            if completed >= TOTAL:
                print("\n\n✓ 所有图片生成完成！")
                break

            time.sleep(2)

    except KeyboardInterrupt:
        print("\n\n监控已停止")


if __name__ == "__main__":
    main()
