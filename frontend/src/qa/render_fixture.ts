import { EventBus } from '../core/EventBus';
import type { RenderFrameInput } from '../types/rendering';
import type { UiRenderProjection } from '../types/ui_projection';

export const QA_RENDER_FIXTURE_ID = 'qa.render.crown_creek_stress_v1';

export const QA_RENDER_CAPABILITIES = Object.freeze({
  ground_map: true,
  resident_sprites: true,
  resident_hud: true,
  heavy_rain: false,
  vfx: false,
  overlay: false,
});

const QA_EVENT_LOG = Object.freeze([
  { revision: 17, event: 'snapshot_applied', entity_count: 12 },
  { revision: 17, event: 'world_scene_ready' },
  { revision: 17, event: 'ui_scene_ready' },
]);

const QA_EVENT_LOG_SHA256 =
  '3a97e9214ad8c80ce85180e46cb60e451d0ea51b840201a8ef1f36eaf60bfae6';

const CHARACTER_ASSET_IDS = [
  'sprite.resident.human_farmer',
  'sprite.resident.elf_mage',
  'sprite.resident.dwarf_blacksmith',
  'sprite.resident.halfling_merchant',
] as const;

export interface QaRenderFixture {
  fixture_id: typeof QA_RENDER_FIXTURE_ID;
  snapshot: RenderFrameInput;
  ui: UiRenderProjection;
  event_log: typeof QA_EVENT_LOG;
  event_log_sha256: string;
  capabilities: typeof QA_RENDER_CAPABILITIES;
}

export function requestedQaFixtureId(search: string): string | null {
  const requestedFixture = new URLSearchParams(search).get('qa');
  return requestedFixture === QA_RENDER_FIXTURE_ID
    ? QA_RENDER_FIXTURE_ID
    : null;
}

export function createQaRenderFixture(): QaRenderFixture {
  const entities = Array.from({ length: 12 }, (_, index) => {
    const column = index % 4;
    const row = Math.floor(index / 4);
    const direction = ([0, 90, 180, 270] as const)[column];
    const characterAssetId =
      CHARACTER_ASSET_IDS[index % CHARACTER_ASSET_IDS.length];
    return {
      entity_id: `qa.resident.${String(index + 1).padStart(2, '0')}`,
      asset_id: characterAssetId,
      world_point: {
        scene_id: 'scene.crown_creek_town',
        x_wu: 270 + column * 150,
        y_wu: 310 + row * 150,
      },
      facing_degrees: direction,
      desired_animation_state: {
        animation_id: `anim.resident.${index % 3 === 0 ? 'walk' : 'idle'}_south`,
        state: index % 3 === 0 ? ('walk' as const) : ('idle' as const),
        loop: true,
        since_revision: 17,
      },
    };
  });

  return {
    fixture_id: QA_RENDER_FIXTURE_ID,
    snapshot: {
      protocol_version: 'render.v1',
      snapshot_id: QA_RENDER_FIXTURE_ID,
      snapshot_content_sha256:
        'e6903c61a88753f7f4657506e750a231effaf81ceac902b124de397a54248285',
      world_id: 'world.qa.crown_creek',
      scene_id: 'scene.crown_creek_town',
      revision: 17,
      game_time: 540,
      camera_target: {
        scene_id: 'scene.crown_creek_town',
        x_wu: 512,
        y_wu: 512,
      },
      entities,
    },
    ui: {
      protocol_version: 'ui.v1',
      world_id: 'world.qa.crown_creek',
      revision: 17,
      game_time: 540,
      hud: {
        player_name: 'Crown Creek · 12 residents',
        season: 'Summer',
        weather: 'Clear',
        time_display: 'Day 1 · 09:00',
      },
    },
    event_log: QA_EVENT_LOG,
    event_log_sha256: QA_EVENT_LOG_SHA256,
    capabilities: QA_RENDER_CAPABILITIES,
  };
}

export function installQaFixtureCoordinator(search: string): () => void {
  if (requestedQaFixtureId(search) === null) {
    return () => undefined;
  }

  let worldReady = false;
  let uiReady = false;
  let injected = false;
  const fixture = createQaRenderFixture();

  const injectWhenReady = (): void => {
    if (injected || !worldReady || !uiReady) {
      return;
    }
    injected = true;
    EventBus.emit('render:frame:update', fixture.snapshot);
    EventBus.emit('ui:update', fixture.ui);
    EventBus.emit('qa:runtime-metadata', {
      fixture_id: fixture.fixture_id,
      entity_count: fixture.snapshot.entities.length,
      scene_id: fixture.snapshot.scene_id,
      revision: fixture.snapshot.revision,
      camera: {
        x_wu: fixture.snapshot.camera_target.x_wu,
        y_wu: fixture.snapshot.camera_target.y_wu,
        zoom: 1,
      },
      capabilities: fixture.capabilities,
      event_log: fixture.event_log,
      event_log_sha256: fixture.event_log_sha256,
    });
  };
  const handleWorldReady = (): void => {
    worldReady = true;
    injectWhenReady();
  };
  const handleUiReady = (): void => {
    uiReady = true;
    injectWhenReady();
  };

  EventBus.on('world-scene-ready', handleWorldReady);
  EventBus.on('ui-scene-ready', handleUiReady);

  return () => {
    EventBus.off('world-scene-ready', handleWorldReady);
    EventBus.off('ui-scene-ready', handleUiReady);
  };
}
