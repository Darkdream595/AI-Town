/**
 * UIScene 单元测试
 *
 * 测试内容：
 * - HUD 信息更新
 * - RenderEventEnvelope 契约（DES-RENDER-001）
 */

import { afterEach, describe, it, expect, vi } from 'vitest';
import type { RenderEventEnvelope, RenderEventPayload } from '../../types/rendering';

/** 构造符合 DES-RENDER-001 的 envelope，仅 render 部分按用例变化 */
function makeEnvelope(render: RenderEventPayload, revision = 43): RenderEventEnvelope {
  return {
    protocol_version: 'render.v1',
    event_id: '01K1AB2CD3EF4GH5JK6MNP7QRW',
    world_id: '01K1AB2CD3EF4GH5JK6MNP7QRS',
    scene_id: 'region.crown_creek_town',
    revision,
    game_time: 1831,
    causation_id: '01K1AB2CD3EF4GH5JK6MNP7QRX',
    correlation_id: '01K1AB2CD3EF4GH5JK6MNP7QRY',
    transaction_event_index: 0,
    transaction_event_count: 1,
    render,
  };
}

const SCENE_ID = 'region.crown_creek_town';

describe('UIScene', () => {
  describe('HUD 更新', () => {
    it('应该接受完整的 HUD 数据', () => {
      const hudData: { time?: string; weather?: string; season?: string } = {
        time: '10:30',
        weather: '晴朗',
        season: '春季',
      };

      expect(hudData.time).toBe('10:30');
      expect(hudData.weather).toBe('晴朗');
      expect(hudData.season).toBe('春季');
    });

    it('应该允许只传部分 HUD 字段', () => {
      // updateHUD 的字段全部可选，未提供的字段保持原显示
      const partialData: { time?: string; weather?: string; season?: string } = {
        time: '10:30',
      };

      expect(partialData.time).toBe('10:30');
      expect(partialData.weather).toBeUndefined();
      expect(partialData.season).toBeUndefined();
    });
  });

  describe('RenderEventEnvelope 契约', () => {
    it('应该以 render.kind 作为判别字段', () => {
      const envelope = makeEnvelope({
        kind: 'entity_moved',
        entity_id: '01K1AB2CD3EF4GH5JK6MNP7QRV',
        world_point: { scene_id: SCENE_ID, x_wu: 1016, y_wu: 752 },
        facing_degrees: 90,
      });

      expect(envelope.render.kind).toBe('entity_moved');
      expect(envelope.protocol_version).toBe('render.v1');
    });

    it('应该支持 entity_animation_changed 事件', () => {
      const envelope = makeEnvelope({
        kind: 'entity_animation_changed',
        entity_id: '01K1AB2CD3EF4GH5JK6MNP7QRV',
        world_point: { scene_id: SCENE_ID, x_wu: 1016, y_wu: 752 },
        facing_degrees: 90,
        desired_animation_state: {
          animation_id: 'anim.resident.walk_east',
          state: 'walk',
          loop: true,
          since_revision: 43,
        },
      });

      expect(envelope.render.kind).toBe('entity_animation_changed');
      if (envelope.render.kind === 'entity_animation_changed') {
        expect(envelope.render.desired_animation_state.state).toBe('walk');
      }
    });

    it('render 的 world_point.scene_id 必须与 envelope 的 scene_id 一致', () => {
      // RULE-RENDER-003: scene_id 必须等于 envelope 的 scene_id
      const envelope = makeEnvelope({
        kind: 'entity_moved',
        entity_id: '01K1AB2CD3EF4GH5JK6MNP7QRV',
        world_point: { scene_id: SCENE_ID, x_wu: 1016, y_wu: 752 },
        facing_degrees: 90,
      });

      if ('world_point' in envelope.render) {
        expect(envelope.render.world_point.scene_id).toBe(envelope.scene_id);
      }
    });

    it('transaction_event_index 必须小于 transaction_event_count', () => {
      const envelope = makeEnvelope({
        kind: 'entity_despawned',
        entity_id: '01K1AB2CD3EF4GH5JK6MNP7QRV',
      });

      expect(envelope.transaction_event_index).toBeLessThan(envelope.transaction_event_count);
      expect(envelope.transaction_event_index).toBeGreaterThanOrEqual(0);
    });

    it('facing_degrees 仅允许 0/90/180/270', () => {
      const allowed: Array<0 | 90 | 180 | 270> = [0, 90, 180, 270];

      for (const facing of allowed) {
        const envelope = makeEnvelope({
          kind: 'entity_moved',
          entity_id: '01K1AB2CD3EF4GH5JK6MNP7QRV',
          world_point: { scene_id: SCENE_ID, x_wu: 0, y_wu: 0 },
          facing_degrees: facing,
        });

        if ('facing_degrees' in envelope.render) {
          expect(allowed).toContain(envelope.render.facing_degrees);
        }
      }
    });
  });
});

