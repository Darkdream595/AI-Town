import { afterEach, describe, expect, it, vi } from 'vitest';
import { EventBus } from '../../core/EventBus';
import {
  QA_RENDER_FIXTURE_ID,
  createQaRenderFixture,
  installQaFixtureCoordinator,
  requestedQaFixtureId,
} from '../render_fixture';

afterEach(() => EventBus.clear());

describe('auditable render QA fixture', () => {
  it('is opt-in through the exact qa query and never injects in normal mode', () => {
    expect(requestedQaFixtureId('?qa=qa.render.crown_creek_stress_v1')).toBe(
      QA_RENDER_FIXTURE_ID,
    );
    expect(requestedQaFixtureId('')).toBeNull();
    expect(requestedQaFixtureId('?qa=other')).toBeNull();
  });

  it('contains a fixed snapshot with 12 visible residents and explicit capabilities', () => {
    const fixture = createQaRenderFixture();

    expect(fixture.snapshot.entities).toHaveLength(12);
    expect(new Set(fixture.snapshot.entities.map(entity => entity.entity_id)).size).toBe(12);
    expect(fixture.snapshot.scene_id).toBe('scene.crown_creek_town');
    expect(fixture.event_log_sha256).toMatch(/^[a-f0-9]{64}$/);
    expect(fixture.capabilities).toEqual(
      expect.objectContaining({
        heavy_rain: false,
        vfx: false,
        overlay: false,
      }),
    );
  });

  it('injects exactly once only after both WorldScene and UIScene are ready', () => {
    const renderFrames: unknown[] = [];
    const uiFrames: unknown[] = [];
    EventBus.on('render:frame:update', frame => renderFrames.push(frame));
    EventBus.on('ui:update', frame => uiFrames.push(frame));

    const dispose = installQaFixtureCoordinator(
      '?qa=qa.render.crown_creek_stress_v1',
    );
    EventBus.emit('world-scene-ready');
    expect(renderFrames).toHaveLength(0);
    EventBus.emit('ui-scene-ready');
    EventBus.emit('world-scene-ready');

    expect(renderFrames).toHaveLength(1);
    expect(uiFrames).toHaveLength(1);
    dispose();
  });

  it('does not subscribe or inject local facts in normal mode', () => {
    const renderFrame = vi.fn();
    EventBus.on('render:frame:update', renderFrame);

    installQaFixtureCoordinator('');
    EventBus.emit('world-scene-ready');
    EventBus.emit('ui-scene-ready');

    expect(renderFrame).not.toHaveBeenCalled();
  });
});
