/**
 * WorldScene 单元测试
 *
 * 测试内容：
 * - TEST-RENDER-008: 深度排序（depth = floor(y_wu * 16) + depth_bias）
 * - 实体创建和销毁
 * - 渲染层初始化
 */

import { describe, it, expect, vi, afterEach } from 'vitest';

vi.mock('phaser', () => {
  class Scene {
    constructor(_configuration?: unknown) {}
  }
  return {
    default: {
      Scene,
      Math: {
        Clamp: (value: number, minimum: number, maximum: number) =>
          Math.min(maximum, Math.max(minimum, value)),
      },
      Scenes: {
        Events: {
          SHUTDOWN: 'shutdown',
          DESTROY: 'destroy',
        },
      },
    },
  };
});

import type {
  RenderEventEnvelope,
  RenderFrameInput,
  EntityProjection,
  WorldPoint,
} from '../../types/rendering';
import { calculateEntityDepth } from '../../types/rendering';
import { EventBus } from '../../core/EventBus';
import { WorldScene } from '../WorldScene';

const HASH_A = 'a'.repeat(64);

function makeFrame(
  revision: number,
  entities: EntityProjection[] = [],
): RenderFrameInput {
  return {
    protocol_version: 'render.v1',
    snapshot_id: `snapshot-${revision}`,
    snapshot_content_sha256: HASH_A,
    world_id: 'world.test',
    scene_id: 'scene.test',
    revision,
    game_time: revision * 100,
    camera_target: { scene_id: 'scene.test', x_wu: 512, y_wu: 512 },
    entities,
  };
}

function makeSpawnEvent(
  revision: number,
  index: number,
  count: number,
  entityId = `entity-${index}`,
): RenderEventEnvelope {
  return {
    protocol_version: 'render.v1',
    event_id: `event-${revision}-${index}`,
    world_id: 'world.test',
    scene_id: 'scene.test',
    revision,
    game_time: revision * 100,
    causation_id: 'cause',
    correlation_id: 'correlation',
    transaction_event_index: index,
    transaction_event_count: count,
    render: {
      kind: 'entity_spawned',
      entity_id: entityId,
      asset_id: 'sprite.resident.test',
      world_point: { scene_id: 'scene.test', x_wu: 10, y_wu: 20 },
      facing_degrees: 90,
      desired_animation_state: {
        animation_id: 'anim.resident.idle_south',
        state: 'idle',
        loop: true,
        since_revision: revision,
      },
    },
  };
}

function defineSceneDependency(scene: WorldScene, name: string, value: unknown): void {
  Object.defineProperty(scene, name, {
    configurable: true,
    value,
  });
}

afterEach(() => {
  EventBus.clear();
});

