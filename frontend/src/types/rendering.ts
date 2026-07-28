/**
 * 渲染系统类型定义
 *
 * 符合 DOC-RENDER-001 规范
 */

// ==================== Protocol Types ====================

/**
 * WorldPoint - 带 scene_id 的世界坐标
 *
 * RULE-RENDER-003: entity、camera、VFX target 均使用完整 WorldPoint
 */
export interface WorldPoint {
  scene_id: string;
  x_wu: number;
  y_wu: number;
}

/**
 * 动画状态
 */
export type RenderAnimationState =
  | 'idle'
  | 'walk'
  | 'work'
  | 'combat'
  | 'cast'
  | 'attack'
  | 'hurt'
  | 'downed';

export interface AnimationState {
  animation_id: string;
  state: RenderAnimationState;
  loop: boolean;
  since_revision: number;
}

/**
 * 实体投影（用于渲染）
 */
export interface EntityProjection {
  entity_id: string;
  asset_id: string;
  world_point: WorldPoint;
  facing_degrees: 0 | 90 | 180 | 270;
  desired_animation_state: AnimationState;
}

/**
 * 渲染帧输入（完整 Snapshot）
 *
 * RULE-RENDER-002: 每个 WorldScene 只消费 protocol/world/scene 匹配且 Revision 连续的 Snapshot/Event
 */
export interface RenderFrameInput {
  protocol_version: string;
  snapshot_id: string;
  snapshot_content_sha256: string;
  world_id: string;
  scene_id: string;
  revision: number;
  game_time: number;
  camera_target: WorldPoint;
  entities: EntityProjection[];
}

/**
 * 渲染事件封装（增量更新）
 */
export interface RenderEventEnvelope {
  protocol_version: string;
  event_id: string;
  world_id: string;
  scene_id: string;
  revision: number;
  game_time: number;
  causation_id: string;
  correlation_id: string;
  transaction_event_index: number;
  transaction_event_count: number;
  render: RenderEventPayload;
}

/**
 * 渲染事件 Payload
 */
export type RenderEventPayload =
  | EntityAnimationChangedEvent
  | EntityMovedEvent
  | EntitySpawnedEvent
  | EntityDespawnedEvent;

export interface EntityAnimationChangedEvent {
  kind: 'entity_animation_changed';
  entity_id: string;
  world_point: WorldPoint;
  facing_degrees: 0 | 90 | 180 | 270;
  desired_animation_state: AnimationState;
}

export interface EntityMovedEvent {
  kind: 'entity_moved';
  entity_id: string;
  world_point: WorldPoint;
  facing_degrees: 0 | 90 | 180 | 270;
}

export interface EntitySpawnedEvent {
  kind: 'entity_spawned';
  entity_id: string;
  asset_id: string;
  world_point: WorldPoint;
  facing_degrees: 0 | 90 | 180 | 270;
  desired_animation_state: AnimationState;
}

export interface EntityDespawnedEvent {
  kind: 'entity_despawned';
  entity_id: string;
}

// ==================== Scene Types ====================

/**
 * Scene 加载请求
 *
 * DOC-RENDER-002: Load Gate
 */
export interface SceneLoadRequest {
  scene_id: string;
  revision: number;
  entry_world_point: WorldPoint;
  required_asset_ids: string[];
}

/**
 * Scene 状态
 */
export type SceneState = 'loading' | 'active' | 'warm' | 'disposed';

// ==================== Asset Types ====================

/**
 * Sprite 规格
 *
 * DOC-RENDER-004: 角色 Sprite 规格
 */
export interface SpriteSpec {
  asset_id: string;
  portrait_asset_id: string;
  frame_size_px: {
    width: number;
    height: number;
  };
  walk_frames_per_direction: number;
  directions: ['north', 'east', 'south', 'west'];
}

/**
 * 地图切片规格
 *
 * DOC-RENDER-003: 五层地图合成
 */
export interface MapSliceSpec {
  scene_id: string;
  asset_id: string;
  render: {
    layer: 'ground' | 'structure_bg' | 'structure_fg';
    lod: 0 | 1;
    origin_x_wu: number;
    origin_y_wu: number;
    width_wu: number;
    height_wu: number;
    pixel_width: number;
    pixel_height: number;
    depth_bias: number;
  };
}

// ==================== Constants ====================

/**
 * RULE-RENDER-010: 四方向
 */
export type Direction = 'north' | 'east' | 'south' | 'west';

/**
 * RULE-RENDER-007: 合成固定顺序
 */
export const RENDER_LAYERS = {
  GROUND_ART: 0,
  STRUCTURE_BG: 1000,
  ENTITIES: 2000,
  STRUCTURE_FG: 3000,
  UI: 4000,
} as const;

/**
 * RULE-RENDER-008: 动态实体 depth 计算
 * depth = floor(y_wu * 16) + depth_bias
 */
export function calculateEntityDepth(worldPoint: WorldPoint, depth_bias: number = 0): number {
  return Math.floor(worldPoint.y_wu * 16) + depth_bias;
}

/**
 * Facing degrees 转 Direction
 */
export function facingToDirection(facing_degrees: 0 | 90 | 180 | 270): Direction {
  switch (facing_degrees) {
    case 0:
      return 'east';
    case 90:
      return 'south';
    case 180:
      return 'west';
    case 270:
      return 'north';
  }
}

/**
 * Direction 转 Facing degrees
 */
export function directionToFacing(direction: Direction): 0 | 90 | 180 | 270 {
  switch (direction) {
    case 'east':
      return 0;
    case 'south':
      return 90;
    case 'west':
      return 180;
    case 'north':
      return 270;
  }
}
