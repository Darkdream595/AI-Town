import type { LightingBand } from './environment';

export type EncounterAudioState = 'none' | 'tension' | 'combat';
export type AudioBus = 'music' | 'environment' | 'ui' | 'alert';

export interface AudioProjection {
  scene_id: string;
  weather_id: string;
  lighting_band: LightingBand;
  encounter: EncounterAudioState;
  muted: boolean;
}

export interface AudioTargetState {
  audio_state_id: string;
  scene_id: string;
  weather_id: string;
  lighting_band: LightingBand;
  encounter: EncounterAudioState;
  muted: boolean;
}

export interface AudioLayer {
  kind: 'music.base' | 'music.tension' | 'music.combat' | 'environment.weather';
  asset_id: string;
  bus: AudioBus;
}

export interface AudioTransition {
  kind: AudioLayer['kind'];
  from_asset_id: string | null;
  to_asset_id: string | null;
  started_at_ms: number;
  duration_ms: number;
}

export interface AudioInstance {
  asset_id: string;
  bus: AudioBus;
  priority: number;
}

export interface AudioPlayResult {
  status: 'played' | 'suppressed';
}

export interface AudioAssetRecord {
  asset_id: string;
  path: string;
  sha256: string;
  license_id: string;
}

export interface LicenseRecord {
  license_id: string;
  source: string;
  author: string;
  terms: string;
  acquired_at: string;
  license_text_path: string;
  license_text_sha256: string;
}

export function deriveAudioTargetState(projection: AudioProjection): AudioTargetState {
  const weatherName = projection.weather_id.replace(/^weather\./, '');
  return {
    audio_state_id: `audio_state.${projection.scene_id}.${projection.lighting_band}.${weatherName}.${projection.encounter}`,
    scene_id: projection.scene_id,
    weather_id: projection.weather_id,
    lighting_band: projection.lighting_band,
    encounter: projection.encounter,
    muted: projection.muted,
  };
}

function layersForState(state: AudioTargetState): AudioLayer[] {
  if (state.muted) {
    return [];
  }
  const layers: AudioLayer[] = [
    {
      kind: 'music.base',
      asset_id: `audio.music.${state.scene_id}.${state.lighting_band}.base`,
      bus: 'music',
    },
    {
      kind: 'environment.weather',
      asset_id: `audio.environment.${state.scene_id}.${state.weather_id}`,
      bus: 'environment',
    },
  ];
  if (state.encounter === 'tension' || state.encounter === 'combat') {
    layers.push({
      kind: 'music.tension',
      asset_id: `audio.music.${state.scene_id}.tension`,
      bus: 'music',
    });
  }
  if (state.encounter === 'combat') {
    layers.push({
      kind: 'music.combat',
      asset_id: `audio.music.${state.scene_id}.combat`,
      bus: 'music',
    });
  }
  return layers;
}

export class AudioStateController {
  readonly crossfadeDurationMs = 500;
  private readonly transitionQueue: AudioTransition[] = [];
  private readonly layers = new Map<AudioLayer['kind'], AudioLayer>();
  private readonly instances = new Map<AudioBus, AudioInstance[]>();
  private readonly transitionCapacity: number;
  private autoplayBlocked: boolean;
  private promptPending = false;
  private promptAlreadyShown = false;
  targetState: AudioTargetState | null = null;

  constructor(options: { autoplayBlocked?: boolean; transitionCapacity?: number } = {}) {
    this.autoplayBlocked = options.autoplayBlocked === true;
    this.transitionCapacity = Math.max(1, Math.floor(options.transitionCapacity ?? 256));
  }

  get activeLayers(): AudioLayer[] {
    return [...this.layers.values()];
  }

  get transitions(): AudioTransition[] {
    return [...this.transitionQueue];
  }

  applyProjection(projection: AudioProjection, nowMs: number): AudioTargetState {
    const targetState = deriveAudioTargetState(projection);
    this.targetState = targetState;
    if (this.autoplayBlocked) {
      this.instances.clear();
      if (!this.promptAlreadyShown) {
        this.promptPending = true;
      }
      return targetState;
    }
    if (targetState.muted) {
      this.instances.clear();
    }
    this.applyTargetLayers(targetState, nowMs);
    return targetState;
  }

