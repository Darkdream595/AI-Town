export type LightingBand = 'dawn' | 'day' | 'dusk' | 'night';

export interface LightingRegistryBand {
  band: LightingBand;
  start_minute: number;
  end_minute: number;
  preset_id: string;
  transition_minutes: number;
  curve: 'smoothstep';
}

export const LIGHTING_REGISTRY = {
  id: 'lighting.registry.medieval_v1',
  sha256: '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e26f3ea47c190a9b18aab45',
  bands: [
    {
      band: 'night',
      start_minute: 0,
      end_minute: 300,
      preset_id: 'lighting.preset.night',
      transition_minutes: 0,
      curve: 'smoothstep',
    },
    {
      band: 'dawn',
      start_minute: 300,
      end_minute: 420,
      preset_id: 'lighting.preset.dawn',
      transition_minutes: 60,
      curve: 'smoothstep',
    },
    {
      band: 'day',
      start_minute: 420,
      end_minute: 1080,
      preset_id: 'lighting.preset.day',
      transition_minutes: 60,
      curve: 'smoothstep',
    },
    {
      band: 'dusk',
      start_minute: 1080,
      end_minute: 1200,
      preset_id: 'lighting.preset.dusk',
      transition_minutes: 60,
      curve: 'smoothstep',
    },
    {
      band: 'night',
      start_minute: 1200,
      end_minute: 1440,
      preset_id: 'lighting.preset.night',
      transition_minutes: 60,
      curve: 'smoothstep',
    },
  ] satisfies LightingRegistryBand[],
} as const;

export interface EnvironmentRenderProjection {
  world_id: string;
  scene_id: string;
  revision: number;
  game_time: number;
  weather_id: string;
  intensity_0_to_1: number;
  lighting_registry_id: string;
  lighting_registry_sha256: string;
  resolved_lighting_band?: LightingBand;
}

export interface LightingState {
  resolved_lighting_band: LightingBand;
  from_preset_id: string;
  to_preset_id: string;
  transition_t: number;
}

export interface WeatherEffectState {
  particle_asset_id: string | null;
  flash: boolean;
  camera_shake: boolean;
  static_tint: boolean;
  static_icon_id: string | null;
}

export interface EnvironmentVisualState extends LightingState {
  world_id: string;
  scene_id: string;
  revision: number;
  game_minute_of_day: number;
  weather_id: string;
  intensity_0_to_1: number;
  weather_effect: WeatherEffectState;
  contract_errors: string[];
}

export interface EnvironmentProjectionResult {
  accepted: boolean;
  state: EnvironmentVisualState | null;
  reason?: 'RENDER_LIGHTING_REGISTRY_MISMATCH';
  request_snapshot: boolean;
}

const KNOWN_WEATHER = new Set([
  'weather.clear',
  'weather.rain.light',
  'weather.rain.heavy',
  'weather.snow',
  'weather.fog',
  'weather.sandstorm',
]);

export function normalizeGameMinute(gameTime: number): number {
  if (!Number.isFinite(gameTime)) {
    return 0;
  }
  const wholeMinute = Math.floor(gameTime);
  return ((wholeMinute % 1440) + 1440) % 1440;
}

export function smoothstep(value: number): number {
  const clamped = Math.min(1, Math.max(0, value));
  return clamped * clamped * (3 - 2 * clamped);
}

export function resolveLightingAtGameTime(gameTime: number): LightingState {
  const minute = normalizeGameMinute(gameTime);
  const bandIndex = LIGHTING_REGISTRY.bands.findIndex(
    (candidate) => minute >= candidate.start_minute && minute < candidate.end_minute,
  );
  const band = LIGHTING_REGISTRY.bands[bandIndex];
  const previousBand =
    LIGHTING_REGISTRY.bands[(bandIndex - 1 + LIGHTING_REGISTRY.bands.length) %
      LIGHTING_REGISTRY.bands.length];

  if (band.transition_minutes === 0 || band.preset_id === previousBand.preset_id) {
    return {
      resolved_lighting_band: band.band,
      from_preset_id: band.preset_id,
      to_preset_id: band.preset_id,
      transition_t: 1,
    };
  }

  return {
    resolved_lighting_band: band.band,
    from_preset_id: previousBand.preset_id,
    to_preset_id: band.preset_id,
    transition_t: smoothstep((minute - band.start_minute) / band.transition_minutes),
  };
}

export function projectEnvironmentVisualState(
  previousState: EnvironmentVisualState | null,
  projection: EnvironmentRenderProjection,
  options: { reducedMotion?: boolean } = {},
): EnvironmentProjectionResult {
  const lighting = resolveLightingAtGameTime(projection.game_time);
  const registryMatches =
    projection.lighting_registry_id === LIGHTING_REGISTRY.id &&
    projection.lighting_registry_sha256 === LIGHTING_REGISTRY.sha256;
  const externalBandMatches =
    projection.resolved_lighting_band === undefined ||
    projection.resolved_lighting_band === lighting.resolved_lighting_band;

  if (!registryMatches || !externalBandMatches) {
    return {
      accepted: false,
      state: previousState,
      reason: 'RENDER_LIGHTING_REGISTRY_MISMATCH',
      request_snapshot: true,
    };
  }

  const contractErrors: string[] = [];
  const weatherId = KNOWN_WEATHER.has(projection.weather_id)
    ? projection.weather_id
    : 'weather.clear';
  if (weatherId !== projection.weather_id) {
    contractErrors.push('RENDER_UNKNOWN_WEATHER');
  }
  const rawIntensity = Number.isFinite(projection.intensity_0_to_1)
    ? projection.intensity_0_to_1
    : 0;
  const intensity = Math.min(1, Math.max(0, rawIntensity));
  const reducedMotion = options.reducedMotion === true;
  const weatherKind = weatherId.split('.')[1] ?? 'clear';

  return {
    accepted: true,
    request_snapshot: false,
    state: {
      world_id: projection.world_id,
      scene_id: projection.scene_id,
      revision: projection.revision,
      game_minute_of_day: normalizeGameMinute(projection.game_time),
      weather_id: weatherId,
      intensity_0_to_1: intensity,
      ...lighting,
      weather_effect: {
        particle_asset_id:
          reducedMotion || weatherId === 'weather.clear' ? null : `weather.particle.${weatherKind}`,
        flash: !reducedMotion && weatherId === 'weather.rain.heavy',
        camera_shake: false,
        static_tint: reducedMotion,
        static_icon_id: reducedMotion && weatherId !== 'weather.clear'
          ? `weather.icon.${weatherKind}`
          : null,
      },
      contract_errors: contractErrors,
    },
  };
}
