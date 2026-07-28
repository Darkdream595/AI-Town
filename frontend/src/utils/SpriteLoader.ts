/**
 * SpriteLoader - 角色 Sprite 加载器
 *
 * 符合 DOC-RENDER-004、DOC-RENDER-005 规范：
 * - 从 extracted frames 加载角色动画
 * - 创建 Phaser 动画配置
 * - 处理缺失动画的降级
 */

import Phaser from 'phaser';
import {
  lintSpriteSpec,
  type SpriteCatalogSpec,
  type SpriteLintDiagnostic,
} from '../render/sprite_lint';

const FALLBACK_SILHOUETTE_TEXTURE = 'asset.fallback.resident_silhouette';

export interface SpriteCatalogRegistration {
  accepted: boolean;
  diagnostics: SpriteLintDiagnostic[];
}

/**
 * 角色动画配置
 */
interface AnimationConfig {
  frames: string[];
  frameRate: number;
  repeat: number;
}

/**
 * Atlas 配置
 */
interface AtlasConfig {
  frames: Array<{
    filename: string;
    frame: { x: number; y: number; w: number; h: number };
    rotated: boolean;
    trimmed: boolean;
    spriteSourceSize: { x: number; y: number; w: number; h: number };
    sourceSize: { w: number; h: number };
    pivot: { x: number; y: number };
  }>;
  meta: {
    app: string;
    version: string;
    image: string;
    format: string;
    size: { w: number; h: number };
    scale: number;
  };
}

/**
 * 角色 Sprite 加载器
 */
export class SpriteLoader {
  private static readonly catalogRegistrations =
    new Map<string, SpriteCatalogRegistration>();

  /**
   * Registers and validates the catalog contract consumed by subsequent
   * load/create calls for this character.
   */
  static registerCharacterCatalog(
    characterName: string,
    spec: SpriteCatalogSpec,
  ): SpriteCatalogRegistration {
    const diagnostics = lintSpriteSpec(spec);
    const registration = {
      accepted: diagnostics.length === 0,
      diagnostics,
    };
    SpriteLoader.catalogRegistrations.set(characterName, registration);
    return registration;
  }

  /**
   * 加载角色的所有动画帧
   *
   * @param scene Phaser Scene
   * @param characterName 角色名称（如 human_farmer）
   */
  static loadCharacter(scene: Phaser.Scene, characterName: string): void {
    if (!SpriteLoader.isCatalogAccepted(characterName)) {
      console.warn(
        `[SpriteLoader] Rejected invalid sprite catalog for ${characterName}; using silhouette fallback`,
      );
      return;
    }

    // 加载 atlas 和动画配置
    const atlasKey = `${characterName}_atlas`;
    const animKey = `${characterName}_animations`;

    // 从缓存中获取配置
    const atlasConfig = scene.cache.json.get(atlasKey) as AtlasConfig;
    const animConfig = scene.cache.json.get(animKey) as Record<string, AnimationConfig>;

    if (!atlasConfig || !animConfig) {
      console.error(`[SpriteLoader] Failed to load config for ${characterName}`);
      return;
    }

    console.log(`[SpriteLoader] Loading ${characterName}: ${atlasConfig.frames.length} frames, ${Object.keys(animConfig).length} animations`);

    // 为每一帧加载图片
    atlasConfig.frames.forEach(frameData => {
      const frameName = frameData.filename;
      const frameKey = `${characterName}_${frameName}`;
      const framePath = `assets/sprites/extracted/${characterName}/${characterName}_${frameName}.png`;

      // 加载单独的帧图片
      scene.load.image(frameKey, framePath);
    });

    // 等待加载完成后创建动画
    scene.load.once('complete', () => {
      SpriteLoader.createAnimations(scene, characterName, animConfig);
    });

    scene.load.start();
  }

  /**
   * 创建角色的所有动画
   *
   * @param scene Phaser Scene
   * @param characterName 角色名称
   * @param animConfig 动画配置
   */
  private static createAnimations(
    scene: Phaser.Scene,
    characterName: string,
    animConfig: Record<string, AnimationConfig>
  ): void {
    // 为每个动画创建 Phaser 动画
    Object.entries(animConfig).forEach(([animName, config]) => {
      const animKey = `${characterName}_${animName}`;

      // 检查动画是否已存在
      if (scene.anims.exists(animKey)) {
        return;
      }

      // 构建帧数组
      const frames = config.frames.map(frameName => ({
        key: `${characterName}_${frameName}`,
      }));

      // 创建动画
      scene.anims.create({
        key: animKey,
        frames: frames,
        frameRate: config.frameRate,
        repeat: config.repeat,
      });
    });

    console.log(`[SpriteLoader] Created ${Object.keys(animConfig).length} animations for ${characterName}`);
  }

