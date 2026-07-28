import { describe, expect, it } from 'vitest';
import type { SceneLoadRequest } from '../../types/rendering';
import { SceneLifecycle } from '../scene_lifecycle';

function makeRequest(
  sceneId: string,
  revision: number,
): SceneLoadRequest {
  return {
    scene_id: sceneId,
    revision,
    entry_world_point: { scene_id: sceneId, x_wu: 32, y_wu: 64 },
    required_asset_ids: [`map.${sceneId}`],
  };
}

describe('TEST-RENDER-002 SceneLifecycle', () => {
  it('rejects incomplete requests and preserves the confirmed scene', () => {
    const lifecycle = new SceneLifecycle({ now: () => 0 });
    lifecycle.setInitialScene('scene.home', { name: 'home' });

    const result = lifecycle.requestLoad({
      scene_id: 'scene.market',
      revision: 2,
    });

    expect(result.action).toBe('contract_error');
    expect(lifecycle.confirmedSceneId).toBe('scene.home');
    expect(lifecycle.currentJob).toBeNull();
  });

  it('keeps one job and lets a higher revision cancel the older job', () => {
    const lifecycle = new SceneLifecycle({ now: () => 0 });

    expect(lifecycle.requestLoad(makeRequest('scene.a', 4)).action).toBe(
      'started',
    );
    const result = lifecycle.requestLoad(makeRequest('scene.b', 5));

    expect(result).toMatchObject({
      action: 'started',
      cancelled: { sceneId: 'scene.a', revision: 4 },
    });
    expect(lifecycle.currentJob).toMatchObject({
      sceneId: 'scene.b',
      revision: 5,
    });
    expect(lifecycle.requestLoad(makeRequest('scene.c', 3)).action).toBe(
      'stale',
    );
  });

  it('rejects requests below the highest confirmed revision', () => {
    const lifecycle = new SceneLifecycle({ now: () => 0 });
    lifecycle.setInitialScene('scene.home', { name: 'home' });
    lifecycle.requestLoad(makeRequest('scene.market', 5));
    lifecycle.confirmLoaded('scene.market', 5, { name: 'market' });

    const result = lifecycle.requestLoad(makeRequest('scene.home', 4));

    expect(result).toEqual({ action: 'stale', currentRevision: 5 });
    expect(lifecycle.confirmedSceneId).toBe('scene.market');
    expect(lifecycle.currentJob).toBeNull();
  });

  it('rolls back after three failures and requests a full snapshot', () => {
    const snapshotRequests: string[] = [];
    const lifecycle = new SceneLifecycle({
      now: () => 0,
      requestSnapshot: sceneId => snapshotRequests.push(sceneId),
    });
    lifecycle.setInitialScene('scene.home', { name: 'home' });
    lifecycle.requestLoad(makeRequest('scene.market', 2));

    expect(lifecycle.recordFailure('scene.market', 2).action).toBe('retry');
    expect(lifecycle.recordFailure('scene.market', 2).action).toBe('retry');
    expect(lifecycle.recordFailure('scene.market', 2)).toEqual({
      action: 'rolled_back',
      sceneId: 'scene.home',
      requestSnapshot: true,
    });
    expect(lifecycle.confirmedSceneId).toBe('scene.home');
    expect(lifecycle.currentJob).toBeNull();
    expect(snapshotRequests).toEqual(['scene.home']);
  });

  it('keeps the old scene warm for 5000ms then disposes it', () => {
    let now = 100;
    const disposed: string[] = [];
    const lifecycle = new SceneLifecycle({
      now: () => now,
      disposeScene: scene => disposed.push(scene.sceneId),
    });
    lifecycle.setInitialScene('scene.home', { name: 'home' });
    lifecycle.requestLoad(makeRequest('scene.market', 2));
    lifecycle.confirmLoaded('scene.market', 2, { name: 'market' });

    expect(lifecycle.warmSceneIds).toEqual(['scene.home']);
    now = 5099;
    lifecycle.tick();
    expect(disposed).toEqual([]);
    now = 5100;
    lifecycle.tick();
    expect(disposed).toEqual(['scene.home']);
  });

  it('reuses a same-id warm scene inside the rollback window', () => {
    let now = 0;
    const disposed: string[] = [];
    const lifecycle = new SceneLifecycle({
      now: () => now,
      disposeScene: scene => disposed.push(scene.sceneId),
    });
    lifecycle.setInitialScene('scene.home', { name: 'home' });
    lifecycle.requestLoad(makeRequest('scene.market', 2));
    lifecycle.confirmLoaded('scene.market', 2, { name: 'market' });

    now = 1000;
    const result = lifecycle.requestLoad(makeRequest('scene.home', 3));

    expect(result).toMatchObject({ action: 'reused', sceneId: 'scene.home' });
    expect(lifecycle.confirmedSceneId).toBe('scene.home');
    expect(disposed).toEqual([]);
  });
});
