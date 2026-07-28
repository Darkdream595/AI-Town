"""
批量生成 Sprite 图片脚本

使用 Qwen 生图模型批量生成 480 张 Sprite
"""

import os
import json
import time
from pathlib import Path
import requests
from openai import OpenAI

from dashscope_auth import require_dashscope_api_key

# API 配置
API_KEY = require_dashscope_api_key()
BASE_URL = "https://llm-quyeui6kpjhryck7.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"

# 输出目录
OUTPUT_DIR = Path("frontend/public/assets/sprites/raw")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 提示词目录
PROMPTS_DIR = Path("docs/superpowers/assets/prompts")

# 进度文件
PROGRESS_FILE = Path("sprite_generation_progress.json")


def load_progress():
    """加载生成进度"""
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, 'r') as f:
            return json.load(f)
    return {"completed": [], "failed": []}


def save_progress(progress):
    """保存生成进度"""
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f, indent=2)


def parse_prompts_file(file_path):
    """解析提示词文件，提取所有提示词"""
    prompts = []

    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    current_name = None
    current_prompt = []
    in_code_block = False

    for line in lines:
        if line.startswith("## ") and ".png" in line:
            # 保存上一个提示词
            if current_name and current_prompt:
                prompts.append({
                    "filename": current_name,
                    "prompt": "\n".join(current_prompt).strip()
                })

            # 开始新提示词
            current_name = line.replace("## ", "").strip()
            current_prompt = []
            in_code_block = False

        elif line.strip() == "```" and current_name:
            in_code_block = not in_code_block

        elif in_code_block and current_name:
            current_prompt.append(line.rstrip())

    # 保存最后一个
    if current_name and current_prompt:
        prompts.append({
            "filename": current_name,
            "prompt": "\n".join(current_prompt).strip()
        })

    return prompts


def test_connection():
    """测试 API 连接"""
    print("测试 DashScope API 连接...")

    try:
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable"
        }

        # 测试简单的生图请求
        response = requests.post(
            "https://llm-quyeui6kpjhryck7.cn-beijing.maas.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis",
            headers=headers,
            json={
                "model": "wanx-v1",
                "input": {"prompt": "test connection"},
                "parameters": {"size": "1024*1024"}
            },
            timeout=30
        )

        if response.status_code in [200, 202]:
            print(f"✓ API 连接成功 (异步模式)")
            return True
        else:
            print(f"✗ API 返回错误: {response.status_code}")
            print(f"  {response.text[:200]}")
            return False

    except Exception as e:
        print(f"✗ API 连接失败: {e}")
        return False


def generate_image(prompt, filename):
    """生成单张图片（异步模式）"""
    try:
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable"
        }

        # 提交生图任务
        response = requests.post(
            "https://llm-quyeui6kpjhryck7.cn-beijing.maas.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis",
            headers=headers,
            json={
                "model": "wanx-v1",
                "input": {"prompt": prompt},
                "parameters": {"size": "1024*1024", "n": 1}
            },
            timeout=30
        )

        if response.status_code != 200:
            print(f"  ✗ 提交失败: {response.status_code} - {response.text[:200]}")
            return False

        result = response.json()
        task_id = result.get("output", {}).get("task_id")

        if not task_id:
            print(f"  ✗ 未获取到 task_id")
            return False

        # 轮询任务状态
        max_retries = 60
        for i in range(max_retries):
            time.sleep(3)

            status_response = requests.get(
                f"https://llm-quyeui6kpjhryck7.cn-beijing.maas.aliyuncs.com/api/v1/tasks/{task_id}",
                headers=headers,
                timeout=30
            )

            if status_response.status_code != 200:
                continue

            status_data = status_response.json()
            task_status = status_data.get("output", {}).get("task_status")

            if task_status == "SUCCEEDED":
                image_url = status_data.get("output", {}).get("results", [{}])[0].get("url")

                if image_url:
                    # 下载图片
                    img_response = requests.get(image_url, timeout=60)
                    if img_response.status_code == 200:
                        output_path = OUTPUT_DIR / filename
                        with open(output_path, 'wb') as f:
                            f.write(img_response.content)
                        return True

            elif task_status == "FAILED":
                print(f"  ✗ 任务失败")
                return False

        print(f"  ✗ 超时（{max_retries * 3}秒）")
        return False

    except Exception as e:
        print(f"  ✗ 生成失败: {e}")
        return False


def main():
    print("="*80)
    print("Sprite 批量生图脚本")
    print("="*80)

    # 测试连接
    if not test_connection():
        print("\n请检查 API 配置后重试")
        return

    # 加载进度
    progress = load_progress()
    completed = set(progress["completed"])
    failed = set(progress["failed"])

    # 收集所有提示词
    all_prompts = []
    for prompt_file in sorted(PROMPTS_DIR.glob("*_prompts.txt")):
        character = prompt_file.stem.replace("_prompts", "")
        prompts = parse_prompts_file(prompt_file)
        all_prompts.extend(prompts)
        print(f"加载: {character} ({len(prompts)} 个提示词)")

    total = len(all_prompts)
    print(f"\n总计: {total} 个提示词")
    print(f"已完成: {len(completed)}")
    print(f"待生成: {total - len(completed)}")

    if len(completed) == total:
        print("\n✓ 所有图片已生成完成！")
        return

    # 开始生成
    print("\n开始批量生成...\n")

    for idx, prompt_data in enumerate(all_prompts, 1):
        filename = prompt_data["filename"]
        prompt = prompt_data["prompt"]

        # 跳过已完成的
        if filename in completed:
            print(f"[{idx}/{total}] ⊙ {filename} (已存在)")
            continue

        print(f"[{idx}/{total}] ⟳ 生成中: {filename}")

        success = generate_image(prompt, filename)

        if success:
            print(f"[{idx}/{total}] ✓ 完成: {filename}")
            completed.add(filename)
            progress["completed"] = list(completed)
        else:
            print(f"[{idx}/{total}] ✗ 失败: {filename}")
            failed.add(filename)
            progress["failed"] = list(failed)

        # 保存进度
        save_progress(progress)

        # 延迟避免 API 限流
        if idx < total:
            time.sleep(2)

    # 最终报告
    print("\n" + "="*80)
    print("生成完成！")
    print(f"成功: {len(completed)}/{total}")
    print(f"失败: {len(failed)}/{total}")

    if failed:
        print("\n失败列表：")
        for f in sorted(failed):
            print(f"  - {f}")

    print(f"\n输出目录: {OUTPUT_DIR}")


if __name__ == "__main__":
    try:
        main()
    finally:
        # 清理敏感信息（注释掉以便调试）
        # if PROGRESS_FILE.exists():
        #     PROGRESS_FILE.unlink()
        pass
