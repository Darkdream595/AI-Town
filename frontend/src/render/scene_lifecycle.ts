import type { SceneLoadRequest } from '../types/rendering';

const WARM_SCENE_TTL_MS = 5_000;
const MAX_FAILURES = 3;

export interface SceneResource<T = unknown> {
  sceneId: string;
  resource: T;
}

export interface SceneLoadJob {
  sceneId: string;
  revision: number;
  request: SceneLoadRequest;
  failures: number;
}

export interface SceneLifecycleOptions<T = unknown> {
  now?: () => number;
  disposeScene?: (scene: SceneResource<T>) => void;
  requestSnapshot?: (sceneId: string) => void;
}

export type SceneLoadDecision =
  | {
      action: 'started';
      job: SceneLoadJob;
      cancelled?: { sceneId: string; revision: number };
    }
  | { action: 'reused'; sceneId: string; revision: number }
  | { action: 'stale'; currentRevision: number }
  | { action: 'contract_error'; reason: string };

export type SceneFailureDecision =
  | { action: 'retry'; attempt: number; remaining: number }
  | {
      action: 'rolled_back';
      sceneId: string | null;
      requestSnapshot: true;
    }
  | { action: 'stale' };

interface WarmScene<T> {
  scene: SceneResource<T>;
  disposeAt: number;
}

/**
 * Pure scene transition state machine. Phaser creation and disposal are
 * injected by the caller so job cancellation is independently testable.
 */
export class SceneLifecycle<T = unknown> {
  private readonly now: () => number;
  private readonly disposeScene: (scene: SceneResource<T>) => void;
  private readonly requestSnapshot: (sceneId: string) => void;
  private confirmed: SceneResource<T> | null = null;
  private highestConfirmedRevision = -1;
  private activeJob: SceneLoadJob | null = null;
  private readonly warmScenes = new Map<string, WarmScene<T>>();

  constructor(options: SceneLifecycleOptions<T> = {}) {
    this.now = options.now ?? (() => Date.now());
    this.disposeScene = options.disposeScene ?? (() => undefined);
    this.requestSnapshot = options.requestSnapshot ?? (() => undefined);
  }

  get confirmedSceneId(): string | null {
    return this.confirmed?.sceneId ?? null;
  }

  get currentJob(): Readonly<SceneLoadJob> | null {
    return this.activeJob;
  }

  get warmSceneIds(): string[] {
    return [...this.warmScenes.keys()].sort();
  }

  setInitialScene(sceneId: string, resource: T, revision = -1): void {
    if (sceneId.length === 0) {
      throw new Error('scene_id_missing');
    }
    this.confirmed = { sceneId, resource };
    this.highestConfirmedRevision = Math.max(
      this.highestConfirmedRevision,
      revision,
    );
  }

  requestLoad(request: unknown): SceneLoadDecision {
    const reason = validateSceneLoadRequest(request);
    if (reason !== null) {
      return { action: 'contract_error', reason };
    }
    const validRequest = request as SceneLoadRequest;
    this.tick();

    if (validRequest.revision < this.highestConfirmedRevision) {
      return {
        action: 'stale',
        currentRevision: this.highestConfirmedRevision,
      };
    }
    if (
      this.activeJob !== null &&
      validRequest.revision <= this.activeJob.revision
    ) {
      return { action: 'stale', currentRevision: this.activeJob.revision };
    }

    const warm = this.warmScenes.get(validRequest.scene_id);
    if (warm !== undefined && warm.disposeAt > this.now()) {
      const cancelled = this.activeJob;
      this.activeJob = null;
      this.warmScenes.delete(validRequest.scene_id);
      this.moveConfirmedToWarm(validRequest.scene_id);
      this.confirmed = warm.scene;
      return {
        action: 'reused',
        sceneId: validRequest.scene_id,
        revision: validRequest.revision,
        ...(cancelled === null
          ? {}
          : {
              cancelled: {
                sceneId: cancelled.sceneId,
                revision: cancelled.revision,
              },
            }),
      };
    }

    const cancelled = this.activeJob;
    const job: SceneLoadJob = {
      sceneId: validRequest.scene_id,
      revision: validRequest.revision,
      request: validRequest,
      failures: 0,
    };
    this.activeJob = job;
    return {
      action: 'started',
      job,
      ...(cancelled === null
        ? {}
        : {
            cancelled: {
              sceneId: cancelled.sceneId,
              revision: cancelled.revision,
            },
          }),
    };
  }

