import { describe, expect, it, vi } from 'vitest';
import {
  AnimationMachine,
  priorityOf,
  type AnimationRequest,
} from '../animation_sm';

function request(
  overrides: Partial<AnimationRequest> = {},
): AnimationRequest {
  return {
    asset_id: 'sprite.resident.apothecary',
    scene_id: 'region.crown_creek_town',
    revision: 1,
    kind: 'idle',
    direction: 'south',
    animation_id: 'anim.resident.idle_south',
    ...overrides,
  };
}

describe('TEST-RENDER-005 animation state machine', () => {
  it('uses the canonical priority order', () => {
    expect(priorityOf('downed')).toBeGreaterThan(priorityOf('hurt'));
    expect(priorityOf('hurt')).toBeGreaterThan(priorityOf('attack'));
    expect(priorityOf('attack')).toBe(priorityOf('cast'));
    expect(priorityOf('cast')).toBeGreaterThan(priorityOf('walk'));
    expect(priorityOf('walk')).toBeGreaterThan(priorityOf('idle'));
  });

  it('lets only a newer revision replace a state at the same priority', () => {
    const machine = new AnimationMachine({
      now: () => 100,
      exists: () => true,
    });

    expect(machine.apply(request({ revision: 4, kind: 'attack' }))).toBe(true);
    expect(
      machine.apply(
        request({
          revision: 3,
          kind: 'cast',
          animation_id: 'anim.resident.cast_south',
        }),
      ),
    ).toBe(false);
    expect(machine.current().kind).toBe('attack');

    expect(
      machine.apply(
        request({
          revision: 5,
          kind: 'cast',
          animation_id: 'anim.resident.cast_south',
        }),
      ),
    ).toBe(true);
    expect(machine.current().kind).toBe('cast');
  });

  it.each([
    {
      latestKind: 'walk' as const,
      staleKind: 'idle' as const,
      latestAnimationId: 'anim.resident.walk_south',
      staleAnimationId: 'anim.resident.idle_south',
    },
    {
      latestKind: 'idle' as const,
      staleKind: 'walk' as const,
      latestAnimationId: 'anim.resident.idle_south',
      staleAnimationId: 'anim.resident.walk_south',
    },
  ])(
    'rejects stale $staleKind after authoritative $latestKind across locomotion priorities',
    ({ latestKind, staleKind, latestAnimationId, staleAnimationId }) => {
      const machine = new AnimationMachine({
        now: () => 0,
        exists: () => true,
      });
      machine.apply(
        request({
          revision: 10,
          kind: latestKind,
          animation_id: latestAnimationId,
        }),
      );

      expect(
        machine.apply(
          request({
            revision: 9,
            kind: staleKind,
            animation_id: staleAnimationId,
          }),
        ),
      ).toBe(false);
      expect(machine.current()).toMatchObject({
        revision: 10,
        kind: latestKind,
        animation_id: latestAnimationId,
      });
    },
  );

  it('lets higher priority interrupt and rejects lower priority while active', () => {
    const machine = new AnimationMachine({
      now: () => 0,
      exists: () => true,
    });
    machine.apply(
      request({
        revision: 1,
        kind: 'attack',
        animation_id: 'anim.resident.attack_south',
      }),
    );

    expect(
      machine.apply(
        request({
          revision: 2,
          kind: 'hurt',
          animation_id: 'anim.resident.hurt_south',
        }),
      ),
    ).toBe(true);
    expect(machine.current().kind).toBe('hurt');
    expect(
      machine.apply(
        request({
          revision: 3,
          kind: 'cast',
          animation_id: 'anim.resident.cast_south',
        }),
      ),
    ).toBe(false);
    expect(machine.current().kind).toBe('hurt');
    expect(
      machine.apply(
        request({
          revision: 4,
          kind: 'downed',
          animation_id: 'anim.resident.downed_south',
        }),
      ),
    ).toBe(true);
    expect(machine.current().kind).toBe('downed');
  });

  it.each(['attack', 'cast', 'hurt'] as const)(
    'limits %s to 900 ms before restoring authoritative locomotion',
    kind => {
      let now = 0;
      const machine = new AnimationMachine({
        now: () => now,
        exists: () => true,
      });
      machine.apply(request({ revision: 1, kind: 'walk' }));
      machine.apply(
        request({
          revision: 2,
          kind,
          animation_id: `anim.resident.${kind}_south`,
        }),
      );

      now = 899;
      expect(machine.tick().kind).toBe(kind);
      now = 900;
      expect(machine.tick().kind).toBe('walk');
    },
  );

  it.each(['attack', 'cast', 'hurt'] as const)(
    'returns a first %s state to deterministic directional idle at 900 ms',
    kind => {
      let now = 0;
      const machine = new AnimationMachine({
        now: () => now,
        exists: () => true,
      });
      machine.apply(
        request({
          kind,
          direction: 'east',
          animation_id: `anim.resident.${kind}_east`,
        }),
      );

      now = 899;
      expect(machine.tick().kind).toBe(kind);
      now = 900;
      expect(machine.tick()).toMatchObject({
        kind: 'idle',
        direction: 'east',
        animation_id: 'anim.resident.idle_east',
        revision: 1,
      });
    },
  );

  it('returns a transient state to the latest authoritative locomotion by 900 ms', () => {
    let now = 0;
    const machine = new AnimationMachine({
      now: () => now,
      exists: () => true,
    });
    machine.apply(request({ revision: 1, kind: 'idle' }));
    machine.apply(
      request({
        revision: 2,
        kind: 'hurt',
        animation_id: 'anim.resident.hurt_south',
      }),
    );
    machine.apply(
      request({
        revision: 3,
        kind: 'walk',
        direction: 'east',
        animation_id: 'anim.resident.walk_east',
      }),
    );

    now = 899;
    expect(machine.tick().kind).toBe('hurt');
    now = 900;
    expect(machine.tick()).toMatchObject({
      kind: 'walk',
      revision: 3,
      animation_id: 'anim.resident.walk_east',
    });
  });

  it('falls back from the target to directional idle and then global south idle', () => {
    const available = new Set(['anim.resident.idle_east']);
    const machine = new AnimationMachine({
      now: () => 0,
      exists: animationId => available.has(animationId),
    });
    machine.apply(
      request({
        kind: 'attack',
        direction: 'east',
        animation_id: 'anim.resident.attack_east',
      }),
    );
    expect(machine.current().animation_id).toBe('anim.resident.idle_east');

    available.clear();
    available.add('anim.fallback.idle_south');
    machine.apply(
      request({
        revision: 2,
        kind: 'cast',
        direction: 'north',
        animation_id: 'anim.resident.cast_north',
      }),
    );
    expect(machine.current().animation_id).toBe('anim.fallback.idle_south');
  });

  it('emits one missing diagnostic per asset and scene pair', () => {
    const onMissingAnimation = vi.fn();
    const machine = new AnimationMachine({
      now: () => 0,
      exists: () => false,
      onMissingAnimation,
    });
    machine.apply(request({ animation_id: 'anim.resident.attack_south', kind: 'attack' }));
    machine.apply(
      request({
        revision: 2,
        animation_id: 'anim.resident.cast_north',
        kind: 'cast',
        direction: 'north',
      }),
    );
    machine.apply(
      request({
        revision: 3,
        scene_id: 'region.harbor',
        animation_id: 'anim.resident.hurt_south',
        kind: 'hurt',
      }),
    );

    expect(onMissingAnimation).toHaveBeenCalledTimes(2);
    expect(onMissingAnimation.mock.calls[0][0]).toMatchObject({
      issue: 'ANIMATION_ASSET_MISSING',
      asset_id: 'sprite.resident.apothecary',
      scene_id: 'region.crown_creek_town',
    });
  });
});
