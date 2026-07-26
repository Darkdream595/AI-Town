/**
 * 渲染系统集成测试
 *
 * 测试 EventBus 通信与 Snapshot/Event 契约的协同
 */

import { describe, it, expect } from 'vitest';
import { EventBus, Events } from '../EventBus';
import type { RenderFrameInput, RenderEventEnvelope } from '../../types/rendering';

const SCENE_ID = 'region.crown_creek_town';
const WORLD_ID = '01K1AB2CD3EF4GH5JK6MNP7QRS';

function makeSnapshot(revision: number): RenderFrameInput {
  return {
    protocol_version: 'render.v1',
    snapshot_id: '01K1AB2CD3EF4GH5JK6MNP7QRT',
    snapshot_content_sha256:
      '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e26f3ea47c190a9b18aab45',
    world_id: WORLD_ID,
    scene_id: SCENE_ID,
    revision,
    game_time: 1830,
    camera_target: { scene_id: SCENE_ID, x_wu: 1024, y_wu: 768 },
    entities: [
      {
        entity_id: '01K1AB2CD3EF4GH5JK6MNP7QRV',
        asset_id: 'sprite.resident.apothecary',
        world_point: { scene_id: SCENE_ID, x_wu: 1008, y_wu: 752 },
        facing_degrees: 90,
        desired_animation_state: {
          animation_id: 'anim.resident.walk_south',
          state: 'walk',
          loop: true,
          since_revision: revision,
        },
      },
    ],
  };
}

function makeMoveEvent(revision: number, index = 0, count = 1): RenderEventEnvelope {
  return {
    protocol_version: 'render.v1',
    event_id: `01K1AB2CD3EF4GH5JK6MNP7QR${index}`,
    world_id: WORLD_ID,
    scene_id: SCENE_ID,
    revision,
    game_time: 1831,
    causation_id: '01K1AB2CD3EF4GH5JK6MNP7QRX',
    correlation_id: '01K1AB2CD3EF4GH5JK6MNP7QRY',
    transaction_event_index: index,
    transaction_event_count: count,
    render: {
      kind: 'entity_moved',
      entity_id: '01K1AB2CD3EF4GH5JK6MNP7QRV',
      world_point: { scene_id: SCENE_ID, x_wu: 1016, y_wu: 752 },
      facing_degrees: 90,
    },
  };
}

