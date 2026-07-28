import { describe, expect, it } from 'vitest';
import { VfxController, validateVfxSpec } from '../vfx';

const event = (eventId: string, overrides = {}) => ({
  event_id: eventId,
  vfx_id: 'vfx.arcane.spark_burst',
  anchor: { scene_id: 'scene.square', x_wu: 2, y_wu: 3 },
  category: 'combat' as const,
  ...overrides,
});

describe('TEST-RENDER-008 VFX lifecycle', () => {
  it('validates duration and the three legal attach points', () => {
    expect(
      validateVfxSpec({
        vfx_id: 'vfx.test',
        asset_id: 'vfx.test.asset',
        attach_point: 'caster_feet',
        duration_ms: 100,
      }),
    ).toBe(true);
    expect(
      validateVfxSpec({
        vfx_id: 'vfx.test',
        asset_id: 'vfx.test.asset',
        attach_point: 'target_center',
        duration_ms: 1500,
      }),
    ).toBe(true);
    expect(
      validateVfxSpec({
        vfx_id: 'vfx.test',
        asset_id: 'vfx.test.asset',
        attach_point: 'ground_point',
        duration_ms: 99,
      }),
    ).toBe(false);
  });

  it('plays each event id once and recycles expired objects', () => {
    const controller = new VfxController();
    expect(controller.play(event('event-1'), 0).status).toBe('played');
    expect(controller.play(event('event-1'), 1).status).toBe('duplicate');
    expect(controller.activeCount).toBe(1);
    controller.sweep(420);
    expect(controller.activeCount).toBe(0);
    expect(controller.pooledCount).toBe(1);
  });

  it('recycles all active objects on dispose', () => {
    const controller = new VfxController();
    controller.play(event('event-1'), 0);
    controller.play(event('event-2'), 0);
    controller.dispose();
    expect(controller.activeCount).toBe(0);
    expect(controller.pooledCount).toBe(2);
  });

  it('caps active effects at 96 and prioritizes combat over environment effects', () => {
    const controller = new VfxController();
    for (let index = 0; index < 96; index += 1) {
      controller.play(
        event(`environment-${index}`, {
          vfx_id: 'vfx.environment.dust',
          category: 'environment',
        }),
        0,
      );
    }

    expect(controller.activeCount).toBe(96);
    expect(controller.play(event('critical-combat'), 1).status).toBe('played');
    expect(controller.activeCount).toBe(96);
    expect(
      controller.play(
        event('extra-environment', {
          vfx_id: 'vfx.environment.mist',
          category: 'environment',
        }),
        2,
      ).status,
    ).toBe('rejected');
  });

  it('falls unknown resources back to a non-flashing status ping', () => {
    const controller = new VfxController();
    const result = controller.play(event('unknown', { vfx_id: 'vfx.not.registered' }), 0);
    expect(result.resolved_vfx_id).toBe('vfx.fallback.status_ping');
    expect(result.effect.static_icon).toBe(true);
    expect(result.effect.flash).toBe(false);
  });

  it('uses static accessible replacements in reduced motion', () => {
    const controller = new VfxController({ reducedMotion: true });
    const result = controller.play(event('event-1'), 0);
    expect(result.effect).toMatchObject({
      particles: false,
      flash: false,
      camera_shake: false,
      static_border: true,
      static_icon: true,
    });
  });

  it('defaults presentation flags off and enables only explicitly declared effects', () => {
    const controller = new VfxController({
      specs: [
        {
          vfx_id: 'vfx.environment.fireflies',
          asset_id: 'vfx.environment.fireflies',
          attach_point: 'ground_point',
          duration_ms: 500,
        },
        {
          vfx_id: 'vfx.combat.impact',
          asset_id: 'vfx.combat.impact',
          attach_point: 'target_center',
          duration_ms: 200,
          presentation: {
            particles: true,
            flash: true,
            camera_shake: true,
          },
        },
      ],
    });

    expect(
      controller.play(
        event('environment-safe', {
          vfx_id: 'vfx.environment.fireflies',
          category: 'environment',
        }),
        0,
      ).effect,
    ).toMatchObject({
      particles: false,
      flash: false,
      camera_shake: false,
    });
    expect(
      controller.play(event('combat-explicit', { vfx_id: 'vfx.combat.impact' }), 0).effect,
    ).toMatchObject({
      particles: true,
      flash: true,
      camera_shake: true,
    });
  });

  it('keeps the seen-event cache bounded and clears it on dispose', () => {
    const controller = new VfxController({ seenEventCapacity: 2 });
    controller.play(event('event-1'), 0);
    controller.play(event('event-2'), 0);
    controller.play(event('event-3'), 0);
    expect(controller.seenEventCount).toBe(2);
    expect(controller.play(event('event-1'), 1).status).toBe('played');

    controller.dispose();
    expect(controller.seenEventCount).toBe(0);
    expect(controller.play(event('event-1'), 2).status).toBe('played');
  });

  it('keeps explicitly animated combat effects static under reduced motion', () => {
    const controller = new VfxController({
      reducedMotion: true,
      specs: [
        {
          vfx_id: 'vfx.combat.impact',
          asset_id: 'vfx.combat.impact',
          attach_point: 'target_center',
          duration_ms: 200,
          presentation: {
            particles: true,
            flash: true,
            camera_shake: true,
          },
        },
      ],
    });

    expect(controller.play(event('combat', { vfx_id: 'vfx.combat.impact' }), 0).effect)
      .toMatchObject({
        particles: false,
        flash: false,
        camera_shake: false,
        static_border: true,
        static_icon: true,
      });
  });
});
