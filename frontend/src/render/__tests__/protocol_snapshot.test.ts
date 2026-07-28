import { describe, expect, it } from 'vitest';
import type {
  EntityProjection,
  RenderFrameInput,
  RenderEventEnvelope,
} from '../../types/rendering';
import {
  validateRenderEventEnvelope,
  validateRenderFrameInput,
} from '../protocol';
import { SnapshotGate } from '../snapshot_gate';

const WORLD_ID = 'world.test';
const SCENE_ID = 'scene.town';
const CONTENT_HASH_A = 'a'.repeat(64);
const CONTENT_HASH_B = 'b'.repeat(64);

function makeEntity(
  overrides: Partial<EntityProjection> = {},
): EntityProjection {
  return {
    entity_id: 'entity.resident.alice',
    asset_id: 'sprite.resident.apothecary',
    world_point: { scene_id: SCENE_ID, x_wu: 32, y_wu: 48 },
    facing_degrees: 90,
    desired_animation_state: {
      animation_id: 'anim.resident.walk_south',
      state: 'walk',
      loop: true,
      since_revision: 1,
    },
    ...overrides,
  };
}

function makeFrame(
  overrides: Partial<RenderFrameInput> = {},
): RenderFrameInput {
  return {
    protocol_version: 'render.v1',
    snapshot_id: 'snapshot.a',
    snapshot_content_sha256: CONTENT_HASH_A,
    world_id: WORLD_ID,
    scene_id: SCENE_ID,
    revision: 1,
    game_time: 420,
    camera_target: { scene_id: SCENE_ID, x_wu: 32, y_wu: 48 },
    entities: [makeEntity()],
    ...overrides,
  };
}

function makeEvent(
  overrides: Partial<RenderEventEnvelope> = {},
): RenderEventEnvelope {
  return {
    protocol_version: 'render.v1',
    event_id: 'event.a',
    world_id: WORLD_ID,
    scene_id: SCENE_ID,
    revision: 2,
    game_time: 421,
    causation_id: 'command.a',
    correlation_id: 'correlation.a',
    transaction_event_index: 0,
    transaction_event_count: 1,
    render: {
      kind: 'entity_moved',
      entity_id: 'entity.resident.alice',
      world_point: { scene_id: SCENE_ID, x_wu: 33, y_wu: 48 },
      facing_degrees: 90,
    },
    ...overrides,
  };
}

describe('TEST-RENDER-001 protocol validation', () => {
  it('rejects non-finite coordinates', () => {
    const frame = makeFrame({
      camera_target: {
        scene_id: SCENE_ID,
        x_wu: Number.NaN,
        y_wu: 0,
      },
    });

    const validation = validateRenderFrameInput(frame);

    expect(validation.ok).toBe(false);
    expect(validation.issues).toContainEqual({
      pointer: '/camera_target/x_wu',
      reason: 'x_wu_not_finite',
    });
  });

  it('rejects camera and entity WorldPoints from another scene', () => {
    const frame = makeFrame({
      camera_target: { scene_id: 'scene.other', x_wu: 0, y_wu: 0 },
      entities: [
        makeEntity({
          world_point: { scene_id: 'scene.other', x_wu: 0, y_wu: 0 },
        }),
      ],
    });

    const validation = validateRenderFrameInput(frame);

    expect(validation.ok).toBe(false);
    expect(validation.issues.map(issue => issue.reason)).toContain(
      'scene_id_mismatch',
    );
  });

  it('rejects an event payload WorldPoint from another scene', () => {
    const event = makeEvent({
      render: {
        kind: 'entity_moved',
        entity_id: 'entity.resident.alice',
        world_point: { scene_id: 'scene.other', x_wu: 0, y_wu: 0 },
        facing_degrees: 90,
      },
    });

    const validation = validateRenderEventEnvelope(event);

    expect(validation.ok).toBe(false);
    expect(validation.issues).toContainEqual({
      pointer: '/render/world_point/scene_id',
      reason: 'scene_id_mismatch',
    });
  });
});

describe('TEST-RENDER-001 SnapshotGate', () => {
  it('accepts a different snapshot id with the same revision and hash as replay', () => {
    const gate = new SnapshotGate(WORLD_ID, SCENE_ID);
    expect(gate.evaluate(makeFrame()).action).toBe('apply');

    const decision = gate.evaluate(
      makeFrame({ snapshot_id: 'snapshot.b' }),
    );

    expect(decision).toEqual({
      action: 'idempotent_replay',
      revision: 1,
    });
  });

  it('rejects conflicting content at the same revision even when snapshot id repeats', () => {
    const gate = new SnapshotGate(WORLD_ID, SCENE_ID);
    expect(gate.evaluate(makeFrame()).action).toBe('apply');

    const decision = gate.evaluate(
      makeFrame({ snapshot_content_sha256: CONTENT_HASH_B }),
    );

    expect(decision).toEqual({
      action: 'contract_error',
      reason: 'content_hash_conflict',
    });
  });

  it('rejects stale and wrong-scope snapshots without advancing revision', () => {
    const gate = new SnapshotGate(WORLD_ID, SCENE_ID);
    expect(gate.evaluate(makeFrame({ revision: 4 })).action).toBe('apply');

    expect(gate.evaluate(makeFrame({ revision: 3 })).action).toBe(
      'reject_stale',
    );
    expect(
      gate.evaluate(makeFrame({ revision: 5, scene_id: 'scene.other' })).action,
    ).toBe('contract_error');
    expect(gate.revision).toBe(4);
  });
});
