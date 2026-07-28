import type {
  AnimationState,
  RenderEventEnvelope,
} from '../types/rendering';
import {
  isNonEmptyString,
  isValidFacing,
  validateAnimationState,
  validateRenderEventEnvelope,
  validateWorldPoint,
} from './protocol';

const DEFAULT_DEDUPE_CAPACITY = 10_000;
const DEFAULT_DEDUPE_TTL_MS = 30 * 60 * 1000;
const VALID_ANIMATION_STATES = new Set<AnimationState['state']>([
  'idle',
  'walk',
  'work',
  'combat',
  'cast',
  'attack',
  'hurt',
  'downed',
]);

export interface EventSequencerOptions {
  now?: () => number;
  dedupeCapacity?: number;
  dedupeTtlMs?: number;
}

export type EventSequencerResult =
  | {
      action: 'applied';
      revision: number;
      events: readonly RenderEventEnvelope[];
    }
  | {
      action: 'pending';
      revision: number;
      received: number;
      expected: number;
    }
  | { action: 'duplicate'; event_id: string }
  | { action: 'stale'; revision: number; snapshot_revision: number }
  | {
      action: 'resync';
      expected_revision: number;
      received_revision: number;
    }
  | { action: 'contract_error'; reason: string };

interface PendingRevision {
  expectedCount: number;
  eventsByIndex: Map<number, RenderEventEnvelope>;
}

/**
 * Buffers immutable render envelopes until one complete revision can be
 * returned atomically. This class deliberately does not mutate scene state.
 */
export class EventSequencer {
  private readonly pending = new Map<number, PendingRevision>();
  private readonly dedupe = new Map<string, number>();
  private readonly now: () => number;
  private readonly dedupeCapacity: number;
  private readonly dedupeTtlMs: number;
  private snapshotRevision: number;
  private currentAppliedRevision: number;

  constructor(
    private readonly worldId: string,
    private readonly sceneId: string,
    snapshotRevision = -1,
    options: EventSequencerOptions = {},
  ) {
    this.snapshotRevision = snapshotRevision;
    this.currentAppliedRevision = snapshotRevision;
    this.now = options.now ?? (() => Date.now());
    this.dedupeCapacity =
      options.dedupeCapacity ?? DEFAULT_DEDUPE_CAPACITY;
    this.dedupeTtlMs = options.dedupeTtlMs ?? DEFAULT_DEDUPE_TTL_MS;
    if (
      !Number.isInteger(this.dedupeCapacity) ||
      this.dedupeCapacity < 1 ||
      !Number.isFinite(this.dedupeTtlMs) ||
      this.dedupeTtlMs < 0
    ) {
      throw new Error('invalid_dedupe_options');
    }
  }

  get appliedRevision(): number {
    return this.currentAppliedRevision;
  }

  push(event: unknown): EventSequencerResult {
    const validation = validateRenderEventEnvelope(event);
    if (!validation.ok) {
      if (typeof event === 'object' && event !== null) {
        const revision = (event as Record<string, unknown>).revision;
        if (typeof revision === 'number' && Number.isInteger(revision)) {
          this.rollbackPendingRevision(revision);
        }
      }
      return {
        action: 'contract_error',
        reason: validation.issues
          .map(issue => `${issue.pointer}:${issue.reason}`)
          .join(';'),
      };
    }
    const envelope = event as RenderEventEnvelope;
    if (
      envelope.world_id !== this.worldId ||
      envelope.scene_id !== this.sceneId
    ) {
      this.rollbackPendingRevision(envelope.revision);
      return { action: 'contract_error', reason: 'world_scene_mismatch' };
    }
    const payloadError = validateRenderPayload(envelope);
    if (payloadError !== null) {
      this.rollbackPendingRevision(envelope.revision);
      return { action: 'contract_error', reason: payloadError };
    }

    this.evictExpiredDedupeEntries();
    const dedupeKey = this.dedupeKey(envelope);
    if (this.dedupe.has(dedupeKey)) {
      this.touchDedupeEntry(dedupeKey);
      return { action: 'duplicate', event_id: envelope.event_id };
    }
    if (envelope.revision <= this.snapshotRevision) {
      return {
        action: 'stale',
        revision: envelope.revision,
        snapshot_revision: this.snapshotRevision,
      };
    }

    const expectedRevision = this.currentAppliedRevision + 1;
    if (envelope.revision > expectedRevision) {
      return {
        action: 'resync',
        expected_revision: expectedRevision,
        received_revision: envelope.revision,
      };
    }
    if (envelope.revision < expectedRevision) {
      return {
        action: 'stale',
        revision: envelope.revision,
        snapshot_revision: this.snapshotRevision,
      };
    }

    let batch = this.pending.get(envelope.revision);
    if (batch === undefined) {
      batch = {
        expectedCount: envelope.transaction_event_count,
        eventsByIndex: new Map(),
      };
      this.pending.set(envelope.revision, batch);
    }
    if (batch.expectedCount !== envelope.transaction_event_count) {
      this.rollbackPendingRevision(envelope.revision);
      return {
        action: 'contract_error',
        reason: 'transaction_event_count_mismatch',
      };
    }
    const existing = batch.eventsByIndex.get(
      envelope.transaction_event_index,
    );
    if (existing !== undefined) {
      this.rollbackPendingRevision(envelope.revision);
      return {
        action: 'contract_error',
        reason: 'transaction_event_index_conflict',
      };
    }

    batch.eventsByIndex.set(envelope.transaction_event_index, envelope);
    this.remember(envelope);
    if (batch.eventsByIndex.size < batch.expectedCount) {
      return {
        action: 'pending',
        revision: envelope.revision,
        received: batch.eventsByIndex.size,
        expected: batch.expectedCount,
      };
    }

    const events = [...batch.eventsByIndex.values()].sort(compareEvents);
    for (let index = 0; index < batch.expectedCount; index += 1) {
      if (events[index]?.transaction_event_index !== index) {
        this.rollbackPendingRevision(envelope.revision);
        return {
          action: 'contract_error',
          reason: 'transaction_event_index_gap',
        };
      }
    }
    this.pending.delete(envelope.revision);
    this.currentAppliedRevision = envelope.revision;
    return { action: 'applied', revision: envelope.revision, events };
  }

