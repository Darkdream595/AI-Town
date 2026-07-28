/**
 * render.v1 协议校验（DOC-RENDER-001 DES-RENDER-001）
 *
 * - 数字必须有限；坐标按 Foundation 量化到 1/16 wu
 * - facing_degrees 仅允许 0/90/180/270
 * - Snapshot/Event 的 protocol/world/scene 字段完整性校验
 */

export const RENDER_PROTOCOL_VERSION = 'render.v1';
export const WU_QUANTUM = 1 / 16;
export const SHA256_PATTERN = /^[a-f0-9]{64}$/;
export const VALID_FACINGS = [0, 90, 180, 270] as const;

export interface ValidationIssue {
  pointer: string;
  reason: string;
}

export interface ValidationResult {
  ok: boolean;
  issues: ValidationIssue[];
}

function result(issues: ValidationIssue[]): ValidationResult {
  return { ok: issues.length === 0, issues };
}

export function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

export function isNonNegativeInteger(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0;
}

export function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0;
}

/** 量化到 1/16 wu（DES-RENDER-001） */
export function quantizeWu(value: number): number {
  return Math.round(value / WU_QUANTUM) * WU_QUANTUM;
}

export function isValidFacing(value: unknown): value is 0 | 90 | 180 | 270 {
  return typeof value === 'number' &&
    (VALID_FACINGS as readonly number[]).includes(value);
}

export function validateWorldPoint(
  value: unknown,
  pointer: string,
  expectedSceneId?: string,
): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  if (typeof value !== 'object' || value === null) {
    return [{ pointer, reason: 'world_point_not_object' }];
  }
  const point = value as Record<string, unknown>;
  if (!isNonEmptyString(point.scene_id)) {
    issues.push({ pointer: `${pointer}/scene_id`, reason: 'scene_id_missing' });
  } else if (
    expectedSceneId !== undefined &&
    point.scene_id !== expectedSceneId
  ) {
    issues.push({
      pointer: `${pointer}/scene_id`,
      reason: 'scene_id_mismatch',
    });
  }
  if (!isFiniteNumber(point.x_wu)) {
    issues.push({ pointer: `${pointer}/x_wu`, reason: 'x_wu_not_finite' });
  }
  if (!isFiniteNumber(point.y_wu)) {
    issues.push({ pointer: `${pointer}/y_wu`, reason: 'y_wu_not_finite' });
  }
  return issues;
}

export function validateAnimationState(
  value: unknown,
  pointer: string,
): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  if (typeof value !== 'object' || value === null) {
    return [{ pointer, reason: 'animation_state_not_object' }];
  }
  const state = value as Record<string, unknown>;
  if (!isNonEmptyString(state.animation_id)) {
    issues.push({
      pointer: `${pointer}/animation_id`,
      reason: 'animation_id_missing',
    });
  }
  if (!isNonEmptyString(state.state)) {
    issues.push({ pointer: `${pointer}/state`, reason: 'state_missing' });
  }
  if (typeof state.loop !== 'boolean') {
    issues.push({ pointer: `${pointer}/loop`, reason: 'loop_not_boolean' });
  }
  if (!isNonNegativeInteger(state.since_revision)) {
    issues.push({
      pointer: `${pointer}/since_revision`,
      reason: 'since_revision_invalid',
    });
  }
  return issues;
}

function validateCommonEnvelope(
  value: Record<string, unknown>,
  issues: ValidationIssue[],
): void {
  if (value.protocol_version !== RENDER_PROTOCOL_VERSION) {
    issues.push({
      pointer: '/protocol_version',
      reason: 'protocol_version_unsupported',
    });
  }
  if (!isNonEmptyString(value.world_id)) {
    issues.push({ pointer: '/world_id', reason: 'world_id_missing' });
  }
  if (!isNonEmptyString(value.scene_id)) {
    issues.push({ pointer: '/scene_id', reason: 'scene_id_missing' });
  }
  if (!isNonNegativeInteger(value.revision)) {
    issues.push({ pointer: '/revision', reason: 'revision_invalid' });
  }
  if (!isFiniteNumber(value.game_time)) {
    issues.push({ pointer: '/game_time', reason: 'game_time_not_finite' });
  }
}

