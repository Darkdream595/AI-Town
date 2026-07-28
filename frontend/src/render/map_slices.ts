const LOD0_EXTENT_WU = 1_024;
const LOD1_EXTENT_WU = 2_048;
const MAX_RESIDENT_CELLS = 20;
const MAX_GPU_BYTES = 160 * 1024 * 1024;
const DEFAULT_BYTES_PER_CELL = 2 * 1_024 * 1_024 * 4;
const WU_EPSILON = 1 / 16;

export interface WorldBounds {
  left_wu: number;
  top_wu: number;
  right_wu: number;
  bottom_wu: number;
}

export interface SliceRange {
  min_x: number;
  max_x: number;
  min_y: number;
  max_y: number;
}

export interface MapSlicePlanInput {
  viewport_width_px: number;
  viewport_height_px: number;
  camera_zoom: number;
  camera_center_x_wu: number;
  camera_center_y_wu: number;
  scene_bounds: WorldBounds;
  bytes_per_cell?: number;
}

export interface MapSlicePlan {
  ok: true;
  lod: 0 | 1;
  slice_extent_wu: number;
  visible_world_bounds: WorldBounds;
  visible_range: SliceRange;
  preload_range: SliceRange;
  cell_count: number;
  estimated_gpu_bytes: number;
}

export type MapSlicePlanResult =
  | MapSlicePlan
  | {
      ok: false;
      reason:
        | 'invalid_input'
        | 'viewport_outside_scene'
        | 'lod1_budget_exceeded';
      lod?: 1;
      cell_count?: number;
      estimated_gpu_bytes?: number;
    };

export interface DepthSortable {
  entity_id: string;
  y_wu: number;
  depth_bias?: number;
}

export function planMapSlices(
  input: MapSlicePlanInput,
): MapSlicePlanResult {
  if (!isValidInput(input)) {
    return { ok: false, reason: 'invalid_input' };
  }
  const visibleWorldBounds = calculateVisibleWorldBounds(input);
  if (
    visibleWorldBounds.left_wu >= visibleWorldBounds.right_wu ||
    visibleWorldBounds.top_wu >= visibleWorldBounds.bottom_wu
  ) {
    return { ok: false, reason: 'viewport_outside_scene' };
  }
  const bytesPerCell = input.bytes_per_cell ?? DEFAULT_BYTES_PER_CELL;
  const lod0 = planAtLod(
    0,
    LOD0_EXTENT_WU,
    visibleWorldBounds,
    input.scene_bounds,
    bytesPerCell,
  );
  if (withinBudget(lod0)) {
    return lod0;
  }
  const lod1 = planAtLod(
    1,
    LOD1_EXTENT_WU,
    visibleWorldBounds,
    input.scene_bounds,
    bytesPerCell,
  );
  if (withinBudget(lod1)) {
    return lod1;
  }
  return {
    ok: false,
    reason: 'lod1_budget_exceeded',
    lod: 1,
    cell_count: lod1.cell_count,
    estimated_gpu_bytes: lod1.estimated_gpu_bytes,
  };
}

export function calculateVisibleWorldBounds(
  input: Pick<
    MapSlicePlanInput,
    | 'viewport_width_px'
    | 'viewport_height_px'
    | 'camera_zoom'
    | 'camera_center_x_wu'
    | 'camera_center_y_wu'
    | 'scene_bounds'
  >,
): WorldBounds {
  const halfWidthWu = input.viewport_width_px / input.camera_zoom / 2;
  const halfHeightWu = input.viewport_height_px / input.camera_zoom / 2;
  return {
    left_wu: Math.max(
      input.scene_bounds.left_wu,
      input.camera_center_x_wu - halfWidthWu,
    ),
    top_wu: Math.max(
      input.scene_bounds.top_wu,
      input.camera_center_y_wu - halfHeightWu,
    ),
    right_wu: Math.min(
      input.scene_bounds.right_wu,
      input.camera_center_x_wu + halfWidthWu,
    ),
    bottom_wu: Math.min(
      input.scene_bounds.bottom_wu,
      input.camera_center_y_wu + halfHeightWu,
    ),
  };
}

