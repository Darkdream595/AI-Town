import { describe, expect, it, vi } from 'vitest';
import {
  RafFrameSampler,
  createQaRuntimeMetadata,
} from '../runtime';

describe('QA runtime metadata and rAF sampling', () => {
  it('exports auditable scene, revision, camera, fixture and entity count', () => {
    expect(
      createQaRuntimeMetadata({
        fixture_id: 'qa.render.crown_creek_stress_v1',
        entity_count: 12,
        scene_id: 'scene.crown_creek_town',
        revision: 17,
        camera: { x_wu: 512, y_wu: 512, zoom: 1 },
      }),
    ).toEqual(
      expect.objectContaining({
        fixture_id: 'qa.render.crown_creek_stress_v1',
        entity_count: 12,
        scene_id: 'scene.crown_creek_town',
        revision: 17,
        camera: { x_wu: 512, y_wu: 512, zoom: 1 },
      }),
    );
  });

  it('records rAF frame deltas and can be stopped without another callback', () => {
    const callbacks: FrameRequestCallback[] = [];
    const requestFrame = vi.fn((callback: FrameRequestCallback) => {
      callbacks.push(callback);
      return callbacks.length;
    });
    const cancelFrame = vi.fn();
    const sampler = new RafFrameSampler(requestFrame, cancelFrame);

    sampler.start();
    callbacks.shift()?.(100);
    callbacks.shift()?.(116.5);
    callbacks.shift()?.(134);
    sampler.stop();

    expect(sampler.samples()).toEqual([16.5, 17.5]);
    expect(cancelFrame).toHaveBeenCalledOnce();
  });
});
