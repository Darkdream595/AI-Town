import { describe, expect, it } from 'vitest';
import {
  AudioStateController,
  deriveAudioTargetState,
  validateAudioLicenseChain,
} from '../audio_state';

const projection = (overrides = {}) => ({
  scene_id: 'scene.crown_creek',
  weather_id: 'weather.clear',
  lighting_band: 'day' as const,
  encounter: 'none' as const,
  muted: false,
  ...overrides,
});

describe('TEST-RENDER-010 audio state', () => {
  it('derives state only from confirmed projection fields', () => {
    expect(deriveAudioTargetState(projection()).audio_state_id).toBe(
      'audio_state.scene.crown_creek.day.clear.none',
    );
    expect(
      deriveAudioTargetState(
        projection({ localDangerScore: 100, wallClockHour: 2 } as never),
      ),
    ).toEqual(deriveAudioTargetState(projection()));
  });

  it('crossfades changes over 500 ms and keeps one instance of each layer', () => {
    const controller = new AudioStateController();
    controller.applyProjection(projection(), 0);
    controller.applyProjection(
      projection({ scene_id: 'scene.inn', encounter: 'combat' }),
      100,
    );

    expect(controller.crossfadeDurationMs).toBe(500);
    expect(controller.transitions.every((transition) => transition.duration_ms === 500)).toBe(true);
    expect(new Set(controller.activeLayers.map((layer) => layer.kind)).size).toBe(
      controller.activeLayers.length,
    );
  });

  it('limits every bus to eight concurrent instances', () => {
    const controller = new AudioStateController();
    for (let index = 0; index < 12; index += 1) {
      controller.playOneShot({
        asset_id: `audio.ui.${index}`,
        bus: 'ui',
        priority: index,
      });
    }

    expect(controller.getBusInstances('ui')).toHaveLength(8);
    expect(controller.getBusInstances('ui').map((instance) => instance.priority)).toEqual([
      4, 5, 6, 7, 8, 9, 10, 11,
    ]);
  });

  it('counts active layers and one-shots together toward the bus limit', () => {
    const controller = new AudioStateController();
    controller.applyProjection(projection({ encounter: 'combat' }), 0);
    for (let index = 0; index < 8; index += 1) {
      controller.playOneShot({
        asset_id: `audio.music.stinger.${index}`,
        bus: 'music',
        priority: index,
      });
    }

    const activeMusicLayerCount = controller.activeLayers.filter(
      (layer) => layer.bus === 'music',
    ).length;
    expect(activeMusicLayerCount).toBe(3);
    expect(controller.getBusInstances('music')).toHaveLength(5);
    expect(activeMusicLayerCount + controller.getBusInstances('music').length).toBe(8);
  });

  it('retains the target state and prompts once when autoplay is blocked', () => {
    const controller = new AudioStateController({ autoplayBlocked: true });
    const target = controller.applyProjection(
      projection({ weather_id: 'weather.rain.light', encounter: 'combat' }),
      0,
    );

    expect(controller.targetState).toEqual(target);
    expect(controller.activeLayers).toHaveLength(0);
    expect(controller.consumeEnableAudioPrompt()).toBe(true);
    expect(controller.consumeEnableAudioPrompt()).toBe(false);
    controller.resumeAfterUserGesture(50);
    expect(controller.activeLayers.length).toBeGreaterThan(0);
  });

  it('never re-pends the autoplay prompt after it has been consumed once', () => {
    const controller = new AudioStateController({ autoplayBlocked: true });
    controller.applyProjection(projection(), 0);
    expect(controller.consumeEnableAudioPrompt()).toBe(true);

    controller.applyProjection(projection({ scene_id: 'scene.inn' }), 100);
    expect(controller.consumeEnableAudioPrompt()).toBe(false);
    expect(controller.targetState?.scene_id).toBe('scene.inn');
  });

  it('validates the complete audio asset to license text hash chain', () => {
    const valid = validateAudioLicenseChain(
      {
        asset_id: 'audio.music.crown_creek.base',
        path: 'assets/audio/crown-creek.ogg',
        sha256: 'asset-hash',
        license_id: 'license.project_original_001',
      },
      {
        license_id: 'license.project_original_001',
        source: 'project',
        author: 'AI Town team',
        terms: 'project original',
        acquired_at: '2026-07-26',
        license_text_path: 'licenses/project-original.txt',
        license_text_sha256: 'license-hash',
      },
      {
        'assets/audio/crown-creek.ogg': 'asset-hash',
        'licenses/project-original.txt': 'license-hash',
      },
    );
    expect(valid).toEqual({ valid: true, diagnostics: [] });

    const invalid = validateAudioLicenseChain(
      {
        asset_id: 'audio.music.bad',
        path: 'assets/audio/bad.ogg',
        sha256: 'expected',
        license_id: 'license.missing',
      },
      {
        license_id: 'license.other',
        source: '',
        author: '',
        terms: '',
        acquired_at: '',
        license_text_path: '',
        license_text_sha256: '',
      },
      {},
    );
    expect(invalid.valid).toBe(false);
    expect(invalid.diagnostics).toContain('RENDER_LICENSE_ID_MISMATCH');
    expect(invalid.diagnostics).toContain('RENDER_LICENSE_METADATA_INCOMPLETE');
    expect(invalid.diagnostics).toContain('RENDER_LICENSE_ASSET_HASH_MISMATCH');
    expect(invalid.diagnostics).toContain('RENDER_LICENSE_TEXT_HASH_MISMATCH');
  });

  it('rejects matching but empty asset and license identifiers', () => {
    const result = validateAudioLicenseChain(
      {
        asset_id: 'audio.music.no-license-id',
        path: 'assets/audio/no-license-id.ogg',
        sha256: 'asset-hash',
        license_id: '',
      },
      {
        license_id: '',
        source: 'project',
        author: 'AI Town team',
        terms: 'project original',
        acquired_at: '2026-07-26',
        license_text_path: 'licenses/project-original.txt',
        license_text_sha256: 'license-hash',
      },
      {
        'assets/audio/no-license-id.ogg': 'asset-hash',
        'licenses/project-original.txt': 'license-hash',
      },
    );

    expect(result.valid).toBe(false);
    expect(result.diagnostics).toContain('RENDER_LICENSE_ID_MISMATCH');
  });

  it('suppresses one-shots while muted or autoplay-blocked without registering them', () => {
    const blockedController = new AudioStateController({ autoplayBlocked: true });
    expect(
      blockedController.playOneShot({
        asset_id: 'audio.ui.blocked',
        bus: 'ui',
        priority: 1,
      }),
    ).toEqual({ status: 'suppressed' });
    expect(blockedController.getBusInstances('ui')).toHaveLength(0);

    const mutedController = new AudioStateController();
    mutedController.applyProjection(projection(), 0);
    expect(
      mutedController.playOneShot({
        asset_id: 'audio.ui.before-mute',
        bus: 'ui',
        priority: 1,
      }),
    ).toEqual({ status: 'played' });
    mutedController.applyProjection(projection({ muted: true }), 10);
    expect(mutedController.getBusInstances('ui')).toHaveLength(0);
    expect(
      mutedController.playOneShot({
        asset_id: 'audio.ui.while-muted',
        bus: 'ui',
        priority: 1,
      }),
    ).toEqual({ status: 'suppressed' });

    mutedController.applyProjection(projection({ muted: false }), 20);
    expect(mutedController.getBusInstances('ui')).toHaveLength(0);
  });

  it('clears pending one-shots when entering autoplay-blocked state', () => {
    const controller = new AudioStateController();
    controller.applyProjection(projection(), 0);
    controller.playOneShot({
      asset_id: 'audio.alert.pending',
      bus: 'alert',
      priority: 10,
    });

    controller.setAutoplayBlocked(true);
    expect(controller.getBusInstances('alert')).toHaveLength(0);
    expect(
      controller.playOneShot({
        asset_id: 'audio.alert.blocked',
        bus: 'alert',
        priority: 10,
      }),
    ).toEqual({ status: 'suppressed' });

    controller.resumeAfterUserGesture(100);
    expect(controller.getBusInstances('alert')).toHaveLength(0);
  });

  it('bounds and drains transition history', () => {
    const controller = new AudioStateController({ transitionCapacity: 3 });
    controller.applyProjection(projection(), 0);
    controller.applyProjection(projection({ scene_id: 'scene.inn' }), 10);
    controller.applyProjection(projection({ scene_id: 'scene.square' }), 20);

    expect(controller.transitions).toHaveLength(3);
    expect(controller.consumeTransitions()).toHaveLength(3);
    expect(controller.transitions).toHaveLength(0);
    expect(controller.consumeTransitions()).toEqual([]);
  });
});
