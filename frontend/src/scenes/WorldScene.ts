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
import type {
  RenderFrameInput,
  EntityProjection,
  WorldPoint,
} from '../types/rendering';
import { calculateEntityDepth, facingToDirection } from '../types/rendering';

interface EntitySprite {
  sprite: Phaser.GameObjects.Sprite;
  projection: EntityProjection;
  /** 最后一次出现在 Snapshot 中的 revision，用于识别已离场实体 */
  lastSeenRevision: number;
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
  private currentSceneId: string = '';
  private sceneRevision: number = 0;

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

    // 创建渲染层（RULE-RENDER-007: 固定顺序）
    this.createRenderLayers();

    // 配置相机
    this.setupCamera();

    // 设置输入处理
    this.setupInput();

    console.log('[WorldScene] Ready');
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
    // 鼠标滚轮缩放
    this.input.on('wheel', (_pointer: any, _gameObjects: any[], _deltaX: number, deltaY: number) => {
      const camera = this.cameras.main;
      const oldZoom = camera.zoom;
      const zoomDelta = deltaY > 0 ? -0.1 : 0.1;
      const newZoom = Phaser.Math.Clamp(oldZoom + zoomDelta, this.MIN_ZOOM, this.MAX_ZOOM);
      camera.setZoom(newZoom);
    });

    // 中键拖拽移动相机（后续实现）
    // 这里暂时留空
  }

  /**
   * 更新渲染帧
   *
   * 由外部调用（后续会通过 EventBus 或 WebSocket 接收 RenderFrameInput）
   */
  public updateFrame(frameInput: RenderFrameInput): void {
    // RULE-RENDER-002: 只接受 revision 不低于当前的 Snapshot，过期输入整帧丢弃而非部分应用
    if (frameInput.revision < this.sceneRevision) {
      return;
    }

    // RULE-RENDER-004: 跨 scene 必须走 Load Gate 重建 Scene，不能在当前 Scene 内静默换图
    if (this.currentSceneId !== '' && this.currentSceneId !== frameInput.scene_id) {
      console.warn(
        `[WorldScene] Rejected snapshot for scene ${frameInput.scene_id}, current scene is ${this.currentSceneId}`
      );
      return;
    }

    this.sceneRevision = frameInput.revision;
    this.currentSceneId = frameInput.scene_id;

    for (const entityProj of frameInput.entities) {
      this.updateEntity(entityProj, frameInput.revision);
    }

    this.removeStaleEntities(frameInput.entities);

    this.sortEntitiesByDepth();
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
    this.updateEntityAnimation(entitySprite, projection.facing_degrees);
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
    const sprite = this.add.sprite(0, 0, 'fallback_silhouette');

    // RULE-RENDER-011: anchor 为脚底中点
    sprite.setOrigin(0.5, 1.0);

    // 添加到实体层
    this.entityLayer.add(sprite);

    return {
      sprite,
      projection,
      lastSeenRevision: 0,
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
    facingDegrees: 0 | 90 | 180 | 270
  ): void {
    const { sprite } = entitySprite;
    const direction = facingToDirection(facingDegrees);

    // RULE-RENDER-010: 方向只由已确认 facing 转换，不由视觉猜测
    // atlas 尚未接入，此处仅落定朝向；动画 key 选择在 Sprite 系统接入后补齐
    // west 有独立朝向帧，翻转 east 只作为缺帧降级手段，因此这里不做 flipX
    sprite.setFlipX(false);
    sprite.setData('direction', direction);
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
    console.log('[WorldScene] Cleaning up...');

    // 销毁所有实体
    for (const entitySprite of this.entities.values()) {
      entitySprite.sprite.destroy();
    }
    this.entities.clear();

    // 清空地图层
    this.groundLayer.removeAll(true);
    this.structureBackgroundLayer.removeAll(true);
    this.structureForegroundLayer.removeAll(true);
  }
}

// TODO: 实现地图切片加载逻辑（DOC-RENDER-003）
// - 根据 camera visible bounds 计算 visible slice bounds
// - 扩展 preload ring（四边各扩一格）
// - 加载 Ground Art 和 Structure 切片
// - 处理 LOD 切换（>20 cells 或 >160 MiB 切到 LOD1）
