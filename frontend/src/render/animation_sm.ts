export type AnimationKind =
  | 'idle'
  | 'walk'
  | 'cast'
  | 'attack'
  | 'hurt'
  | 'downed';

export type AnimationDirection = 'north' | 'east' | 'south' | 'west';

export interface AnimationRequest {
  asset_id: string;
  scene_id: string;
  revision: number;
  kind: AnimationKind;
  direction: AnimationDirection;
  animation_id: string;
}

export interface ResolvedAnimation extends AnimationRequest {
  requested_animation_id: string;
}

export interface MissingAnimationDiagnostic {
  issue: 'ANIMATION_ASSET_MISSING';
  reason: 'requested animation is missing; fallback selected';
  asset_id: string;
  scene_id: string;
  requested_animation_id: string;
  fallback_animation_id: string;
}

export interface AnimationMachineDependencies {
  now: () => number;
  exists: (animationId: string) => boolean;
  onMissingAnimation?: (diagnostic: MissingAnimationDiagnostic) => void;
}

const TRANSIENT_DURATION_MS = 900;

const ANIMATION_PRIORITY: Record<AnimationKind, number> = {
  idle: 0,
  walk: 1,
  cast: 2,
  attack: 2,
  hurt: 3,
  downed: 4,
};

export function priorityOf(kind: AnimationKind): number {
  return ANIMATION_PRIORITY[kind];
}

function isLocomotion(kind: AnimationKind): boolean {
  return kind === 'idle' || kind === 'walk';
}

function isTimed(kind: AnimationKind): boolean {
  return kind === 'attack' || kind === 'cast' || kind === 'hurt';
}

export class AnimationMachine {
  private active: ResolvedAnimation | null = null;
  private activatedAtMs = 0;
  private authoritativeLocomotion: ResolvedAnimation | null = null;
  private readonly latestRevisionByPriority = new Map<number, number>();
  private readonly diagnosedAssetScenes = new Set<string>();

  constructor(private readonly dependencies: AnimationMachineDependencies) {}

  apply(request: AnimationRequest): boolean {
    if (
      isLocomotion(request.kind) &&
      this.authoritativeLocomotion !== null &&
      request.revision <= this.authoritativeLocomotion.revision
    ) {
      return false;
    }

    const priority = priorityOf(request.kind);
    const latestRevision = this.latestRevisionByPriority.get(priority);
    if (latestRevision !== undefined && request.revision <= latestRevision) {
      return false;
    }
    this.latestRevisionByPriority.set(priority, request.revision);

    const resolved = this.resolve(request);
    if (isLocomotion(request.kind)) {
      if (
        this.authoritativeLocomotion === null ||
        request.revision > this.authoritativeLocomotion.revision
      ) {
        this.authoritativeLocomotion = resolved;
      }

      if (
        this.active === null ||
        isLocomotion(this.active.kind) ||
        this.hasTimedOut()
      ) {
        this.activate(resolved);
        return true;
      }
      return false;
    }

    if (
      this.active !== null &&
      !isLocomotion(this.active.kind) &&
      priority < priorityOf(this.active.kind) &&
      !this.hasTimedOut()
    ) {
      return false;
    }

    this.activate(resolved);
    return true;
  }

  tick(): ResolvedAnimation {
    if (this.hasTimedOut() && this.active !== null) {
      const nextLocomotion =
        this.authoritativeLocomotion ?? this.createDirectionalIdle(this.active);
      this.authoritativeLocomotion = nextLocomotion;
      this.activate(nextLocomotion);
    }
    return this.current();
  }

  current(): ResolvedAnimation {
    if (this.active === null) {
      throw new Error('AnimationMachine has no animation state');
    }
    return this.active;
  }

  private activate(animation: ResolvedAnimation): void {
    this.active = animation;
    this.activatedAtMs = this.dependencies.now();
  }

  private hasTimedOut(): boolean {
    return (
      this.active !== null &&
      isTimed(this.active.kind) &&
      this.dependencies.now() - this.activatedAtMs >= TRANSIENT_DURATION_MS
    );
  }

  private createDirectionalIdle(
    transientAnimation: ResolvedAnimation,
  ): ResolvedAnimation {
    const idleAnimationId = transientAnimation.requested_animation_id.replace(
      /\.[^.]+$/,
      `.idle_${transientAnimation.direction}`,
    );
    return this.resolve({
      asset_id: transientAnimation.asset_id,
      scene_id: transientAnimation.scene_id,
      revision: transientAnimation.revision,
      kind: 'idle',
      direction: transientAnimation.direction,
      animation_id: idleAnimationId,
    });
  }

  private resolve(request: AnimationRequest): ResolvedAnimation {
    if (this.dependencies.exists(request.animation_id)) {
      return {
        ...request,
        requested_animation_id: request.animation_id,
      };
    }

    const directionalIdleId = request.animation_id.replace(
      /\.[^.]+$/,
      `.idle_${request.direction}`,
    );
    const fallbackAnimationId = this.dependencies.exists(directionalIdleId)
      ? directionalIdleId
      : 'anim.fallback.idle_south';
    this.diagnoseOnce(request, fallbackAnimationId);

    return {
      ...request,
      animation_id: fallbackAnimationId,
      requested_animation_id: request.animation_id,
    };
  }

  private diagnoseOnce(
    request: AnimationRequest,
    fallbackAnimationId: string,
  ): void {
    const diagnosticKey = `${request.asset_id}\u0000${request.scene_id}`;
    if (this.diagnosedAssetScenes.has(diagnosticKey)) {
      return;
    }
    this.diagnosedAssetScenes.add(diagnosticKey);
    this.dependencies.onMissingAnimation?.({
      issue: 'ANIMATION_ASSET_MISSING',
      reason: 'requested animation is missing; fallback selected',
      asset_id: request.asset_id,
      scene_id: request.scene_id,
      requested_animation_id: request.animation_id,
      fallback_animation_id: fallbackAnimationId,
    });
  }
}