describe('渲染系统集成', () => {
  describe('EventBus', () => {
    it('应该正确发送和接收事件', () => {
      let received = false;
      const handler = () => {
        received = true;
      };

      EventBus.on(Events.RENDER_FRAME_UPDATE, handler);
      EventBus.emit(Events.RENDER_FRAME_UPDATE);
      EventBus.off(Events.RENDER_FRAME_UPDATE, handler);

      expect(received).toBe(true);
    });

    it('应该支持事件数据传递', () => {
      let receivedData: unknown = null;
      const handler = (data: unknown) => {
        receivedData = data;
      };

      const snapshot = makeSnapshot(42);
      EventBus.on(Events.RENDER_FRAME_UPDATE, handler);
      EventBus.emit(Events.RENDER_FRAME_UPDATE, snapshot);
      EventBus.off(Events.RENDER_FRAME_UPDATE, handler);

      expect(receivedData).toEqual(snapshot);
    });

    it('应该支持多个监听器', () => {
      let count = 0;
      const handlers = [() => count++, () => count++, () => count++];

      handlers.forEach(h => EventBus.on(Events.DEBUG_TOGGLE, h));
      EventBus.emit(Events.DEBUG_TOGGLE);
      handlers.forEach(h => EventBus.off(Events.DEBUG_TOGGLE, h));

      expect(count).toBe(3);
    });

    it('off 之后不应再收到事件', () => {
      let count = 0;
      const handler = () => count++;

      EventBus.on(Events.HUD_UPDATE, handler);
      EventBus.emit(Events.HUD_UPDATE);
      EventBus.off(Events.HUD_UPDATE, handler);
      EventBus.emit(Events.HUD_UPDATE);

      expect(count).toBe(1);
    });

    it('重复注册同一 handler 只应触发一次', () => {
      // 基于 Set 存储，避免 Scene 重启时重复监听导致的多次响应
      let count = 0;
      const handler = () => count++;

      EventBus.on(Events.HUD_UPDATE, handler);
      EventBus.on(Events.HUD_UPDATE, handler);
      EventBus.emit(Events.HUD_UPDATE);
      EventBus.off(Events.HUD_UPDATE, handler);

      expect(count).toBe(1);
    });

    it('emit 未注册的事件不应抛错', () => {
      expect(() => EventBus.emit('never:registered:event')).not.toThrow();
    });
  });

  describe('Snapshot 契约', () => {
    it('camera_target 与 entity 的 scene_id 必须等于 envelope 的 scene_id', () => {
      // RULE-RENDER-003
      const snapshot = makeSnapshot(42);

      expect(snapshot.camera_target.scene_id).toBe(snapshot.scene_id);
      for (const entity of snapshot.entities) {
        expect(entity.world_point.scene_id).toBe(snapshot.scene_id);
      }
    });

    it('坐标必须是有限数值', () => {
      // DES-RENDER-001: 数字必须有限
      const snapshot = makeSnapshot(42);

      for (const entity of snapshot.entities) {
        expect(Number.isFinite(entity.world_point.x_wu)).toBe(true);
        expect(Number.isFinite(entity.world_point.y_wu)).toBe(true);
      }
    });
  });

  describe('Event 排序与 Revision 连续性', () => {
    it('同一 Revision 的事件应按 transaction_event_index 排序', () => {
      const events = [makeMoveEvent(43, 2, 3), makeMoveEvent(43, 0, 3), makeMoveEvent(43, 1, 3)];

      events.sort((a, b) => {
        if (a.revision !== b.revision) {
          return a.revision - b.revision;
        }
        if (a.transaction_event_index !== b.transaction_event_index) {
          return a.transaction_event_index - b.transaction_event_index;
        }
        return a.event_id.localeCompare(b.event_id);
      });

      expect(events.map(e => e.transaction_event_index)).toEqual([0, 1, 2]);
    });

    it('应该识别事务事件不完整的情况', () => {
      // 收齐同一 Revision 的全部 event 后才可原子应用
      const partial = [makeMoveEvent(43, 0, 3), makeMoveEvent(43, 1, 3)];
      const expectedCount = partial[0].transaction_event_count;

      expect(partial.length).toBeLessThan(expectedCount);
    });

    it('应该丢弃 revision 不大于当前 Snapshot 的事件', () => {
      const snapshotRevision = 43;
      const incoming = [makeMoveEvent(42), makeMoveEvent(43), makeMoveEvent(44)];

      const applicable = incoming.filter(e => e.revision > snapshotRevision);

      expect(applicable).toHaveLength(1);
      expect(applicable[0].revision).toBe(44);
    });
  });

  describe('场景生命周期', () => {
    it('应该处理场景加载流程', () => {
      const loadEvents: string[] = [];
      const startHandler = () => loadEvents.push('start');
      const completeHandler = () => loadEvents.push('complete');

      EventBus.on(Events.SCENE_LOAD_START, startHandler);
      EventBus.on(Events.SCENE_LOAD_COMPLETE, completeHandler);

      EventBus.emit(Events.SCENE_LOAD_START, { scene_id: SCENE_ID });
      EventBus.emit(Events.SCENE_LOAD_COMPLETE, { scene_id: SCENE_ID });

      EventBus.off(Events.SCENE_LOAD_START, startHandler);
      EventBus.off(Events.SCENE_LOAD_COMPLETE, completeHandler);

      expect(loadEvents).toEqual(['start', 'complete']);
    });

    it('应该处理场景卸载', () => {
      let unloaded = false;
      const handler = () => {
        unloaded = true;
      };

      EventBus.on(Events.SCENE_UNLOAD, handler);
      EventBus.emit(Events.SCENE_UNLOAD, { scene_id: 'region.old_town' });
      EventBus.off(Events.SCENE_UNLOAD, handler);

      expect(unloaded).toBe(true);
    });
  });
});