  /** Alias for callers that model the operation as ingestion. */
  ingest(event: unknown): EventSequencerResult {
    return this.push(event);
  }

  onSnapshotApplied(revision: number): void {
    if (!Number.isInteger(revision) || revision < this.snapshotRevision) {
      return;
    }
    this.snapshotRevision = revision;
    this.currentAppliedRevision = revision;
    for (const pendingRevision of this.pending.keys()) {
      if (pendingRevision <= revision) {
        this.pending.delete(pendingRevision);
      }
    }
  }

  private dedupeKey(event: RenderEventEnvelope): string {
    return `${event.world_id}\u0000${event.event_id}`;
  }

  private remember(event: RenderEventEnvelope): void {
    const key = this.dedupeKey(event);
    this.dedupe.set(key, this.now());
    while (this.dedupe.size > this.dedupeCapacity) {
      const oldestKey = this.dedupe.keys().next().value as string | undefined;
      if (oldestKey === undefined) {
        break;
      }
      this.dedupe.delete(oldestKey);
    }
  }

  private touchDedupeEntry(key: string): void {
    const seenAt = this.dedupe.get(key);
    if (seenAt === undefined) {
      return;
    }
    this.dedupe.delete(key);
    this.dedupe.set(key, seenAt);
  }

  private evictExpiredDedupeEntries(): void {
    const expirationThreshold = this.now() - this.dedupeTtlMs;
    for (const [key, seenAt] of this.dedupe) {
      if (seenAt <= expirationThreshold) {
        this.dedupe.delete(key);
      }
    }
  }

  private rollbackPendingRevision(revision: number): void {
    const batch = this.pending.get(revision);
    if (batch === undefined) {
      return;
    }
    for (const pendingEvent of batch.eventsByIndex.values()) {
      this.dedupe.delete(this.dedupeKey(pendingEvent));
    }
    this.pending.delete(revision);
  }
}

export function compareEvents(
  left: RenderEventEnvelope,
  right: RenderEventEnvelope,
): number {
  return (
    left.revision - right.revision ||
    left.transaction_event_index - right.transaction_event_index ||
    compareStableIds(left.event_id, right.event_id)
  );
}

function compareStableIds(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}

function validateRenderPayload(
  envelope: RenderEventEnvelope,
): string | null {
  const payload = envelope.render as unknown as Record<string, unknown>;
  const errors: string[] = [];
  const requireEntityId = (): void => {
    if (!isNonEmptyString(payload.entity_id)) {
      errors.push('/render/entity_id:entity_id_missing');
    }
  };
  const requireWorldPoint = (): void => {
    errors.push(
      ...validateWorldPoint(
        payload.world_point,
        '/render/world_point',
        envelope.scene_id,
      ).map(issue => `${issue.pointer}:${issue.reason}`),
    );
  };
  const requireFacing = (): void => {
    if (!isValidFacing(payload.facing_degrees)) {
      errors.push('/render/facing_degrees:facing_invalid');
    }
  };
  const requireAnimation = (): void => {
    errors.push(
      ...validateAnimationState(
        payload.desired_animation_state,
        '/render/desired_animation_state',
      ).map(issue => `${issue.pointer}:${issue.reason}`),
    );
    const animation = payload.desired_animation_state;
    if (typeof animation === 'object' && animation !== null) {
      const state = (animation as Record<string, unknown>).state;
      if (
        typeof state !== 'string' ||
        !VALID_ANIMATION_STATES.has(state as AnimationState['state'])
      ) {
        errors.push(
          '/render/desired_animation_state/state:state_invalid',
        );
      }
    }
  };

  switch (payload.kind) {
    case 'entity_animation_changed':
      requireEntityId();
      requireWorldPoint();
      requireFacing();
      requireAnimation();
      break;
    case 'entity_moved':
      requireEntityId();
      requireWorldPoint();
      requireFacing();
      break;
    case 'entity_spawned':
      requireEntityId();
      if (!isNonEmptyString(payload.asset_id)) {
        errors.push('/render/asset_id:asset_id_missing');
      }
      requireWorldPoint();
      requireFacing();
      requireAnimation();
      break;
    case 'entity_despawned':
      requireEntityId();
      break;
    default:
      errors.push('/render/kind:render_kind_unsupported');
  }
  return errors.length === 0 ? null : errors.join(';');
}
