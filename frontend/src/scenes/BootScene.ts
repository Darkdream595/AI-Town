/**
 * BootScene - 启动场景
 *
 * 符合 DOC-RENDER-001 规范：
 * - RULE-RENDER-001: BootScene -> PreloadScene -> WorldScene + UIScene 是唯一启动次序
 *
 * 职责：
 * - 建立字体、通用占位和配置
 * - 注册 fallback 资源
 * - 启动 PreloadScene
 */

import Phaser from 'phaser';

export class BootScene extends Phaser.Scene {
  constructor() {
    super({ key: 'BootScene' });
  }

  preload(): void {
    // 加载 fallback 资源
    this.loadFallbackAssets();
  }

  create(): void {
    console.log('[BootScene] Boot complete, starting PreloadScene...');

    // 设置全局配置
    this.setupGlobalConfig();

    // RULE-RENDER-001: 启动 PreloadScene
    this.scene.start('PreloadScene');
  }

  /**
   * 加载 fallback 资源
   *
   * DOC-RENDER-001: 资源或动画缺失时使用 fallback
   */
  private loadFallbackAssets(): void {
    // 创建 checkerboard fallback（用于缺失的地图切片）
    this.createCheckerboardTexture();

    // 创建 silhouette fallback（用于缺失的角色 sprite）
    this.createSilhouetteTexture();
  }

  /**
   * 创建 checkerboard 纹理（棋盘格）
   */
  private createCheckerboardTexture(): void {
    const size = 64;
    const cellSize = 8;
    const graphics = this.add.graphics();

    for (let y = 0; y < size; y += cellSize) {
      for (let x = 0; x < size; x += cellSize) {
        const isEven = ((x / cellSize) + (y / cellSize)) % 2 === 0;
        graphics.fillStyle(isEven ? 0xff00ff : 0x000000, 1);
        graphics.fillRect(x, y, cellSize, cellSize);
      }
    }

    graphics.generateTexture('asset.fallback.checkerboard', size, size);
    graphics.destroy();
  }

  /**
   * 创建 silhouette 纹理（角色剪影）
   */
  private createSilhouetteTexture(): void {
    const width = 32;
    const height = 48;
    const graphics = this.add.graphics();

    // 绘制简单的人形剪影
    graphics.fillStyle(0x666666, 1);

    // 头部
    graphics.fillCircle(width / 2, height * 0.2, width * 0.15);

    // 身体
    graphics.fillRect(width * 0.3, height * 0.3, width * 0.4, height * 0.5);

    // 腿
    graphics.fillRect(width * 0.35, height * 0.7, width * 0.12, height * 0.25);
    graphics.fillRect(width * 0.53, height * 0.7, width * 0.12, height * 0.25);

    graphics.generateTexture('asset.fallback.resident_silhouette', width, height);
    graphics.destroy();
  }

  /**
   * 设置全局配置
   */
  private setupGlobalConfig(): void {
    // 纹理过滤在 game config 的 pixelArt 中统一设定，运行期不再改 renderer

    // 禁用右键菜单
    this.input.mouse?.disableContextMenu();

    // 记录游戏配置
    console.log('[BootScene] Renderer:', this.renderer.type === Phaser.WEBGL ? 'WebGL' : 'Canvas');
    console.log('[BootScene] Resolution:', this.scale.width, 'x', this.scale.height);
  }
}
