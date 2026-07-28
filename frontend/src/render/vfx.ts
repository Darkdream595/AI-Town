export type VfxAttachPoint = 'caster_feet' | 'target_center' | 'ground_point';
export type VfxCategory = 'combat' | 'status' | 'environment';

export interface VfxPresentationFlags {
  particles: boolean;
  flash: boolean;
  camera_shake: boolean;
}

export interface VfxSpec {
  vfx_id: string;
  asset_id: string;
  attach_point: VfxAttachPoint;
  duration_ms: number;
  presentation?: Partial<VfxPresentationFlags>;
}

export interface VfxEvent {
  event_id: string;
  vfx_id: string;
  anchor: { scene_id: string; x_wu: number; y_wu: number };
  category: VfxCategory;
}

export interface VfxEffectSemantics {
  particles: boolean;
  flash: boolean;
  camera_shake: boolean;
  static_border: boolean;
  static_icon: boolean;
}

export interface VfxPlayResult {
  status: 'played' | 'duplicate' | 'merged' | 'rejected';
  resolved_vfx_id: string;
  effect: VfxEffectSemantics;
}

interface ActiveVfx {
  poolObjectId: number;
  event: VfxEvent;
  spec: VfxSpec;
  expiresAt: number;
}

const FALLBACK_VFX_ID = 'vfx.fallback.status_ping';
const ACTIVE_CAP = 96;

const DEFAULT_VFX_SPECS: VfxSpec[] = [
  {
    vfx_id: 'vfx.arcane.spark_burst',
    asset_id: 'vfx.arcane.spark_atlas',
    attach_point: 'target_center',
    duration_ms: 420,
    presentation: {
      particles: true,
      flash: true,
      camera_shake: true,
    },
  },
  {
    vfx_id: 'vfx.environment.dust',
    asset_id: 'vfx.environment.dust',
    attach_point: 'ground_point',
    duration_ms: 1000,
    presentation: {
      particles: true,
    },
  },
  {
    vfx_id: 'vfx.environment.mist',
    asset_id: 'vfx.environment.mist',
    attach_point: 'ground_point',
    duration_ms: 1000,
    presentation: {
      particles: true,
    },
  },
  {
    vfx_id: FALLBACK_VFX_ID,
    asset_id: 'vfx.fallback.status_ping',
    attach_point: 'target_center',
    duration_ms: 300,
  },
];

const ATTACH_POINTS = new Set<VfxAttachPoint>([
  'caster_feet',
  'target_center',
  'ground_point',
]);

export function validateVfxSpec(spec: VfxSpec): boolean {
  return (
    spec.vfx_id.length > 0 &&
    spec.asset_id.length > 0 &&
    ATTACH_POINTS.has(spec.attach_point) &&
    Number.isFinite(spec.duration_ms) &&
    spec.duration_ms >= 100 &&
    spec.duration_ms <= 1500
  );
}

function effectSemantics(
  reducedMotion: boolean,
  fallback: boolean,
  presentation: Partial<VfxPresentationFlags> | undefined,
): VfxEffectSemantics {
  if (reducedMotion || fallback) {
    return {
      particles: false,
      flash: false,
      camera_shake: false,
      static_border: true,
      static_icon: true,
    };
  }
  return {
    particles: presentation?.particles === true,
    flash: presentation?.flash === true,
    camera_shake: presentation?.camera_shake === true,
    static_border: false,
    static_icon: false,
  };
}

export class VfxController {
  private readonly specs = new Map<string, VfxSpec>();
  private readonly seenEventIds = new Map<string, true>();
  private readonly active: ActiveVfx[] = [];
  private readonly pool: number[] = [];
  private readonly reducedMotion: boolean;
  private readonly seenEventCapacity: number;
  private nextPoolObjectId = 1;

  constructor(
    options: {
      reducedMotion?: boolean;
      specs?: VfxSpec[];
      seenEventCapacity?: number;
    } = {},
  ) {
    this.reducedMotion = options.reducedMotion === true;
    this.seenEventCapacity = Math.max(1, Math.floor(options.seenEventCapacity ?? 2048));
    for (const spec of options.specs ?? DEFAULT_VFX_SPECS) {
      if (validateVfxSpec(spec)) {
        this.specs.set(spec.vfx_id, spec);
      }
    }
    if (!this.specs.has(FALLBACK_VFX_ID)) {
      const fallback = DEFAULT_VFX_SPECS.find((spec) => spec.vfx_id === FALLBACK_VFX_ID);
      if (fallback) {
        this.specs.set(FALLBACK_VFX_ID, fallback);
      }
    }
  }

  get activeCount(): number {
    return this.active.length;
  }

  get pooledCount(): number {
    return this.pool.length;
  }

  get seenEventCount(): number {
    return this.seenEventIds.size;
  }

  play(event: VfxEvent, nowMs: number): VfxPlayResult {
    const registeredSpec = this.specs.get(event.vfx_id);
    const spec = registeredSpec ?? this.specs.get(FALLBACK_VFX_ID);
    if (!spec) {
      throw new Error('Fallback VFX spec is unavailable');
    }
    const resolvedVfxId = spec.vfx_id;
    const semantics = effectSemantics(
      this.reducedMotion,
      registeredSpec === undefined,
      spec.presentation,
    );

    if (this.seenEventIds.has(event.event_id)) {
      this.seenEventIds.delete(event.event_id);
      this.seenEventIds.set(event.event_id, true);
      return { status: 'duplicate', resolved_vfx_id: resolvedVfxId, effect: semantics };
    }
    this.seenEventIds.set(event.event_id, true);
    while (this.seenEventIds.size > this.seenEventCapacity) {
      const oldestEventId = this.seenEventIds.keys().next().value;
      if (oldestEventId === undefined) {
        break;
      }
      this.seenEventIds.delete(oldestEventId);
    }
    this.sweep(nowMs);

    if (this.active.length >= ACTIVE_CAP) {
      if (event.category === 'environment') {
        const mergeCandidate = this.active.find(
          (active) =>
            active.event.category === 'environment' &&
            active.spec.vfx_id === resolvedVfxId &&
            active.event.anchor.scene_id === event.anchor.scene_id,
        );
        return {
          status: mergeCandidate ? 'merged' : 'rejected',
          resolved_vfx_id: resolvedVfxId,
          effect: semantics,
        };
      }

      const replaceIndex = this.active.findIndex(
        (active) => active.event.category === 'environment',
      );
      if (replaceIndex === -1) {
        return {
          status: 'rejected',
          resolved_vfx_id: resolvedVfxId,
          effect: semantics,
        };
      }
      this.recycleAt(replaceIndex);
    }

    const poolObjectId = this.pool.pop() ?? this.nextPoolObjectId++;
    this.active.push({
      poolObjectId,
      event,
      spec,
      expiresAt: nowMs + spec.duration_ms,
    });
    return { status: 'played', resolved_vfx_id: resolvedVfxId, effect: semantics };
  }

  sweep(nowMs: number): void {
    for (let index = this.active.length - 1; index >= 0; index -= 1) {
      if (this.active[index].expiresAt <= nowMs) {
        this.recycleAt(index);
      }
    }
  }

  dispose(): void {
    while (this.active.length > 0) {
      this.recycleAt(this.active.length - 1);
    }
    this.seenEventIds.clear();
  }

  private recycleAt(index: number): void {
    const [released] = this.active.splice(index, 1);
    this.pool.push(released.poolObjectId);
  }
}
