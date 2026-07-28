/**
 * WorldScene - 主游戏场景
 *
 * 符合 DOC-RENDER-003、DOC-RENDER-004、DOC-RENDER-005 规范：
 * - RULE-RENDER-007: 五层地图合成（Ground Art → Structure → Entities → UI）
 * - RULE-RENDER-008: 确定性深度排序 (depth = floor(y_wu * 16) + depth_bias)
 * - RULE-RENDER-009: 支持 viewport 最大 3840×2160 px，zoom 0.75..2.0
 * - RULE-RENDER-010: 四方向、六帧 walk cycle
 * - RULE-RENDER-011: Sprite anchor 固定为脚底中点
 *
 * 职责：
 * - 管理地图切片（Ground Art、Structure）
 * - 管理动态实体（Sprite、动画、深度排序）
 * - 相机控制与视野裁剪
 * - 接收 RenderFrameInput 更新实体状态
 */

import Phaser from 'phaser';
import { EventBus } from '../core/EventBus';
import type {
  AnimationState,
  RenderFrameInput,
  RenderEventEnvelope,
  EntityProjection,
  WorldPoint,
} from '../types/rendering';
import { calculateEntityDepth, facingToDirection } from '../types/rendering';
import { SnapshotGate } from '../render/snapshot_gate';
import { EventSequencer } from '../render/event_sequencer';
import {
  AnimationMachine,
  type AnimationKind,
  type ResolvedAnimation,
} from '../render/animation_sm';
import {
  planMapSlices,
  type MapSlicePlan,
  type MapSlicePlanResult,
  type WorldBounds,
} from '../render/map_slices';
import { SpriteLoader } from '../utils/SpriteLoader';

interface EntitySprite {
  sprite: Phaser.GameObjects.Sprite;
  projection: EntityProjection;
  animationMachine: AnimationMachine;
  /** 最后一次出现在 Snapshot 中的 revision，用于识别已离场实体 */
  lastSeenRevision: number;
  characterName: string | null;
}

export class WorldScene extends Phaser.Scene {
  // 实体管理
  private entities: Map<string, EntitySprite> = new Map();

  // 地图层容器
  private groundLayer!: Phaser.GameObjects.Container;
  private structureBackgroundLayer!: Phaser.GameObjects.Container;
  private entityLayer!: Phaser.GameObjects.Container;
  private structureForegroundLayer!: Phaser.GameObjects.Container;

  // 当前场景信息
  private snapshotGate: SnapshotGate | null = null;
  private eventSequencer: EventSequencer | null = null;
  private cleanupCompleted = false;
  private worldInputAllowed = true;
  private currentMapSlicePlan: MapSlicePlan | null = null;
  private lastMapPlanInputSignature: string | null = null;
  private lastMapPlanFailureSignature: string | null = null;
  private readonly sceneBounds: WorldBounds = {
    left_wu: 0,
    top_wu: 0,
    right_wu: 4096,
    bottom_wu: 4096,
  };
  private readonly handleWorldInputAllowed = (allowed: boolean): void => {
    this.worldInputAllowed = allowed;
  };
  private readonly handleLifecycleCleanup = (): void => {
    this.cleanup();
  };
  private readonly handleRenderFrame = (frame: RenderFrameInput): void => {
    this.updateFrame(frame);
  };
  private readonly handleRenderEvent = (event: RenderEventEnvelope): void => {
    this.updateEvent(event);
  };
  private readonly handleWheel = (
    _pointer: Phaser.Input.Pointer,
    _gameObjects: Phaser.GameObjects.GameObject[],
    _deltaX: number,
    deltaY: number,
  ): void => {
    if (!this.worldInputAllowed) {
      return;
    }
    const camera = this.cameras.main;
    const zoomDelta = deltaY > 0 ? -0.1 : 0.1;
    camera.setZoom(
      Phaser.Math.Clamp(
        camera.zoom + zoomDelta,
        this.MIN_ZOOM,
        this.MAX_ZOOM,
      ),
    );
    this.refreshMapSlicePlan();
  };

  // 相机配置（RULE-RENDER-009）
  private readonly MIN_ZOOM = 0.75;
  private readonly MAX_ZOOM = 2.0;
  private readonly MAX_VIEWPORT_WIDTH = 3840;
  private readonly MAX_VIEWPORT_HEIGHT = 2160;

  constructor() {
    super({ key: 'WorldScene' });
  }

