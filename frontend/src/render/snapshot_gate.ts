/**
 * Snapshot 原子替换门（DOC-RENDER-001 RULE-RENDER-002、§6.3、§7）
 *
 * - 只消费 protocol/world/scene 匹配的 Snapshot
 * - 低于当前 Revision 的 replacement 拒绝
 * - 同 Revision：snapshot_id 相同为幂等重放；snapshot_id 不同但内容 hash
 *   一致也接受（幂等）；hash 不一致视为 contract error
 * - 更高 Revision：单帧原子替换，调用方负责清空插值/一次性 VFX 队列并
 *   删除所有 revision <= snapshot.revision 的待处理 event
 */

import type { RenderFrameInput } from '../types/rendering';
import { RENDER_PROTOCOL_VERSION, validateRenderFrameInput } from './protocol';

export type SnapshotDecision =
  | { action: 'apply'; revision: number }
  | { action: 'idempotent_replay'; revision: number }
  | { action: 'reject_stale'; current_revision: number }
  | { action: 'contract_error'; reason: string };

export class SnapshotGate {
  private currentRevision = -1;
  private currentSnapshotId: string | null = null;
  private currentContentHash: string | null = null;

  constructor(
    private readonly worldId: string,
    private readonly sceneId: string,
  ) {}

  get revision(): number {
    return this.currentRevision;
  }

  get snapshotId(): string | null {
    return this.currentSnapshotId;
  }

  /** 评估 Snapshot；apply/idempotent_replay 时同步内部状态 */
  evaluate(frame: RenderFrameInput): SnapshotDecision {
    const validation = validateRenderFrameInput(frame);
    if (!validation.ok) {
      return {
        action: 'contract_error',
        reason: validation.issues
          .map(issue => `${issue.pointer}:${issue.reason}`)
          .join(';'),
      };
    }
    if (frame.protocol_version !== RENDER_PROTOCOL_VERSION) {
      return { action: 'contract_error', reason: 'protocol_version_unsupported' };
    }
    if (frame.world_id !== this.worldId || frame.scene_id !== this.sceneId) {
      return { action: 'contract_error', reason: 'world_scene_mismatch' };
    }

    if (frame.revision < this.currentRevision) {
      // 过期 replacement 整帧拒绝，绝不部分应用
      return {
        action: 'reject_stale',
        current_revision: this.currentRevision,
      };
    }

    if (frame.revision === this.currentRevision) {
      const sameHash =
        frame.snapshot_content_sha256 === this.currentContentHash;
      if (sameHash) {
        // 同 Revision 只能重放同一内容；snapshot_id 不参与内容一致性判定
        return { action: 'idempotent_replay', revision: frame.revision };
      }
      // 同 Revision 内容 hash 不一致 = contract error
      return { action: 'contract_error', reason: 'content_hash_conflict' };
    }

    this.currentRevision = frame.revision;
    this.currentSnapshotId = frame.snapshot_id;
    this.currentContentHash = frame.snapshot_content_sha256;
    return { action: 'apply', revision: frame.revision };
  }

  /** 重连/恢复后重置（浏览器恢复先请求新 Snapshot） */
  reset(): void {
    this.currentRevision = -1;
    this.currentSnapshotId = null;
    this.currentContentHash = null;
  }
}
