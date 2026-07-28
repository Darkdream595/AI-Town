import { describe, expect, it } from 'vitest';
import {
  LIGHTING_REGISTRY,
  projectEnvironmentVisualState,
  resolveLightingAtGameTime,
  smoothstep,
} from '../environment';

const projection = (gameTime: number) => ({
  world_id: 'world.medieval',
  scene_id: 'scene.square',
  revision: 1,
  game_time: gameTime,
  weather_id: 'weather.rain.light',
  intensity_0_to_1: 0.75,
  lighting_registry_id: LIGHTING_REGISTRY.id,
  lighting_registry_sha256: LIGHTING_REGISTRY.sha256,
});

describe('TEST-RENDER-007 environment projection', () => {
  it('covers every minute exactly once and resolves all boundaries', () => {
    for (let minute = 0; minute < 1440; minute += 1) {
      const matches = LIGHTING_REGISTRY.bands.filter(
        (band) => minute >= band.start_minute && minute < band.end_minute,
      );
      expect(matches).toHaveLength(1);
    }

    expect(resolveLightingAtGameTime(0).resolved_lighting_band).toBe('night');
    expect(resolveLightingAtGameTime(300).resolved_lighting_band).toBe('dawn');
    expect(resolveLightingAtGameTime(420).resolved_lighting_band).toBe('day');
    expect(resolveLightingAtGameTime(1080).resolved_lighting_band).toBe('dusk');
    expect(resolveLightingAtGameTime(1200).resolved_lighting_band).toBe('night');
    expect(resolveLightingAtGameTime(1440 + 300).resolved_lighting_band).toBe('dawn');
    expect(resolveLightingAtGameTime(-1).resolved_lighting_band).toBe('night');
  });

  it('uses smoothstep for the first 60 minutes of a new band', () => {
    expect(smoothstep(0)).toBe(0);
    expect(smoothstep(0.5)).toBe(0.5);
    expect(smoothstep(1)).toBe(1);
    expect(resolveLightingAtGameTime(330).transition_t).toBe(0.5);
    expect(resolveLightingAtGameTime(500).transition_t).toBe(1);
    expect(resolveLightingAtGameTime(0).transition_t).toBe(1);
    expect(resolveLightingAtGameTime(1200).from_preset_id).toBe('lighting.preset.dusk');
  });

  it('preserves the last valid state and requests a snapshot on registry mismatch', () => {
    const valid = projectEnvironmentVisualState(null, projection(420));
    const rejected = projectEnvironmentVisualState(valid.state, {
      ...projection(421),
      lighting_registry_sha256: 'wrong',
    });

    expect(rejected.accepted).toBe(false);
    expect(rejected.state).toBe(valid.state);
    expect(rejected.reason).toBe('RENDER_LIGHTING_REGISTRY_MISMATCH');
    expect(rejected.request_snapshot).toBe(true);
  });

  it('rejects an externally supplied band that disagrees with local derivation', () => {
    const valid = projectEnvironmentVisualState(null, projection(420));
    const rejected = projectEnvironmentVisualState(valid.state, {
      ...projection(1080),
      resolved_lighting_band: 'day' as const,
    });

    expect(rejected.accepted).toBe(false);
    expect(rejected.state).toBe(valid.state);
    expect(rejected.reason).toBe('RENDER_LIGHTING_REGISTRY_MISMATCH');
  });

  it('falls unknown weather back to clear and clamps intensity', () => {
    const result = projectEnvironmentVisualState(null, {
      ...projection(420),
      weather_id: 'weather.unknown',
      intensity_0_to_1: 4,
    });

    expect(result.state?.weather_id).toBe('weather.clear');
    expect(result.state?.intensity_0_to_1).toBe(1);
    expect(result.state?.contract_errors).toContain('RENDER_UNKNOWN_WEATHER');
  });

  it('replaces particles, flashes, and shake with static semantics in reduced motion', () => {
    const result = projectEnvironmentVisualState(null, projection(420), {
      reducedMotion: true,
    });

    expect(result.state?.weather_effect).toEqual({
      particle_asset_id: null,
      flash: false,
      camera_shake: false,
      static_tint: true,
      static_icon_id: 'weather.icon.rain',
    });
  });
});