  create(): void {
    console.log('[WorldScene] Initializing...');
    this.cleanupCompleted = false;

    // 创建渲染层（RULE-RENDER-007: 固定顺序）
    this.createRenderLayers();

    // 配置相机
    this.setupCamera();

    // 设置输入处理
    this.setupInput();
    EventBus.on('ui:world-input-allowed', this.handleWorldInputAllowed);
    EventBus.on('render:frame:update', this.handleRenderFrame);
    EventBus.on('render:event', this.handleRenderEvent);
    this.events.once(Phaser.Scenes.Events.SHUTDOWN, this.handleLifecycleCleanup);
    this.events.once(Phaser.Scenes.Events.DESTROY, this.handleLifecycleCleanup);
    this.refreshMapSlicePlan();

    console.log('[WorldScene] Ready');
    EventBus.emit('world-scene-ready');
  }

  /**
   * 创建渲染层
   *
   * RULE-RENDER-007: Ground Art → 背景 Structure → entities/VFX → 前景 Structure → UI
   */
  private createRenderLayers(): void {
    // Layer 1: Ground Art (depth 0)
    this.groundLayer = this.add.container(0, 0);
    this.groundLayer.setDepth(0);
    const groundImage = this.add.image(0, 0, 'crown_creek_town_base');
    groundImage.setOrigin(0, 0);
    this.groundLayer.add(groundImage);

    // Layer 2: Structure Background (depth 100)
    this.structureBackgroundLayer = this.add.container(0, 0);
    this.structureBackgroundLayer.setDepth(100);

    // Layer 3: Entities/VFX (depth 1000+, 由 y_wu 动态计算)
    this.entityLayer = this.add.container(0, 0);
    this.entityLayer.setDepth(1000);

    // Layer 4: Structure Foreground (depth 100000)
    this.structureForegroundLayer = this.add.container(0, 0);
    this.structureForegroundLayer.setDepth(100000);
  }

  /**
   * 配置相机
   *
   * RULE-RENDER-009: 支持 viewport 最大 3840×2160 px，zoom 0.75..2.0
   */
  private setupCamera(): void {
    const camera = this.cameras.main;

    // 超出支持上限的 viewport 会让 preload ring 估算失真，需尽早暴露而非静默渲染
    if (
      this.scale.width > this.MAX_VIEWPORT_WIDTH ||
      this.scale.height > this.MAX_VIEWPORT_HEIGHT
    ) {
      console.warn(
        `[WorldScene] Viewport ${this.scale.width}x${this.scale.height} exceeds supported maximum ` +
          `${this.MAX_VIEWPORT_WIDTH}x${this.MAX_VIEWPORT_HEIGHT}`
      );
    }

    // 设置 zoom 范围
    camera.setZoom(1.0);

    // 设置相机边界（后续从 Scene bounds 读取）
    // 这里暂时设置一个默认值
    camera.setBounds(0, 0, 4096, 4096);

    // 设置背景色（临时用浅色背景）
    camera.setBackgroundColor('#c8b896');
  }

  /**
   * 设置输入处理
   */
  private setupInput(): void {
    this.input.on('wheel', this.handleWheel);

    // 中键拖拽移动相机（后续实现）
    // 这里暂时留空
  }

  /**
   * 更新渲染帧
   *
   * 由外部调用（后续会通过 EventBus 或 WebSocket 接收 RenderFrameInput）
   */
  public updateFrame(frameInput: RenderFrameInput): void {
    if (!this.snapshotGate) {
      this.snapshotGate = new SnapshotGate(
        frameInput.world_id,
        frameInput.scene_id,
      );
    }
    const decision = this.snapshotGate.evaluate(frameInput);
    if (decision.action !== 'apply') {
      if (decision.action === 'contract_error') {
        console.warn(`[WorldScene] Rejected snapshot: ${decision.reason}`);
      }
      return;
    }
    if (!this.eventSequencer) {
      this.eventSequencer = new EventSequencer(
        frameInput.world_id,
        frameInput.scene_id,
        frameInput.revision,
      );
    } else {
      this.eventSequencer.onSnapshotApplied(frameInput.revision);
    }

    this.cameras.main.centerOn(
      frameInput.camera_target.x_wu,
      frameInput.camera_target.y_wu,
    );

    for (const entityProj of frameInput.entities) {
      this.updateEntity(entityProj, frameInput.revision);
    }

    this.removeStaleEntities(frameInput.entities);

    this.sortEntitiesByDepth();
  }

  public updateEvent(event: RenderEventEnvelope): void {
    if (!this.eventSequencer) {
      EventBus.emit('render:resync-required', {
        reason: 'snapshot_required',
        received_revision: event.revision,
      });
      return;
    }
    const decision = this.eventSequencer.ingest(event);
    if (decision.action === 'resync' || decision.action === 'contract_error') {
      EventBus.emit('render:resync-required', decision);
      return;
    }
    if (decision.action !== 'applied') {
      return;
    }
    for (const appliedEvent of decision.events) {
      this.applyRenderEvent(appliedEvent);
    }
    this.sortEntitiesByDepth();
  }

