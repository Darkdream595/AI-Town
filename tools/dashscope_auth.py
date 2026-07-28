"""DashScope 生成工具的本地凭据入口。"""
from __future__ import annotations

import os


def require_dashscope_api_key() -> str:
    """从进程环境读取凭据，缺失时在网络请求前失败。"""
    api_key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "未设置 DASHSCOPE_API_KEY。请先在本机环境变量中配置 DashScope API Key。"
        )
    return api_key
