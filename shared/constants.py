"""共享类型定义 - 前后端通用

本模块定义前后端共享的核心类型和常量
"""

# 坐标单位：世界单位（wu）
# 1 tile = 32 wu
TILE_SIZE = 32

# 时间单位
# 游戏时间：1 现实秒 = 1 游戏分钟
GAME_MINUTES_PER_REAL_SECOND = 1

# ULID 格式
ULID_PATTERN = r"^[0-9A-HJKMNP-TV-Z]{26}$"

# API 版本
API_VERSION = "v1"