  confirmLoaded(sceneId: string, revision: number, resource: T): boolean {
    if (
      this.activeJob === null ||
      this.activeJob.sceneId !== sceneId ||
      this.activeJob.revision !== revision
    ) {
      return false;
    }
    this.moveConfirmedToWarm(sceneId);
    this.confirmed = { sceneId, resource };
    this.highestConfirmedRevision = Math.max(
      this.highestConfirmedRevision,
      revision,
    );
    this.activeJob = null;
    return true;
  }

  recordFailure(sceneId: string, revision: number): SceneFailureDecision {
    if (
      this.activeJob === null ||
      this.activeJob.sceneId !== sceneId ||
      this.activeJob.revision !== revision
    ) {
      return { action: 'stale' };
    }
    this.activeJob.failures += 1;
    if (this.activeJob.failures < MAX_FAILURES) {
      return {
        action: 'retry',
        attempt: this.activeJob.failures,
        remaining: MAX_FAILURES - this.activeJob.failures,
      };
    }

    this.activeJob = null;
    const sceneIdForSnapshot = this.confirmed?.sceneId ?? null;
    if (sceneIdForSnapshot !== null) {
      this.requestSnapshot(sceneIdForSnapshot);
    }
    return {
      action: 'rolled_back',
      sceneId: sceneIdForSnapshot,
      requestSnapshot: true,
    };
  }

  tick(): void {
    const now = this.now();
    for (const [sceneId, warm] of this.warmScenes) {
      if (warm.disposeAt <= now) {
        this.warmScenes.delete(sceneId);
        this.disposeScene(warm.scene);
      }
    }
  }

  private moveConfirmedToWarm(replacingSceneId: string): void {
    if (
      this.confirmed === null ||
      this.confirmed.sceneId === replacingSceneId
    ) {
      return;
    }
    this.warmScenes.set(this.confirmed.sceneId, {
      scene: this.confirmed,
      disposeAt: this.now() + WARM_SCENE_TTL_MS,
    });
  }
}

export function validateSceneLoadRequest(value: unknown): string | null {
  if (typeof value !== 'object' || value === null) {
    return 'request_not_object';
  }
  const request = value as Record<string, unknown>;
  if (typeof request.scene_id !== 'string' || request.scene_id.length === 0) {
    return 'scene_id_missing';
  }
  if (
    typeof request.revision !== 'number' ||
    !Number.isInteger(request.revision) ||
    request.revision < 0
  ) {
    return 'revision_invalid';
  }
  const entry = request.entry_world_point;
  if (typeof entry !== 'object' || entry === null) {
    return 'entry_world_point_missing';
  }
  const point = entry as Record<string, unknown>;
  if (point.scene_id !== request.scene_id) {
    return 'entry_scene_id_mismatch';
  }
  if (
    typeof point.x_wu !== 'number' ||
    !Number.isFinite(point.x_wu) ||
    typeof point.y_wu !== 'number' ||
    !Number.isFinite(point.y_wu)
  ) {
    return 'entry_coordinates_invalid';
  }
  if (
    !Array.isArray(request.required_asset_ids) ||
    request.required_asset_ids.some(
      assetId => typeof assetId !== 'string' || assetId.length === 0,
    )
  ) {
    return 'required_asset_ids_invalid';
  }
  return null;
}
