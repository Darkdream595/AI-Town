"""
批量生成 Sprite - 使用 DashScope SDK

使用 SDK 方式批量生成所有 480 张 Sprite
"""

import os
import time
from pathlib import Path
import dashscope
from dashscope import ImageSynthesis
import requests

# API 配置
API_KEY = "REMOVED_DASHSCOPE_API_KEY"
dashscope.api_key = API_KEY
dashscope.base_http_api_url = "https://llm-quyeui6kpjhryck7.cn-beijing.maas.aliyuncs.com/api/v1"

# 输出目录
OUTPUT_DIR = Path("frontend/public/assets/sprites/raw")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 提示词目录
PROMPTS_DIR = Path("docs/superpowers/assets/prompts")

# 进度文件
PROGRESS_FILE = Path("sprite_generation_progress.json")


def parse_prompts_file(file_path):
    """解析提示词文件"""
    prompts = []
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    current_name = None
    current_prompt = []
    in_code_block = False

    for line in lines:
        if line.startswith("## ") and ".png" in line:
            if current_name and current_prompt:
                prompts.append({
                    "filename": current_name,
                    "prompt": "\n".join(current_prompt).strip()
                })
            current_name = line.replace("## ", "").strip()
            current_prompt = []
            in_code_block = False
        elif line.strip() == "```" and current_name:
            in_code_block = not in_code_block
        elif in_code_block and current_name:
            current_prompt.append(line.rstrip())

    if current_name and current_prompt:
        prompts.append({
            "filename": current_name,
            "prompt": "\n".join(current_prompt).strip()
        })

    return prompts


def generate_image(prompt, filename):
    """生成单张图片"""
    try:
        # 提交任务
        resp = ImageSynthesis.async_call(
            model='wanx-v1',
            prompt=prompt,
            size='1024*1024',
            n=1
        )

        if resp.status_code != 200:
            print(f"  ✗ 提交失败: {resp.code}")
            return False

        task_id = resp.output.task_id

        # 轮询任务状态（最多 60 次，每次 3 秒）
        for i in range(60):
            time.sleep(3)

            result = ImageSynthesis.fetch(task_id)

            if result.status_code != 200:
                continue

            task_status = result.output.task_status

            if task_status == "SUCCEEDED":
                # 下载图片
                image_url = result.output.results[0].url

                img_response = requests.get(image_url, timeout=60)
                if img_response.status_code == 200:
                    output_path = OUTPUT_DIR / filename
                    with open(output_path, 'wb') as f:
                        f.write(img_response.content)
                    return True
                else:
                    print(f"  ✗ 下载失败: {img_response.status_code}")
                    return False

            elif task_status == "FAILED":
                print(f"  ✗ 任务失败")
                return False

        print(f"  ✗ 超时")
        return False

    except Exception as e:
        print(f"  ✗ 异常: {e}")
        return False


def main():
    import json

    print("="*80)
    print("开始批量生成 Sprite")
    print("="*80)

    # 加载进度
    completed = set()
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, 'r') as f:
            progress = json.load(f)
            completed = set(progress.get("completed", []))

    # 收集所有提示词
    all_prompts = []
    for prompt_file in sorted(PROMPTS_DIR.glob("*_prompts.txt")):
        prompts = parse_prompts_file(prompt_file)
        all_prompts.extend(prompts)

    total = len(all_prompts)
    print(f"总计: {total} 个提示词")
    print(f"已完成: {len(completed)}")
    print(f"待生成: {total - len(completed)}\n")

    # 开始生成
    for idx, prompt_data in enumerate(all_prompts, 1):
        filename = prompt_data["filename"]
        prompt = prompt_data["prompt"]

        if filename in completed:
            print(f"[{idx}/{total}] ⊙ {filename} (已存在)")
            continue

        print(f"[{idx}/{total}] ⟳ {filename}")

        success = generate_image(prompt, filename)

        if success:
            print(f"[{idx}/{total}] ✓ {filename}")
            completed.add(filename)
        else:
            print(f"[{idx}/{total}] ✗ {filename}")

        # 保存进度
        with open(PROGRESS_FILE, 'w') as f:
            json.dump({"completed": list(completed)}, f, indent=2)

        # 延迟避免限流
        time.sleep(1)

    print(f"\n✓ 完成！成功: {len(completed)}/{total}")


if __name__ == "__main__":
    main()