  /**
   * 创建角色 Sprite
   *
   * @param scene Phaser Scene
   * @param x X 坐标
   * @param y Y 坐标
   * @param characterName 角色名称
   * @returns Phaser Sprite
   */
  static createSprite(
    scene: Phaser.Scene,
    x: number,
    y: number,
    characterName: string
  ): Phaser.GameObjects.Sprite {
    if (!SpriteLoader.isCatalogAccepted(characterName)) {
      const fallbackSprite = scene.add.sprite(
        x,
        y,
        FALLBACK_SILHOUETTE_TEXTURE,
      );
      fallbackSprite.setOrigin(0.5, 1.0);
      return fallbackSprite;
    }

    // 使用 idle_south 的第一帧作为初始纹理
    const initialTexture = `${characterName}_idle_south_0`;

    // 创建 sprite
    const sprite = scene.add.sprite(x, y, initialTexture);

    // 设置锚点在脚底中心（符合 RULE-RENDER-011）
    sprite.setOrigin(0.5, 1.0);

    // 播放默认 idle 动画
    const idleAnimKey = `${characterName}_idle_south`;
    if (scene.anims.exists(idleAnimKey)) {
      sprite.play(idleAnimKey);
    }

    return sprite;
  }

  static resolveCharacterName(assetId: string): string | null {
    const prefix = 'sprite.resident.';
    if (!assetId.startsWith(prefix)) {
      return null;
    }
    const characterName = assetId.slice(prefix.length);
    return SpriteLoader.getSupportedCharacters().includes(characterName)
      ? characterName
      : null;
  }

  static createSpriteForAsset(
    scene: Phaser.Scene,
    x: number,
    y: number,
    assetId: string,
  ): Phaser.GameObjects.Sprite {
    const characterName = SpriteLoader.resolveCharacterName(assetId);
    if (
      characterName === null ||
      !scene.textures.exists(`${characterName}_idle_south_0`)
    ) {
      const fallbackSprite = scene.add.sprite(
        x,
        y,
        FALLBACK_SILHOUETTE_TEXTURE,
      );
      fallbackSprite.setOrigin(0.5, 1);
      return fallbackSprite;
    }
    return SpriteLoader.createSprite(scene, x, y, characterName);
  }

  /**
   * 播放角色动画
   *
   * 符合 DOC-RENDER-005 动画状态机规范
   *
   * @param sprite Phaser Sprite
   * @param characterName 角色名称
   * @param action 动作名称（如 walk, idle, spellcast）
   * @param direction 方向（north, east, south, west）
   */
  static playAnimation(
    sprite: Phaser.GameObjects.Sprite,
    characterName: string,
    action: string,
    direction: string
  ): void {
    if (!SpriteLoader.isCatalogAccepted(characterName)) {
      return;
    }

    const animKey = `${characterName}_${action}_${direction}`;

    // 检查动画是否存在
    if (!sprite.scene.anims.exists(animKey)) {
      // 降级：尝试 idle 动画
      const fallbackKey = `${characterName}_idle_${direction}`;
      if (sprite.scene.anims.exists(fallbackKey)) {
        sprite.play(fallbackKey, true);
        return;
      }

      // 再降级：尝试 idle_south
      const finalFallback = `${characterName}_idle_south`;
      if (sprite.scene.anims.exists(finalFallback)) {
        sprite.play(finalFallback, true);
        return;
      }

      console.warn(`[SpriteLoader] Animation not found: ${animKey}, no fallback available`);
      return;
    }

    // 播放动画
    sprite.play(animKey, true);
  }

  /**
   * 获取所有支持的角色列表
   */
  static getSupportedCharacters(): string[] {
    return [
      'human_farmer',
      'elf_mage',
      'dwarf_blacksmith',
      'halfling_merchant',
      'human_guard',
      'human_priest',
      'human_innkeeper',
      'elf_alchemist',
      'human_hunter',
      'dwarf_miner',
    ];
  }

  private static isCatalogAccepted(characterName: string): boolean {
    return SpriteLoader.catalogRegistrations.get(characterName)?.accepted ?? true;
  }
}
