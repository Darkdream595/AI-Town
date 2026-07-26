"""
共享类型定义 - TypeScript

与后端 Python 版本对应
"""

// RULE-FOUNDATION-040: 坐标单位常量
export const TILE_SIZE = 32; // 1 tile = 32 wu
export const WU_PRECISION = 1 / 16; // 精度为 1/16 wu

// RULE-FOUNDATION-048: 时间转换率
export const GAME_MINUTES_PER_REAL_SECOND = 1;
export const REAL_MS_PER_GAME_MINUTE = 1000;

// RULE-FOUNDATION-033: ULID 格式
export const ULID_PATTERN = /^[0-9A-HJKMNP-TV-Z]{26}$/;

/**
 * 世界坐标（World Units）
 */
export interface WorldCoordinate {
  x_wu: number;
  y_wu: number;
}

/**
 * 本地坐标（Tile + 偏移）
 */
export interface LocalCoordinate {
  tile_x: number;
  tile_y: number;
  offset_x_wu: number;
  offset_y_wu: number;
}

/**
 * 现实时间
 */
export interface RealTime {
  timestamp_ms: number;
}

/**
 * 游戏时间
 */
export interface GameTime {
  game_minutes: number;
}

/**
 * 领域事件基础接口
 */
export interface DomainEvent {
  event_id: string;
  event_type: string;
  occurred_at: string; // ISO 8601 UTC
  world_id: string;
  revision: number;
  caused_by_command_id?: string;
}