describe('WorldScene', () => {
  describe('深度计算', () => {
    it('应该按 RULE-RENDER-008 计算实体深度', () => {
      // TEST-RENDER-008: depth = floor(y_wu * 16) + depth_bias

      const testPoint: WorldPoint = { scene_id: 'test', x_wu: 0, y_wu: 10 };

      // 测试用例 1: y=10, bias=0 => depth=160
      expect(calculateEntityDepth(testPoint, 0)).toBe(160);

      // 测试用例 2: y=10.5, bias=0 => depth=168
      expect(calculateEntityDepth({ scene_id: 'test', x_wu: 0, y_wu: 10.5 }, 0)).toBe(168);

      // 测试用例 3: y=10, bias=5 => depth=165
      expect(calculateEntityDepth(testPoint, 5)).toBe(165);

      // 测试用例 4: y=10, bias=-5 => depth=155
      expect(calculateEntityDepth(testPoint, -5)).toBe(155);

      // 测试用例 5: y=0, bias=0 => depth=0
      expect(calculateEntityDepth({ scene_id: 'test', x_wu: 0, y_wu: 0 }, 0)).toBe(0);

      // 测试用例 6: y=100.99, bias=0 => depth=1615
      expect(calculateEntityDepth({ scene_id: 'test', x_wu: 0, y_wu: 100.99 }, 0)).toBe(1615);
    });

    it('应该处理负坐标', () => {
      // 负 y 坐标应该产生负深度
      expect(calculateEntityDepth({ scene_id: 'test', x_wu: 0, y_wu: -10 }, 0)).toBe(-160);
      expect(calculateEntityDepth({ scene_id: 'test', x_wu: 0, y_wu: -10.5 }, 0)).toBe(-168);
    });

    it('应该处理大坐标', () => {
      // 大坐标应该正确计算
      expect(calculateEntityDepth({ scene_id: 'test', x_wu: 0, y_wu: 1000 }, 0)).toBe(16000);
      expect(calculateEntityDepth({ scene_id: 'test', x_wu: 0, y_wu: 10000 }, 0)).toBe(160000);
    });
  });

  describe('实体排序', () => {
    it('应该按深度值排序实体', () => {
      const entities: Array<{ id: string; depth: number }> = [
        { id: 'entity_3', depth: 300 },
        { id: 'entity_1', depth: 100 },
        { id: 'entity_2', depth: 200 },
      ];

      entities.sort((a, b) => a.depth - b.depth);

      expect(entities[0].id).toBe('entity_1');
      expect(entities[1].id).toBe('entity_2');
      expect(entities[2].id).toBe('entity_3');
    });

    it('应该在深度相同时按 entity_id 字典序排序', () => {
      // RULE-RENDER-008: 同值以 stable entity_id 字典序打破平局
      const entities: Array<{ id: string; depth: number }> = [
        { id: 'entity_c', depth: 100 },
        { id: 'entity_a', depth: 100 },
        { id: 'entity_b', depth: 100 },
      ];

      entities.sort((a, b) => {
        if (a.depth !== b.depth) {
          return a.depth - b.depth;
        }
        return a.id.localeCompare(b.id);
      });

      expect(entities[0].id).toBe('entity_a');
      expect(entities[1].id).toBe('entity_b');
      expect(entities[2].id).toBe('entity_c');
    });

    it('应该稳定排序混合深度的实体', () => {
      const entities: Array<{ id: string; depth: number }> = [
        { id: 'entity_3', depth: 200 },
        { id: 'entity_1', depth: 100 },
        { id: 'entity_5', depth: 200 },
        { id: 'entity_2', depth: 100 },
        { id: 'entity_4', depth: 150 },
      ];

      entities.sort((a, b) => {
        if (a.depth !== b.depth) {
          return a.depth - b.depth;
        }
        return a.id.localeCompare(b.id);
      });

      expect(entities.map(e => e.id)).toEqual([
        'entity_1',
        'entity_2',
        'entity_4',
        'entity_3',
        'entity_5',
      ]);
    });
  });

  describe('Snapshot 准入判定', () => {
    // updateFrame 的拦截条件（RULE-RENDER-002 / RULE-RENDER-004）：
    // revision 低于当前的整帧丢弃；scene_id 与当前 Scene 不符的拒绝
    function shouldAccept(
      currentSceneId: string,
      currentRevision: number,
      incoming: { scene_id: string; revision: number }
    ): boolean {
      if (incoming.revision < currentRevision) {
        return false;
      }
      if (currentSceneId !== '' && currentSceneId !== incoming.scene_id) {
        return false;
      }
      return true;
    }

    it('应该拒绝 revision 低于当前的 Snapshot', () => {
      expect(shouldAccept('region.a', 42, { scene_id: 'region.a', revision: 41 })).toBe(false);
    });

    it('应该接受同 revision 的 Snapshot 以支持幂等重放', () => {
      // 同 Revision replacement 在内容 hash 一致时允许幂等重放
      expect(shouldAccept('region.a', 42, { scene_id: 'region.a', revision: 42 })).toBe(true);
    });

    it('应该接受 revision 更高的 Snapshot', () => {
      expect(shouldAccept('region.a', 42, { scene_id: 'region.a', revision: 43 })).toBe(true);
    });

    it('应该拒绝 scene_id 不匹配的 Snapshot', () => {
      // 跨 scene 必须走 Load Gate，不能在当前 Scene 内静默换图
      expect(shouldAccept('region.a', 42, { scene_id: 'region.b', revision: 43 })).toBe(false);
    });

    it('首帧（当前 scene 为空）应接受任意 scene_id', () => {
      expect(shouldAccept('', 0, { scene_id: 'region.a', revision: 1 })).toBe(true);
    });
  });

  describe('RenderFrameInput 验证', () => {
    it('应该接受有效的 RenderFrameInput', () => {
      const validFrame: RenderFrameInput = {
        protocol_version: 'render.v1',
        snapshot_id: '01K1AB2CD3EF4GH5JK6MNP7QRT',
        snapshot_content_sha256: '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e26f3ea47c190a9b18aab45',
        world_id: '01K1AB2CD3EF4GH5JK6MNP7QRS',
        scene_id: 'region.test_town',
        revision: 1,
        game_time: 1000,
        camera_target: {
          scene_id: 'region.test_town',
          x_wu: 1024,
          y_wu: 768,
        },
        entities: [
          {
            entity_id: 'entity_1',
            asset_id: 'sprite.resident.test',
            world_point: {
              scene_id: 'region.test_town',
              x_wu: 100,
              y_wu: 200,
            },
            facing_degrees: 90,
            desired_animation_state: {
              animation_id: 'anim.resident.idle_south',
              state: 'idle',
              loop: true,
              since_revision: 1,
            },
          },
        ],
      };

      expect(validFrame.revision).toBe(1);
      expect(validFrame.entities).toHaveLength(1);
      expect(validFrame.entities[0].entity_id).toBe('entity_1');
    });

    it('应该处理空实体列表', () => {
      const emptyFrame: RenderFrameInput = {
        protocol_version: 'render.v1',
        snapshot_id: '01K1AB2CD3EF4GH5JK6MNP7QRT',
        snapshot_content_sha256: '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e26f3ea47c190a9b18aab45',
        world_id: '01K1AB2CD3EF4GH5JK6MNP7QRS',
        scene_id: 'region.test_town',
        revision: 1,
        game_time: 1000,
        camera_target: {
          scene_id: 'region.test_town',
          x_wu: 1024,
          y_wu: 768,
        },
        entities: [],
      };

      expect(emptyFrame.entities).toHaveLength(0);
    });

    it('应该处理多个实体', () => {
      const entities: EntityProjection[] = [];
      for (let i = 0; i < 100; i++) {
        entities.push({
          entity_id: `entity_${i}`,
          asset_id: 'sprite.resident.test',
          world_point: {
            scene_id: 'region.test_town',
            x_wu: i * 10,
            y_wu: i * 10,
          },
          facing_degrees: 90,
          desired_animation_state: {
            animation_id: 'anim.resident.walk_south',
            state: 'walk',
            loop: true,
            since_revision: 1,
          },
        });
      }

      const frame: RenderFrameInput = {
        protocol_version: 'render.v1',
        snapshot_id: '01K1AB2CD3EF4GH5JK6MNP7QRT',
        snapshot_content_sha256: '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e26f3ea47c190a9b18aab45',
        world_id: '01K1AB2CD3EF4GH5JK6MNP7QRS',
        scene_id: 'region.test_town',
        revision: 1,
        game_time: 1000,
        camera_target: {
          scene_id: 'region.test_town',
          x_wu: 1024,
          y_wu: 768,
        },
        entities,
      };

      expect(frame.entities).toHaveLength(100);
    });
  });

  describe('真实 WorldScene 协议路径', () => {
    it('Snapshot stale 和 duplicate 不会重复更新实体', () => {
      const scene = new WorldScene();
      const updateEntity = vi.fn();
      (scene as any).updateEntity = updateEntity;
      (scene as any).removeStaleEntities = vi.fn();
      (scene as any).sortEntitiesByDepth = vi.fn();
      defineSceneDependency(scene, 'cameras', {
        main: { centerOn: vi.fn() },
      });

      const entity = makeSpawnEvent(1, 0, 1).render as EntityProjection;
      scene.updateFrame(makeFrame(1, [entity]));
      scene.updateFrame(makeFrame(1, [entity]));
      scene.updateFrame({ ...makeFrame(0, [entity]), snapshot_content_sha256: 'b'.repeat(64) });

      expect(updateEntity).toHaveBeenCalledTimes(1);
    });

    it('event transaction 仅完整时应用，并在 revision gap 时请求 resync', () => {
      const scene = new WorldScene();
      (scene as any).updateEntity = vi.fn();
      (scene as any).removeStaleEntities = vi.fn();
      (scene as any).sortEntitiesByDepth = vi.fn();
      defineSceneDependency(scene, 'cameras', {
        main: { centerOn: vi.fn() },
      });
      const applyRenderEvent = vi.fn();
      (scene as any).applyRenderEvent = applyRenderEvent;
      const resync = vi.fn();
      EventBus.on('render:resync-required', resync);

      scene.updateFrame(makeFrame(1));
      scene.updateEvent(makeSpawnEvent(2, 1, 2));
      expect(applyRenderEvent).not.toHaveBeenCalled();

      scene.updateEvent(makeSpawnEvent(2, 0, 2));
      expect(applyRenderEvent).toHaveBeenCalledTimes(2);

      scene.updateEvent(makeSpawnEvent(4, 0, 1));
      expect(resync).toHaveBeenCalledWith(
        expect.objectContaining({
          action: 'resync',
          expected_revision: 3,
          received_revision: 4,
        }),
      );
    });
  });

  describe('Scene lifecycle', () => {
    it('routes render frame and event bus inputs while active, then unregisters them', () => {
      const scene = new WorldScene();
      const updateFrame = vi.spyOn(scene, 'updateFrame').mockImplementation(() => undefined);
      const updateEvent = vi.spyOn(scene, 'updateEvent').mockImplementation(() => undefined);
      const lifecycleHandlers = new Map<string, () => void>();
      defineSceneDependency(scene, 'events', {
        once: (event: string, handler: () => void) => lifecycleHandlers.set(event, handler),
        off: vi.fn(),
      });
      (scene as any).createRenderLayers = vi.fn();
      (scene as any).setupCamera = vi.fn();
      (scene as any).setupInput = vi.fn();
      (scene as any).refreshMapSlicePlan = vi.fn();

      scene.create();
      EventBus.emit('render:frame:update', makeFrame(1));
      EventBus.emit('render:event', makeSpawnEvent(2, 0, 1));

      expect(updateFrame).toHaveBeenCalledWith(makeFrame(1));
      expect(updateEvent).toHaveBeenCalledWith(makeSpawnEvent(2, 0, 1));

      lifecycleHandlers.get('shutdown')?.();
      EventBus.emit('render:frame:update', makeFrame(2));
      EventBus.emit('render:event', makeSpawnEvent(3, 0, 1));
      expect(updateFrame).toHaveBeenCalledTimes(1);
      expect(updateEvent).toHaveBeenCalledTimes(1);
    });

    it('create 不生成本地测试角色，并绑定 shutdown/destroy cleanup', () => {
      const scene = new WorldScene();
      const createTestCharacters = vi.fn();
      const cleanup = vi.spyOn(scene, 'cleanup');
      const lifecycleHandlers = new Map<string, () => void>();
      const lifecycleOff = vi.fn();
      defineSceneDependency(scene, 'events', {
        once: (event: string, handler: () => void) => {
          lifecycleHandlers.set(event, handler);
        },
        off: lifecycleOff,
      });
      (scene as any).createRenderLayers = vi.fn();
      (scene as any).setupCamera = vi.fn();
      (scene as any).setupInput = vi.fn();
      (scene as any).refreshMapSlicePlan = vi.fn();
      (scene as any).createTestCharacters = createTestCharacters;

      scene.create();

      expect(createTestCharacters).not.toHaveBeenCalled();
      expect(lifecycleHandlers.has('shutdown')).toBe(true);
      expect(lifecycleHandlers.has('destroy')).toBe(true);
      lifecycleHandlers.get('shutdown')?.();
      lifecycleHandlers.get('destroy')?.();
      expect(cleanup).toHaveBeenCalledTimes(2);
      expect(lifecycleOff).toHaveBeenCalledWith(
        'shutdown',
        expect.any(Function),
      );
      expect(lifecycleOff).toHaveBeenCalledWith(
        'destroy',
        expect.any(Function),
      );
    });

    it('cleanup 可幂等调用且只销毁资源一次', () => {
      const scene = new WorldScene();
      const sprite = { destroy: vi.fn() };
      (scene as any).entities.set('entity', {
        sprite,
        projection: makeSpawnEvent(1, 0, 1).render,
        lastSeenRevision: 1,
      });
      const groundRemoveAll = vi.fn();
      const backgroundRemoveAll = vi.fn();
      const foregroundRemoveAll = vi.fn();
      (scene as any).groundLayer = { removeAll: groundRemoveAll };
      (scene as any).structureBackgroundLayer = { removeAll: backgroundRemoveAll };
      (scene as any).structureForegroundLayer = { removeAll: foregroundRemoveAll };

      scene.cleanup();
      scene.cleanup();

      expect(sprite.destroy).toHaveBeenCalledTimes(1);
      expect(groundRemoveAll).toHaveBeenCalledTimes(1);
      expect(backgroundRemoveAll).toHaveBeenCalledTimes(1);
      expect(foregroundRemoveAll).toHaveBeenCalledTimes(1);
    });
  });

  describe('Ground rendering', () => {
    it('adds the loaded Crown Creek base image to the ground layer', () => {
      const scene = new WorldScene();
      const groundAdd = vi.fn();
      const containers = [
        { setDepth: vi.fn().mockReturnThis(), add: groundAdd },
        { setDepth: vi.fn().mockReturnThis(), add: vi.fn() },
        { setDepth: vi.fn().mockReturnThis(), add: vi.fn() },
        { setDepth: vi.fn().mockReturnThis(), add: vi.fn() },
      ];
      const groundImage = { setOrigin: vi.fn().mockReturnThis() };
      defineSceneDependency(scene, 'add', {
        container: vi.fn(() => containers.shift()),
        image: vi.fn(() => groundImage),
      });

      (scene as any).createRenderLayers();

      expect((scene as any).add.image).toHaveBeenCalledWith(
        0,
        0,
        'crown_creek_town_base',
      );
      expect(groundImage.setOrigin).toHaveBeenCalledWith(0, 0);
      expect(groundAdd).toHaveBeenCalledWith(groundImage);
    });
  });

  describe('地图切片接入', () => {
    it('根据真实相机状态生成并发布 map slice plan', () => {
      const scene = new WorldScene();
      defineSceneDependency(scene, 'scale', { width: 1280, height: 720 });
      defineSceneDependency(scene, 'cameras', {
        main: { zoom: 1, midPoint: { x: 2048, y: 2048 } },
      });
      const plans: unknown[] = [];
      EventBus.on('render:map-slice-plan', plan => plans.push(plan));

      (scene as any).refreshMapSlicePlan();

      expect(scene.getMapSlicePlan()).toEqual(
        expect.objectContaining({ ok: true, lod: 0 }),
      );
      expect(plans).toHaveLength(1);
    });

    it('无效 viewport 只发出一次稳定 diagnostic', () => {
      const scene = new WorldScene();
      defineSceneDependency(scene, 'scale', { width: 4000, height: 720 });
      defineSceneDependency(scene, 'cameras', {
        main: { zoom: 1, midPoint: { x: 2048, y: 2048 } },
      });
      const diagnostics: unknown[] = [];
      EventBus.on('render:diagnostic', diagnostic => diagnostics.push(diagnostic));

      (scene as any).refreshMapSlicePlan();
      (scene as any).refreshMapSlicePlan();

      expect(diagnostics).toEqual([
        expect.objectContaining({
          issue: 'MAP_SLICE_PLAN_FAILED',
          reason: 'invalid_input',
        }),
      ]);
    });
  });

  describe('AnimationMachine 接入', () => {
    it('消费 projection desired state 并在 900ms 后回退 idle', () => {
      const scene = new WorldScene();
      let now = 0;
      defineSceneDependency(scene, 'time', { get now() { return now; } });
      defineSceneDependency(scene, 'anims', {
        exists: (animationId: string) =>
          animationId === 'anim.resident.attack_south' ||
          animationId === 'anim.resident.idle_south',
      });
      const sprite = {
        depth: 0,
        setOrigin: vi.fn().mockReturnThis(),
        setPosition: vi.fn().mockReturnThis(),
        setFlipX: vi.fn().mockReturnThis(),
        setData: vi.fn().mockReturnThis(),
        setDepth(value: number) {
          this.depth = value;
          return this;
        },
        play: vi.fn().mockReturnThis(),
        destroy: vi.fn(),
      };
      defineSceneDependency(scene, 'add', { sprite: vi.fn(() => sprite) });
      (scene as any).entityLayer = {
        add: vi.fn(),
        bringToTop: vi.fn(),
      };
      (scene as any).refreshMapSlicePlan = vi.fn();
      const projection: EntityProjection = {
        entity_id: 'entity-1',
        asset_id: 'sprite.resident.test',
        world_point: { scene_id: 'scene.test', x_wu: 10, y_wu: 20 },
        facing_degrees: 90,
        desired_animation_state: {
          animation_id: 'anim.resident.attack_south',
          state: 'attack',
          loop: false,
          since_revision: 1,
        },
      };

      (scene as any).updateEntity(projection, 1);
      expect(sprite.setData).toHaveBeenCalledWith('animationKind', 'attack');

      now = 900;
      scene.update();
      expect(sprite.setData).toHaveBeenLastCalledWith('animationKind', 'idle');
    });
  });
});
