"""
简化的测试脚本 - 生成 1 张图验证流程
"""
import requests
import time
from pathlib import Path

API_KEY = "REMOVED_DASHSCOPE_API_KEY"
OUTPUT_DIR = Path("frontend/public/assets/sprites/raw")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def generate_test_image():
    print("开始测试生成...")

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable"
    }

    prompt = "A single 1024x1024 pixel sprite of a human farmer viewed from behind, top-down 45-degree angle for RPG game. Standing still. Brown tunic, straw hat. Studio Ghibli style. Transparent background."

    # 提交任务
    print("1. 提交生图任务...")
    resp = requests.post(
        "https://llm-quyeui6kpjhryck7.cn-beijing.maas.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis",
        headers=headers,
        json={
            "model": "wanx-v1",
            "input": {"prompt": prompt},
            "parameters": {"size": "1024*1024", "n": 1}
        },
        timeout=30
    )

    print(f"   状态码: {resp.status_code}")

    if resp.status_code != 200:
        print(f"   错误: {resp.text}")
        return False

    data = resp.json()
    task_id = data.get("output", {}).get("task_id")
    print(f"   Task ID: {task_id}")

    if not task_id:
        print("   未获取到 task_id")
        return False

    # 轮询任务状态
    print("2. 等待生成完成...")
    for i in range(60):
        time.sleep(3)
        print(f"   轮询 {i+1}/60...")

        status_resp = requests.get(
            f"https://llm-quyeui6kpjhryck7.cn-beijing.maas.aliyuncs.com/api/v1/tasks/{task_id}",
            headers=headers,
            timeout=30
        )

        if status_resp.status_code != 200:
            print(f"   状态查询失败: {status_resp.status_code}")
            continue

        status_data = status_resp.json()
        task_status = status_data.get("output", {}).get("task_status")
        print(f"   任务状态: {task_status}")

        if task_status == "SUCCEEDED":
            results = status_data.get("output", {}).get("results", [])
            if results:
                image_url = results[0].get("url")
                print(f"   图片 URL: {image_url}")

                # 下载图片
                print("3. 下载图片...")
                img_resp = requests.get(image_url, timeout=60)

                if img_resp.status_code == 200:
                    output_path = OUTPUT_DIR / "test_human_farmer_north_idle.png"
                    with open(output_path, 'wb') as f:
                        f.write(img_resp.content)
                    print(f"✓ 成功: {output_path}")
                    return True
                else:
                    print(f"✗ 下载失败: {img_resp.status_code}")
                    return False

        elif task_status == "FAILED":
            print(f"✗ 任务失败: {status_data}")
            return False

    print("✗ 超时")
    return False

if __name__ == "__main__":
    generate_test_image()
