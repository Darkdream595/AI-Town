import { describe, expect, it } from 'vitest';
import {
  compareDeterministicDepth,
  planMapSlices,
} from '../map_slices';

const LARGE_SCENE = {
  left_wu: 0,
  top_wu: 0,
  right_wu: 16384,
  bottom_wu: 16384,
};

describe('TEST-RENDER-003 map slice planning', () => {
  it('computes visible bounds and a one-cell preload ring', () => {
    const result = planMapSlices({
      viewport_width_px: 1920,
      viewport_height_px: 1080,
      camera_zoom: 2,
      camera_center_x_wu: 2048,
      camera_center_y_wu: 2048,
      scene_bounds: LARGE_SCENE,
    });

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.lod).toBe(0);
      expect(result.visible_world_bounds).toEqual({
        left_wu: 1568,
        top_wu: 1778,
        right_wu: 2528,
        bottom_wu: 2318,
      });
      expect(result.visible_range).toEqual({
        min_x: 1,
        max_x: 2,
        min_y: 1,
        max_y: 2,
      });
      expect(result.preload_range).toEqual({
        min_x: 0,
        max_x: 3,
        min_y: 0,
        max_y: 3,
      });
    }
  });

  it('clamps negative indices and the preload ring at scene edges', () => {
    const result = planMapSlices({
      viewport_width_px: 1280,
      viewport_height_px: 720,
      camera_zoom: 2,
      camera_center_x_wu: 0,
      camera_center_y_wu: 0,
      scene_bounds: {
        left_wu: 0,
        top_wu: 0,
        right_wu: 2048,
        bottom_wu: 2048,
      },
    });

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.visible_range.min_x).toBe(0);
      expect(result.visible_range.min_y).toBe(0);
      expect(result.preload_range).toEqual({
        min_x: 0,
        max_x: 1,
        min_y: 0,
        max_y: 1,
      });
    }
  });

  it('clamps preload minima to a non-zero scene origin cell', () => {
    const result = planMapSlices({
      viewport_width_px: 1280,
      viewport_height_px: 720,
      camera_zoom: 2,
      camera_center_x_wu: 2048,
      camera_center_y_wu: 3072,
      scene_bounds: {
        left_wu: 2048,
        top_wu: 3072,
        right_wu: 6144,
        bottom_wu: 7168,
      },
    });

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.visible_range.min_x).toBe(2);
      expect(result.visible_range.min_y).toBe(3);
      expect(result.preload_range.min_x).toBe(2);
      expect(result.preload_range.min_y).toBe(3);
    }
  });

  it('switches 4K at zoom 0.75 to LOD1 when LOD0 exceeds budget', () => {
    const result = planMapSlices({
      viewport_width_px: 3840,
      viewport_height_px: 2160,
      camera_zoom: 0.75,
      camera_center_x_wu: 4096,
      camera_center_y_wu: 4096,
      scene_bounds: LARGE_SCENE,
    });

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.lod).toBe(1);
      expect(result.cell_count).toBeLessThanOrEqual(20);
      expect(result.estimated_gpu_bytes).toBeLessThanOrEqual(
        160 * 1024 * 1024,
      );
    }
  });

  it('keeps 4K at zoom 2.0 within the LOD0 limits', () => {
    const result = planMapSlices({
      viewport_width_px: 3840,
      viewport_height_px: 2160,
      camera_zoom: 2,
      camera_center_x_wu: 4096,
      camera_center_y_wu: 4096,
      scene_bounds: LARGE_SCENE,
    });

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.lod).toBe(0);
      expect(result.cell_count).toBeLessThanOrEqual(20);
    }
  });

  it('returns failure when LOD1 still exceeds cell or GPU budget', () => {
    const result = planMapSlices({
      viewport_width_px: 3840,
      viewport_height_px: 2160,
      camera_zoom: 0.75,
      camera_center_x_wu: 4096,
      camera_center_y_wu: 4096,
      scene_bounds: LARGE_SCENE,
      bytes_per_cell: 16 * 1024 * 1024,
    });

    expect(result).toEqual({
      ok: false,
      reason: 'lod1_budget_exceeded',
      lod: 1,
      cell_count: 20,
      estimated_gpu_bytes: 320 * 1024 * 1024,
    });
  });

  it('sorts equal depths by stable entity id', () => {
    const entities = [
      { entity_id: 'entity.z', y_wu: 10, depth_bias: 0 },
      { entity_id: 'entity.a', y_wu: 10, depth_bias: 0 },
      { entity_id: 'entity.low', y_wu: 9, depth_bias: 0 },
    ];

    expect(entities.sort(compareDeterministicDepth).map(item => item.entity_id))
      .toEqual(['entity.low', 'entity.a', 'entity.z']);
  });
});