  playOneShot(instance: AudioInstance): AudioPlayResult {
    if (this.autoplayBlocked || this.targetState?.muted === true) {
      return { status: 'suppressed' };
    }
    const busInstances = this.instances.get(instance.bus) ?? [];
    busInstances.push(instance);
    busInstances.sort((left, right) => left.priority - right.priority);
    this.instances.set(instance.bus, busInstances);
    this.enforceBusCapacity(instance.bus);
    return { status: 'played' };
  }

  getBusInstances(bus: AudioBus): AudioInstance[] {
    return [...(this.instances.get(bus) ?? [])];
  }

  consumeEnableAudioPrompt(): boolean {
    const shouldShow = this.promptPending;
    this.promptPending = false;
    if (shouldShow) {
      this.promptAlreadyShown = true;
    }
    return shouldShow;
  }

  consumeTransitions(): AudioTransition[] {
    return this.transitionQueue.splice(0);
  }

  setAutoplayBlocked(blocked: boolean): void {
    this.autoplayBlocked = blocked;
    if (blocked) {
      this.instances.clear();
      this.layers.clear();
      if (!this.promptAlreadyShown) {
        this.promptPending = true;
      }
    }
  }

  resumeAfterUserGesture(nowMs: number): void {
    this.setAutoplayBlocked(false);
    if (this.targetState) {
      this.applyTargetLayers(this.targetState, nowMs);
    }
  }

  private applyTargetLayers(state: AudioTargetState, nowMs: number): void {
    const targetLayers = new Map(layersForState(state).map((layer) => [layer.kind, layer]));
    const kinds = new Set([...this.layers.keys(), ...targetLayers.keys()]);
    for (const kind of kinds) {
      const previous = this.layers.get(kind);
      const next = targetLayers.get(kind);
      if (previous?.asset_id === next?.asset_id) {
        continue;
      }
      this.transitionQueue.push({
        kind,
        from_asset_id: previous?.asset_id ?? null,
        to_asset_id: next?.asset_id ?? null,
        started_at_ms: nowMs,
        duration_ms: this.crossfadeDurationMs,
      });
      while (this.transitionQueue.length > this.transitionCapacity) {
        this.transitionQueue.shift();
      }
      if (next) {
        this.layers.set(kind, next);
      } else {
        this.layers.delete(kind);
      }
    }
    for (const bus of new Set([
      ...this.instances.keys(),
      ...[...this.layers.values()].map((layer) => layer.bus),
    ])) {
      this.enforceBusCapacity(bus);
    }
  }

  private enforceBusCapacity(bus: AudioBus): void {
    const busInstances = this.instances.get(bus);
    if (!busInstances) {
      return;
    }
    const activeLayerCount = [...this.layers.values()].filter(
      (layer) => layer.bus === bus,
    ).length;
    const oneShotCapacity = Math.max(0, 8 - activeLayerCount);
    while (busInstances.length > oneShotCapacity) {
      busInstances.shift();
    }
  }
}

export function validateAudioLicenseChain(
  asset: AudioAssetRecord,
  license: LicenseRecord | undefined,
  fileHashes: Readonly<Record<string, string>>,
): { valid: boolean; diagnostics: string[] } {
  const diagnostics: string[] = [];
  if (
    !license ||
    asset.license_id.trim().length === 0 ||
    license.license_id.trim().length === 0 ||
    asset.license_id !== license.license_id
  ) {
    diagnostics.push('RENDER_LICENSE_ID_MISMATCH');
  }
  if (
    !license ||
    [
      license.source,
      license.author,
      license.terms,
      license.acquired_at,
      license.license_text_path,
      license.license_text_sha256,
    ].some((value) => value.trim().length === 0)
  ) {
    diagnostics.push('RENDER_LICENSE_METADATA_INCOMPLETE');
  }
  if (
    asset.path.trim().length === 0 ||
    asset.sha256.trim().length === 0 ||
    fileHashes[asset.path] !== asset.sha256
  ) {
    diagnostics.push('RENDER_LICENSE_ASSET_HASH_MISMATCH');
  }
  if (
    !license ||
    license.license_text_path.trim().length === 0 ||
    license.license_text_sha256.trim().length === 0 ||
    fileHashes[license.license_text_path] !== license.license_text_sha256
  ) {
    diagnostics.push('RENDER_LICENSE_TEXT_HASH_MISMATCH');
  }
  return { valid: diagnostics.length === 0, diagnostics };
}
