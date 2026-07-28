"""
批量生成 Sprite - 多线程并发版本

使用线程池加速生成，默认 10 个并发
"""

import os
import time
from pathlib import Path
import dashscope
from dashscope import ImageSynthesis
import requests
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from dashscope_auth import require_dashscope_api_key

# API 配置
API_KEY = require_dashscope_api_key()
dashscope.api_key = API_KEY
dashscope.base_http_api_url = "https://llm-quyeui6kpjhryck7.cn-beijing.maas.aliyuncs.com/api/v1"

# 输出目录
OUTPUT_DIR = Path("frontend/public/assets/sprites/raw")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 提示词目录
PROMPTS_DIR = Path("docs/superpowers/assets/prompts")

# 进度文件
PROGRESS_FILE = Path("sprite_generation_progress.json")

# 并发数（降低到 5 避免限流）
MAX_WORKERS = 5

# 线程锁
progress_lock = threading.Lock()


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


def save_progress(completed):
    """线程安全保存进度"""
    with progress_lock:
        with open(PROGRESS_FILE, 'w') as f:
            json.dump({"completed": list(completed)}, f, indent=2)


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
            return False, f"提交失败: {resp.code}"

        task_id = resp.output.task_id

        # 轮询任务状态（最多 60 次）
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
                    return True, "成功"
                else:
                    return False, f"下载失败: {img_response.status_code}"

            elif task_status == "FAILED":
                return False, "任务失败"

        return False, "超时"

    except Exception as e:
        return False, f"异常: {str(e)}"


def worker(task):
    """工作线程"""
    idx, total, filename, prompt = task
    success, msg = generate_image(prompt, filename)

    status = "✓" if success else "✗"
    print(f"[{idx}/{total}] {status} {filename}")

    return filename, success


def main():
    print("="*80)
    print(f"批量生成 Sprite（{MAX_WORKERS} 并发）")
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

    # 构建任务列表（跳过已完成）
    tasks = []
    for idx, prompt_data in enumerate(all_prompts, 1):
        filename = prompt_data["filename"]
        if filename not in completed:
            tasks.append((idx, total, filename, prompt_data["prompt"]))

    if not tasks:
        print("✓ 所有图片已生成完成！")
        return

    print(f"开始并发生成（{MAX_WORKERS} 线程）...\n")

    # 使用线程池
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(worker, task): task for task in tasks}

        for future in as_completed(futures):
            filename, success = future.result()
            if success:
                completed.add(filename)
                save_progress(completed)

    print(f"\n✓ 完成！成功: {len(completed)}/{total}")


if __name__ == "__main__":
    main()