  public update(): void {
    if (this.cleanupCompleted) {
      return;
    }
    this.refreshMapSlicePlan();
    for (const entitySprite of this.entities.values()) {
      this.renderResolvedAnimation(
        entitySprite,
        entitySprite.animationMachine.tick(),
      );
    }
  }

  public getMapSlicePlan(): MapSlicePlan | null {
    return this.currentMapSlicePlan;
  }

  private refreshMapSlicePlan(): void {
    const camera = this.cameras.main;
    const input = {
      viewport_width_px: this.scale.width,
      viewport_height_px: this.scale.height,
      camera_zoom: camera.zoom,
      camera_center_x_wu: camera.midPoint.x,
      camera_center_y_wu: camera.midPoint.y,
      scene_bounds: this.sceneBounds,
    };
    const inputSignature = JSON.stringify(input);
    if (inputSignature === this.lastMapPlanInputSignature) {
      return;
    }
    this.lastMapPlanInputSignature = inputSignature;
    const result: MapSlicePlanResult = planMapSlices(input);
    if (!result.ok) {
      const failureSignature = `${result.reason}:${inputSignature}`;
      if (failureSignature !== this.lastMapPlanFailureSignature) {
        this.lastMapPlanFailureSignature = failureSignature;
        EventBus.emit('render:diagnostic', {
          issue: 'MAP_SLICE_PLAN_FAILED',
          reason: result.reason,
        });
      }
      return;
    }
    this.lastMapPlanFailureSignature = null;
    this.currentMapSlicePlan = result;
    EventBus.emit('render:map-slice-plan', result);
  }

  private applyRenderEvent(event: RenderEventEnvelope): void {
    const payload = event.render;
    if (payload.kind === 'entity_spawned') {
      this.updateEntity(payload, event.revision);
      return;
    }
    const current = this.entities.get(payload.entity_id);
    if (payload.kind === 'entity_despawned') {
      current?.sprite.destroy();
      this.entities.delete(payload.entity_id);
      return;
    }
    if (!current) {
      EventBus.emit('render:resync-required', {
        reason: 'entity_projection_missing',
        entity_id: payload.entity_id,
        received_revision: event.revision,
      });
      return;
    }
    const projection: EntityProjection =
      payload.kind === 'entity_moved'
        ? {
            ...current.projection,
            world_point: payload.world_point,
            facing_degrees: payload.facing_degrees,
          }
        : {
            ...current.projection,
            world_point: payload.world_point,
            facing_degrees: payload.facing_degrees,
            desired_animation_state: payload.desired_animation_state,
          };
    this.updateEntity(projection, event.revision);
  }

  /**
   * 更新单个实体
   */
  private updateEntity(projection: EntityProjection, revision: number): void {
    const entityId = projection.entity_id;
    let entitySprite = this.entities.get(entityId);

    if (!entitySprite) {
      entitySprite = this.createEntity(projection);
      this.entities.set(entityId, entitySprite);
    }

    this.updateEntityPosition(entitySprite, projection.world_point);
    this.updateEntityAnimation(entitySprite, projection, revision);
    this.updateEntityDepth(entitySprite, projection.world_point);

    entitySprite.projection = projection;
    entitySprite.lastSeenRevision = revision;
  }

  /**
   * 创建实体 Sprite
   *
   * RULE-RENDER-011: Sprite anchor 固定为脚底中点
   */
  private createEntity(projection: EntityProjection): EntitySprite {
    // 暂时使用 fallback silhouette
    // 后续会根据 sprite_asset_id 加载实际 texture
    const sprite = SpriteLoader.createSpriteForAsset(
      this,
      0,
      0,
      projection.asset_id,
    );

    // RULE-RENDER-011: anchor 为脚底中点
    sprite.setOrigin(0.5, 1.0);

    // 添加到实体层
    this.entityLayer.add(sprite);

    const animationMachine = new AnimationMachine({
      now: () => this.time.now,
      exists: animationId => this.anims.exists(animationId),
      onMissingAnimation: diagnostic =>
        EventBus.emit('render:diagnostic', diagnostic),
    });
    return {
      sprite,
      projection,
      animationMachine,
      lastSeenRevision: 0,
      characterName: SpriteLoader.resolveCharacterName(projection.asset_id),
    };
  }

  /**
   * 更新实体位置
   *
   * WorldPoint 使用 world units (wu)，需要转换为像素坐标
   * 当前简化实现：1 wu = 1 px
   */
  private updateEntityPosition(entitySprite: EntitySprite, worldPoint: WorldPoint): void {
    // 简化实现：1 wu = 1 px
    // 后续会加入插值动画
    entitySprite.sprite.setPosition(worldPoint.x_wu, worldPoint.y_wu);
  }