export function entityDepth(entity: DepthSortable): number {
  return Math.floor(entity.y_wu * 16) + (entity.depth_bias ?? 0);
}

export function compareDeterministicDepth(
  left: DepthSortable,
  right: DepthSortable,
): number {
  return (
    entityDepth(left) - entityDepth(right) ||
    compareStableIds(left.entity_id, right.entity_id)
  );
}

function planAtLod(
  lod: 0 | 1,
  extent: number,
  visibleWorldBounds: WorldBounds,
  sceneBounds: WorldBounds,
  bytesPerCell: number,
): MapSlicePlan {
  const sceneMinX = Math.max(
    0,
    Math.floor(sceneBounds.left_wu / extent),
  );
  const sceneMinY = Math.max(
    0,
    Math.floor(sceneBounds.top_wu / extent),
  );
  const sceneMaxX = Math.max(
    sceneMinX,
    Math.floor((sceneBounds.right_wu - WU_EPSILON) / extent),
  );
  const sceneMaxY = Math.max(
    sceneMinY,
    Math.floor((sceneBounds.bottom_wu - WU_EPSILON) / extent),
  );
  const visibleRange: SliceRange = {
    min_x: clampIndex(
      Math.floor(visibleWorldBounds.left_wu / extent),
      sceneMinX,
      sceneMaxX,
    ),
    max_x: clampIndex(
      Math.floor((visibleWorldBounds.right_wu - WU_EPSILON) / extent),
      sceneMinX,
      sceneMaxX,
    ),
    min_y: clampIndex(
      Math.floor(visibleWorldBounds.top_wu / extent),
      sceneMinY,
      sceneMaxY,
    ),
    max_y: clampIndex(
      Math.floor((visibleWorldBounds.bottom_wu - WU_EPSILON) / extent),
      sceneMinY,
      sceneMaxY,
    ),
  };
  const preloadRange: SliceRange = {
    min_x: Math.max(sceneMinX, visibleRange.min_x - 1),
    max_x: Math.min(sceneMaxX, visibleRange.max_x + 1),
    min_y: Math.max(sceneMinY, visibleRange.min_y - 1),
    max_y: Math.min(sceneMaxY, visibleRange.max_y + 1),
  };
  const cellCount =
    (preloadRange.max_x - preloadRange.min_x + 1) *
    (preloadRange.max_y - preloadRange.min_y + 1);
  return {
    ok: true,
    lod,
    slice_extent_wu: extent,
    visible_world_bounds: visibleWorldBounds,
    visible_range: visibleRange,
    preload_range: preloadRange,
    cell_count: cellCount,
    estimated_gpu_bytes: cellCount * bytesPerCell,
  };
}

function withinBudget(plan: MapSlicePlan): boolean {
  return (
    plan.cell_count <= MAX_RESIDENT_CELLS &&
    plan.estimated_gpu_bytes <= MAX_GPU_BYTES
  );
}

function clampIndex(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function compareStableIds(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}

function isValidInput(input: MapSlicePlanInput): boolean {
  const numbers = [
    input.viewport_width_px,
    input.viewport_height_px,
    input.camera_zoom,
    input.camera_center_x_wu,
    input.camera_center_y_wu,
    input.scene_bounds.left_wu,
    input.scene_bounds.top_wu,
    input.scene_bounds.right_wu,
    input.scene_bounds.bottom_wu,
    input.bytes_per_cell ?? DEFAULT_BYTES_PER_CELL,
  ];
  return (
    numbers.every(value => Number.isFinite(value)) &&
    input.viewport_width_px > 0 &&
    input.viewport_width_px <= 3_840 &&
    input.viewport_height_px > 0 &&
    input.viewport_height_px <= 2_160 &&
    input.camera_zoom >= 0.75 &&
    input.camera_zoom <= 2 &&
    input.scene_bounds.left_wu < input.scene_bounds.right_wu &&
    input.scene_bounds.top_wu < input.scene_bounds.bottom_wu &&
    (input.bytes_per_cell ?? DEFAULT_BYTES_PER_CELL) > 0
  );
}
