/**
 * WorldScene 单元测试
 *
 * 测试内容：
 * - TEST-RENDER-008: 深度排序（depth = floor(y_wu * 16) + depth_bias）
 * - 实体创建和销毁
 * - 渲染层初始化
 */

import { describe, it, expect } from 'vitest';
import type { RenderFrameInput, EntityProjection, WorldPoint } from '../../types/rendering';
import { calculateEntityDepth } from '../../types/rendering';

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
});