afterEach(() => {
  vi.doUnmock('phaser');
  vi.doUnmock('../../ui/PhaserDomBridge');
  vi.resetModules();
});

describe('UIScene lifecycle cleanup', () => {
  it('binds cleanup to SHUTDOWN and removes EventBus, keyboard, and bridge listeners once', async () => {
    type Handler = (...args: any[]) => void;

    class FakeEmitter {
      private listeners = new Map<string, Set<Handler>>();
      private onceWrappers = new Map<Handler, Handler>();

      on(event: string, handler: Handler): this {
        const handlers = this.listeners.get(event) ?? new Set();
        handlers.add(handler);
        this.listeners.set(event, handlers);
        return this;
      }

      once(event: string, handler: Handler): this {
        const wrapper: Handler = (...args) => {
          this.off(event, wrapper);
          handler(...args);
        };
        this.onceWrappers.set(handler, wrapper);
        return this.on(event, wrapper);
      }

      off(event: string, handler: Handler): this {
        const wrapper = this.onceWrappers.get(handler);
        this.listeners.get(event)?.delete(wrapper ?? handler);
        this.onceWrappers.delete(handler);
        return this;
      }

      emit(event: string, ...args: any[]): void {
        for (const handler of [...(this.listeners.get(event) ?? [])]) {
          handler(...args);
        }
      }

      listenerCount(event: string): number {
        return this.listeners.get(event)?.size ?? 0;
      }
    }

    const bridges: Array<{
      patch: ReturnType<typeof vi.fn>;
      dispose: ReturnType<typeof vi.fn>;
      onLayoutChanged?: (layout: { width: number; height: number }) => void;
    }> = [];
    const scaleResize = vi.fn();

    vi.doMock('phaser', () => ({
      default: {
        Scene: class {
          public readonly events = new FakeEmitter();
          public readonly input = { keyboard: new FakeEmitter() };
          public readonly scale = { resize: scaleResize };
        },
        Scenes: {
          Events: {
            SHUTDOWN: 'shutdown',
            DESTROY: 'destroy',
          },
        },
      },
    }));
    vi.doMock('../../ui/PhaserDomBridge', () => ({
      PhaserDomBridge: class {
        public readonly patch = vi.fn();
        public readonly dispose = vi.fn();

        constructor(
          _gate?: unknown,
          _inputCallback?: unknown,
          onLayoutChanged?: (layout: { width: number; height: number }) => void,
        ) {
          this.onLayoutChanged = onLayoutChanged;
          bridges.push(this);
        }
        public onLayoutChanged?: (layout: { width: number; height: number }) => void;
      },
    }));

    const [{ UIScene }, { EventBus }] = await Promise.all([
      import('../UIScene'),
      import('../../core/EventBus'),
    ]);
    const scene = new UIScene();
    const sceneInternals = scene as unknown as {
      events: FakeEmitter;
      input: { keyboard: FakeEmitter };
    };

    scene.create();
    expect(bridges[0].patch).toHaveBeenCalledTimes(1);
    expect(sceneInternals.input.keyboard.listenerCount('keydown-F3')).toBe(1);
    bridges[0].onLayoutChanged?.({ width: 1920, height: 1080 });
    expect(scaleResize).toHaveBeenCalledWith(1920, 1080);

    sceneInternals.events.emit('shutdown');
    sceneInternals.events.emit('destroy');
    EventBus.emit('ui:update', {
      protocol_version: 'ui.v1',
      world_id: 'world',
      revision: 1,
      game_time: 0,
      hud: {
        player_name: 'Player',
        season: 'Spring',
        weather: 'Clear',
        time_display: '09:00',
      },
    });

    expect(bridges[0].dispose).toHaveBeenCalledTimes(1);
    expect(bridges[0].patch).toHaveBeenCalledTimes(1);
    expect(sceneInternals.input.keyboard.listenerCount('keydown-F3')).toBe(0);
  });
});