/** 完整 Snapshot replacement 校验（DES-RENDER-001） */
export function validateRenderFrameInput(value: unknown): ValidationResult {
  if (typeof value !== 'object' || value === null) {
    return result([{ pointer: '/', reason: 'snapshot_not_object' }]);
  }
  const frame = value as Record<string, unknown>;
  const issues: ValidationIssue[] = [];
  validateCommonEnvelope(frame, issues);
  if (!isNonEmptyString(frame.snapshot_id)) {
    issues.push({ pointer: '/snapshot_id', reason: 'snapshot_id_missing' });
  }
  if (
    typeof frame.snapshot_content_sha256 !== 'string' ||
    !SHA256_PATTERN.test(frame.snapshot_content_sha256)
  ) {
    issues.push({
      pointer: '/snapshot_content_sha256',
      reason: 'content_sha256_invalid',
    });
  }
  const sceneId = isNonEmptyString(frame.scene_id) ? frame.scene_id : undefined;
  issues.push(
    ...validateWorldPoint(frame.camera_target, '/camera_target', sceneId),
  );
  if (!Array.isArray(frame.entities)) {
    issues.push({ pointer: '/entities', reason: 'entities_not_array' });
  } else {
    frame.entities.forEach((entity, index) => {
      const pointer = `/entities/${index}`;
      if (typeof entity !== 'object' || entity === null) {
        issues.push({ pointer, reason: 'entity_not_object' });
        return;
      }
      const proj = entity as Record<string, unknown>;
      if (!isNonEmptyString(proj.entity_id)) {
        issues.push({ pointer: `${pointer}/entity_id`, reason: 'missing' });
      }
      if (!isNonEmptyString(proj.asset_id)) {
        issues.push({ pointer: `${pointer}/asset_id`, reason: 'missing' });
      }
      issues.push(
        ...validateWorldPoint(
          proj.world_point,
          `${pointer}/world_point`,
          sceneId,
        ),
      );
      if (!isValidFacing(proj.facing_degrees)) {
        issues.push({
          pointer: `${pointer}/facing_degrees`,
          reason: 'facing_invalid',
        });
      }
      issues.push(
        ...validateAnimationState(
          proj.desired_animation_state,
          `${pointer}/desired_animation_state`,
        ),
      );
    });
  }
  return result(issues);
}

/** 增量 RenderEventEnvelope 校验（DES-RENDER-001） */
export function validateRenderEventEnvelope(value: unknown): ValidationResult {
  if (typeof value !== 'object' || value === null) {
    return result([{ pointer: '/', reason: 'event_not_object' }]);
  }
  const envelope = value as Record<string, unknown>;
  const issues: ValidationIssue[] = [];
  validateCommonEnvelope(envelope, issues);
  if (!isNonEmptyString(envelope.event_id)) {
    issues.push({ pointer: '/event_id', reason: 'event_id_missing' });
  }
  const index = envelope.transaction_event_index;
  const count = envelope.transaction_event_count;
  if (!isNonNegativeInteger(index)) {
    issues.push({
      pointer: '/transaction_event_index',
      reason: 'index_invalid',
    });
  }
  if (
    typeof count !== 'number' ||
    !Number.isInteger(count) ||
    count < 1
  ) {
    issues.push({
      pointer: '/transaction_event_count',
      reason: 'count_invalid',
    });
  } else if (isNonNegativeInteger(index) && index >= count) {
    // transaction_event_index 从 0 连续递增且小于 count
    issues.push({
      pointer: '/transaction_event_index',
      reason: 'index_out_of_range',
    });
  }
  if (typeof envelope.render !== 'object' || envelope.render === null) {
    issues.push({ pointer: '/render', reason: 'render_payload_missing' });
  } else {
    const render = envelope.render as Record<string, unknown>;
    if (!isNonEmptyString(render.kind)) {
      issues.push({ pointer: '/render/kind', reason: 'render_kind_missing' });
    }
    if ('world_point' in render) {
      const sceneId = isNonEmptyString(envelope.scene_id)
        ? envelope.scene_id
        : undefined;
      issues.push(
        ...validateWorldPoint(
          render.world_point,
          '/render/world_point',
          sceneId,
        ),
      );
    }
  }
  return result(issues);
}
