"""
Foundation 工具函数 - TypeScript

与后端 Python 版本对应的客户端实现
"""

import {
  WorldCoordinate,
  LocalCoordinate,
  RealTime,
  GameTime,
  TILE_SIZE,
  WU_PRECISION,
  REAL_MS_PER_GAME_MINUTE,
  ULID_PATTERN,
} from '../types/foundation';

/**
 * 量化坐标到 1/16 wu 精度
 */
function quantize(value: number): number {
  return Math.round(value / WU_PRECISION) * WU_PRECISION;
}

/**
 * 世界坐标转本地坐标
 */
export function convertWorldToLocal(worldCoord: WorldCoordinate): LocalCoordinate {
  const tile_x = Math.floor(worldCoord.x_wu / TILE_SIZE);
  const tile_y = Math.floor(worldCoord.y_wu / TILE_SIZE);
  const offset_x_wu = quantize(worldCoord.x_wu % TILE_SIZE);
  const offset_y_wu = quantize(worldCoord.y_wu % TILE_SIZE);

  return { tile_x, tile_y, offset_x_wu, offset_y_wu };
}

/**
 * 本地坐标转世界坐标
 */
export function convertLocalToWorld(localCoord: LocalCoordinate): WorldCoordinate {
  const x_wu = quantize(localCoord.tile_x * TILE_SIZE + localCoord.offset_x_wu);
  const y_wu = quantize(localCoord.tile_y * TILE_SIZE + localCoord.offset_y_wu);

  return { x_wu, y_wu };
}

/**
 * 计算两个世界坐标的距离
 */
export function calculateDistance(a: WorldCoordinate, b: WorldCoordinate): number {
  const dx = a.x_wu - b.x_wu;
  const dy = a.y_wu - b.y_wu;
  return Math.sqrt(dx * dx + dy * dy);
}

/**
 * 验证 ULID 格式
 */
export function isValidULID(ulidStr: string): boolean {
  if (typeof ulidStr !== 'string') {
    return false;
  }
  return ULID_PATTERN.test(ulidStr);
}

/**
 * 现实时间转游戏时间
 */
export function realToGameTime(
  realTime: RealTime,
  worldCreationTime: RealTime
): GameTime {
  const elapsedMs = realTime.timestamp_ms - worldCreationTime.timestamp_ms;

  if (elapsedMs < 0) {
    throw new Error('realTime cannot be before worldCreationTime');
  }

  const game_minutes = Math.floor(elapsedMs / REAL_MS_PER_GAME_MINUTE);
  return { game_minutes };
}

/**
 * 游戏时间转现实时间
 */
export function gameToRealTime(
  gameTime: GameTime,
  worldCreationTime: RealTime
): RealTime {
  const elapsedMs = gameTime.game_minutes * REAL_MS_PER_GAME_MINUTE;
  const timestamp_ms = worldCreationTime.timestamp_ms + elapsedMs;

  return { timestamp_ms };
}

/**
 * 格式化游戏时间为可读字符串
 */
export function formatGameTime(gameTime: GameTime): string {
  const days = Math.floor(gameTime.game_minutes / (60 * 24));
  const hours = Math.floor((gameTime.game_minutes % (60 * 24)) / 60);
  const minutes = gameTime.game_minutes % 60;

  return `第 ${days} 天 ${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}`;
}