  /**
   * 更新实体动画
   *
   * RULE-RENDER-010: 四方向、六帧 walk cycle
   * RULE-RENDER-013: 优先级为 downed > hurt > attack/cast > walk > idle
   */
  private updateEntityAnimation(
    entitySprite: EntitySprite,
    projection: EntityProjection,
    revision: number,
  ): void {
    const direction = facingToDirection(projection.facing_degrees);
    entitySprite.animationMachine.apply({
      asset_id: projection.asset_id,
      scene_id: projection.world_point.scene_id,
      revision,
      kind: this.toAnimationKind(projection.desired_animation_state),
      direction,
      animation_id: projection.desired_animation_state.animation_id,
    });
    this.renderResolvedAnimation(
      entitySprite,
      entitySprite.animationMachine.tick(),
    );
  }

  private toAnimationKind(state: AnimationState): AnimationKind {
    if (state.state === 'work') {
      return 'cast';
    }
    if (state.state === 'combat') {
      return 'attack';
    }
    return state.state;
  }

  private renderResolvedAnimation(
    entitySprite: EntitySprite,
    animation: ResolvedAnimation,
  ): void {
    entitySprite.sprite.setFlipX(false);
    entitySprite.sprite.setData('direction', animation.direction);
    entitySprite.sprite.setData('animationId', animation.animation_id);
    entitySprite.sprite.setData('animationKind', animation.kind);
    if (entitySprite.characterName !== null) {
      SpriteLoader.playAnimation(
        entitySprite.sprite,
        entitySprite.characterName,
        animation.kind,
        animation.direction,
      );
      return;
    }
    if (this.anims.exists(animation.animation_id)) {
      entitySprite.sprite.play(animation.animation_id, true);
    }
  }

  /**
   * 更新实体深度
   *
   * RULE-RENDER-008: depth = floor(y_wu * 16) + depth_bias
   * 同值以 stable entity_id 字典序打破平局
   */
  private updateEntityDepth(entitySprite: EntitySprite, worldPoint: WorldPoint): void {
    // 动态实体无 depth_bias（该字段属于 map slice），故按 y_wu 单独定序
    const depth = calculateEntityDepth(worldPoint);
    entitySprite.sprite.setDepth(depth);
  }

  /**
   * 移除过期实体
   *
   * 不在当前帧中的实体视为已离开视野或销毁
   */
  private removeStaleEntities(currentEntities: EntityProjection[]): void {
    const currentEntityIds = new Set(currentEntities.map(e => e.entity_id));

    for (const [entityId, entitySprite] of this.entities.entries()) {
      if (!currentEntityIds.has(entityId)) {
        entitySprite.sprite.destroy();
        this.entities.delete(entityId);
      }
    }
  }

  /**
   * 执行深度排序
   *
   * RULE-RENDER-008: 同 depth 值以 stable entity_id 字典序打破平局
   */
  private sortEntitiesByDepth(): void {
    const sortedEntities = Array.from(this.entities.entries())
      .sort((a, b) => {
        const depthA = a[1].sprite.depth;
        const depthB = b[1].sprite.depth;

        if (depthA !== depthB) {
          return depthA - depthB;
        }

        // 同 depth 按 entity_id 字典序
        return a[0].localeCompare(b[0]);
      });

    // 更新渲染顺序（通过设置 container 内的顺序）
    for (let i = 0; i < sortedEntities.length; i++) {
      const entitySprite = sortedEntities[i][1];
      this.entityLayer.bringToTop(entitySprite.sprite);
    }
  }

  /**
   * 清理场景
   *
   * RULE-RENDER-006: 离开区域 5 秒后 Dispose
   */
  public cleanup(): void {
    if (this.cleanupCompleted) {
      return;
    }
    this.cleanupCompleted = true;
    console.log('[WorldScene] Cleaning up...');
    this.events?.off(
      Phaser.Scenes.Events.SHUTDOWN,
      this.handleLifecycleCleanup,
    );
    this.events?.off(
      Phaser.Scenes.Events.DESTROY,
      this.handleLifecycleCleanup,
    );
    EventBus.off('ui:world-input-allowed', this.handleWorldInputAllowed);
    EventBus.off('render:frame:update', this.handleRenderFrame);
    EventBus.off('render:event', this.handleRenderEvent);
    this.input?.off('wheel', this.handleWheel);

    // 销毁所有实体
    for (const entitySprite of this.entities.values()) {
      entitySprite.sprite.destroy();
    }
    this.entities.clear();
    this.snapshotGate?.reset();
    this.snapshotGate = null;
    this.eventSequencer = null;
    this.currentMapSlicePlan = null;
    this.lastMapPlanInputSignature = null;
    this.lastMapPlanFailureSignature = null;

    // 清空地图层
    this.groundLayer?.removeAll(true);
    this.structureBackgroundLayer?.removeAll(true);
    this.structureForegroundLayer?.removeAll(true);
  }
}
