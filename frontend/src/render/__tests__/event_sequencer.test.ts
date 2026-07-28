import { describe, expect, it } from 'vitest';
import type { RenderEventEnvelope } from '../../types/rendering';
import { EventSequencer } from '../event_sequencer';

const WORLD_ID = 'world.test';
const SCENE_ID = 'scene.town';
const ANIMATION_STATES = [
  'idle',
  'walk',
  'work',
  'combat',
  'cast',
  'attack',
  'hurt',
  'downed',
] as const;

function makeEvent(
  revision: number,
  index = 0,
  count = 1,
  eventId = `event.${revision}.${index}`,
): RenderEventEnvelope {
  return {
    protocol_version: 'render.v1',
    event_id: eventId,
    world_id: WORLD_ID,
    scene_id: SCENE_ID,
    revision,
    game_time: revision,
    causation_id: `command.${revision}`,
    correlation_id: `correlation.${revision}`,
    transaction_event_index: index,
    transaction_event_count: count,
    render: {
      kind: 'entity_despawned',
      entity_id: `entity.${eventId}`,
    },
  };
}

describe('TEST-RENDER-001 EventSequencer', () => {
  it('atomically returns a complete revision in deterministic index order', () => {
    const sequencer = new EventSequencer(WORLD_ID, SCENE_ID, 4);

    expect(sequencer.push(makeEvent(5, 1, 2, 'event.b')).action).toBe(
      'pending',
    );
    const result = sequencer.push(makeEvent(5, 0, 2, 'event.a'));

    expect(result.action).toBe('applied');
    if (result.action === 'applied') {
      expect(result.revision).toBe(5);
      expect(result.events.map(event => event.event_id)).toEqual([
        'event.a',
        'event.b',
      ]);
    }
    expect(sequencer.appliedRevision).toBe(5);
  });

  it('rejects a malformed or mismatched batch without advancing revision', () => {
    const sequencer = new EventSequencer(WORLD_ID, SCENE_ID, 9);
    expect(sequencer.push(makeEvent(10, 0, 2)).action).toBe('pending');

    const inconsistent = sequencer.push(makeEvent(10, 1, 3));

    expect(inconsistent.action).toBe('contract_error');
    expect(sequencer.appliedRevision).toBe(9);
    expect(
      sequencer.push({
        ...makeEvent(10, 1, 2),
        protocol_version: 'render.v2',
      }).action,
    ).toBe('contract_error');
    expect(sequencer.appliedRevision).toBe(9);
  });

  it('returns a contract error instead of throwing for non-object input', () => {
    const sequencer = new EventSequencer(WORLD_ID, SCENE_ID, 0);

    expect(
      sequencer.push(null as unknown as RenderEventEnvelope),
    ).toEqual({
      action: 'contract_error',
      reason: '/:event_not_object',
    });
    expect(sequencer.appliedRevision).toBe(0);
  });

  it('rejects unknown and incomplete payload kinds without partial apply', () => {
    const sequencer = new EventSequencer(WORLD_ID, SCENE_ID, 0);
    expect(sequencer.push(makeEvent(1, 0, 2, 'event.valid')).action).toBe(
      'pending',
    );

    const unknownKind = makeEvent(1, 1, 2, 'event.unknown');
    unknownKind.render = {
      kind: 'entity_teleported',
      entity_id: 'entity.a',
    } as unknown as RenderEventEnvelope['render'];
    expect(sequencer.push(unknownKind).action).toBe('contract_error');
    expect(sequencer.appliedRevision).toBe(0);

    const missingFields = makeEvent(1, 1, 2, 'event.missing');
    missingFields.render = {
      kind: 'entity_moved',
      entity_id: 'entity.a',
    } as RenderEventEnvelope['render'];
    expect(sequencer.push(missingFields).action).toBe('contract_error');
    expect(sequencer.appliedRevision).toBe(0);
  });

  it('validates required fields for every render payload kind', () => {
    const invalidPayloads: RenderEventEnvelope['render'][] = [
      {
        kind: 'entity_animation_changed',
        entity_id: '',
        world_point: { scene_id: SCENE_ID, x_wu: 0, y_wu: 0 },
        facing_degrees: 90,
        desired_animation_state: {
          animation_id: 'anim.walk',
          state: 'walk',
          loop: true,
          since_revision: 1,
        },
      },
      {
        kind: 'entity_moved',
        entity_id: 'entity.a',
        world_point: { scene_id: SCENE_ID, x_wu: 0, y_wu: 0 },
        facing_degrees: 45,
      } as unknown as RenderEventEnvelope['render'],
      {
        kind: 'entity_spawned',
        entity_id: 'entity.a',
        asset_id: '',
        world_point: { scene_id: SCENE_ID, x_wu: 0, y_wu: 0 },
        facing_degrees: 90,
        desired_animation_state: {
          animation_id: 'anim.walk',
          state: 'walk',
          loop: true,
          since_revision: 1,
        },
      },
      { kind: 'entity_despawned', entity_id: '' },
    ];

    invalidPayloads.forEach((render, index) => {
      const sequencer = new EventSequencer(WORLD_ID, SCENE_ID, index);
      expect(
        sequencer.push({
          ...makeEvent(index + 1),
          render,
        }).action,
      ).toBe('contract_error');
      expect(sequencer.appliedRevision).toBe(index);
    });
  });

  it.each(ANIMATION_STATES)(
    'accepts animation_changed state %s',
    state => {
      const sequencer = new EventSequencer(WORLD_ID, SCENE_ID, 0);
      const event = makeEvent(1);
      event.render = {
        kind: 'entity_animation_changed',
        entity_id: 'entity.a',
        world_point: { scene_id: SCENE_ID, x_wu: 0, y_wu: 0 },
        facing_degrees: 90,
        desired_animation_state: {
          animation_id: `anim.${state}`,
          state,
          loop: state !== 'downed',
          since_revision: 1,
        },
      };

      expect(sequencer.push(event).action).toBe('applied');
    },
  );

  it.each(ANIMATION_STATES)('accepts spawned state %s', state => {
    const sequencer = new EventSequencer(WORLD_ID, SCENE_ID, 0);
    const event = makeEvent(1);
    event.render = {
      kind: 'entity_spawned',
      entity_id: 'entity.a',
      asset_id: 'sprite.entity.a',
      world_point: { scene_id: SCENE_ID, x_wu: 0, y_wu: 0 },
      facing_degrees: 90,
      desired_animation_state: {
        animation_id: `anim.${state}`,
        state,
        loop: state !== 'downed',
        since_revision: 1,
      },
    };

    expect(sequencer.push(event).action).toBe('applied');
  });

  it('rejects an animation state outside the shared union', () => {
    const sequencer = new EventSequencer(WORLD_ID, SCENE_ID, 0);
    const event = makeEvent(1);
    event.render = {
      kind: 'entity_animation_changed',
      entity_id: 'entity.a',
      world_point: { scene_id: SCENE_ID, x_wu: 0, y_wu: 0 },
      facing_degrees: 90,
      desired_animation_state: {
        animation_id: 'anim.unknown',
        state: 'teleporting',
        loop: false,
        since_revision: 1,
      },
    } as unknown as RenderEventEnvelope['render'];

    expect(sequencer.push(event).action).toBe('contract_error');
    expect(sequencer.appliedRevision).toBe(0);
  });

  it('reports revision gaps and discards events at or before a snapshot', () => {
    const sequencer = new EventSequencer(WORLD_ID, SCENE_ID, 20);

    expect(sequencer.push(makeEvent(22))).toEqual({
      action: 'resync',
      expected_revision: 21,
      received_revision: 22,
    });
    expect(sequencer.push(makeEvent(20)).action).toBe('stale');
    expect(sequencer.push(makeEvent(19)).action).toBe('stale');
  });

  it('drops old pending revisions when a newer snapshot is applied', () => {
    const sequencer = new EventSequencer(WORLD_ID, SCENE_ID, 3);
    expect(sequencer.push(makeEvent(4, 0, 2))).toEqual({
      action: 'pending',
      revision: 4,
      received: 1,
      expected: 2,
    });

    sequencer.onSnapshotApplied(4);

    expect(sequencer.push(makeEvent(4, 1, 2)).action).toBe('stale');
    expect(sequencer.appliedRevision).toBe(4);
  });

  it('uses true LRU eviction when dedupe capacity is reached', () => {
    let now = 0;
    const sequencer = new EventSequencer(WORLD_ID, SCENE_ID, 0, {
      now: () => now,
      dedupeCapacity: 2,
      dedupeTtlMs: 30 * 60 * 1000,
    });

    expect(sequencer.push(makeEvent(1, 0, 1, 'event.shared')).action).toBe(
      'applied',
    );
    expect(sequencer.push(makeEvent(2, 0, 1, 'event.shared')).action).toBe(
      'duplicate',
    );
    expect(sequencer.push(makeEvent(2, 0, 1, 'event.second')).action).toBe(
      'applied',
    );
    expect(sequencer.push(makeEvent(3, 0, 1, 'event.shared')).action).toBe(
      'duplicate',
    );
    expect(sequencer.push(makeEvent(3, 0, 1, 'event.third')).action).toBe(
      'applied',
    );
    expect(sequencer.push(makeEvent(4, 0, 1, 'event.second')).action).toBe(
      'applied',
    );
  });

  it('expires dedupe entries after 30 minutes', () => {
    let now = 0;
    const sequencer = new EventSequencer(WORLD_ID, SCENE_ID, 0, {
      now: () => now,
    });
    expect(sequencer.push(makeEvent(1, 0, 1, 'event.shared')).action).toBe(
      'applied',
    );
    now = 30 * 60 * 1000 + 1;
    expect(sequencer.push(makeEvent(2, 0, 1, 'event.shared')).action).toBe(
      'applied',
    );
  });
});
