/**
 * PreloadScene - 预加载场景
 *
 * 符合 DOC-RENDER-001、DOC-RENDER-002 规范：
 * - RULE-RENDER-001: PreloadScene 按 Asset Manifest 加载当前 Scene 的必需资源
 * - RULE-RENDER-005: Load Gate 未完成前展示 loading parchment
 *
 * 职责：
 * - 按 Asset Manifest 加载必需资源
 * - 显示加载进度（羊皮纸风格）
 * - 完成后启动 WorldScene + UIScene
 */

import Phaser from 'phaser';

export class PreloadScene extends Phaser.Scene {
  private loadingText!: Phaser.GameObjects.Text;
  private progressBar!: Phaser.GameObjects.Graphics;
  private progressBox!: Phaser.GameObjects.Graphics;

  constructor() {
    super({ key: 'PreloadScene' });
  }

  preload(): void {
    console.log('[PreloadScene] Loading assets...');

    // 显示加载界面（羊皮纸风格）
    this.createLoadingUI();

    // 加载测试资源（后续会从 Asset Manifest 加载）
    this.loadTestAssets();

    // 设置加载进度回调
    this.setupLoadingCallbacks();
  }

  create(): void {
    console.log('[PreloadScene] Assets loaded, starting WorldScene and UIScene...');

    // RULE-RENDER-001: 启动 WorldScene + UIScene
    // WorldScene 是主要的游戏场景
    this.scene.launch('WorldScene');

    // UIScene 是常驻 UI orchestrator
    this.scene.launch('UIScene');

    // 停止 PreloadScene
    this.scene.stop('PreloadScene');
  }

  /**
   * 创建加载 UI（羊皮纸风格）
   *
   * RULE-RENDER-005: Load Gate 未完成前展示 loading parchment
   */
  private createLoadingUI(): void {
    const centerX = this.cameras.main.width / 2;
    const centerY = this.cameras.main.height / 2;

    // 背景（羊皮纸色）
    this.add.rectangle(0, 0, this.cameras.main.width, this.cameras.main.height, 0xf4e4c1)
      .setOrigin(0, 0);

    // 标题
    this.add.text(centerX, centerY - 100, 'AI 小镇', {
      fontSize: '48px',
      color: '#5a4a3a',
      fontFamily: 'serif',
      fontStyle: 'bold',
    }).setOrigin(0.5);

    // 加载文本
    this.loadingText = this.add.text(centerX, centerY + 50, '加载中... 0%', {
      fontSize: '20px',
      color: '#5a4a3a',
      fontFamily: 'serif',
    }).setOrigin(0.5);

    // 进度条背景
    this.progressBox = this.add.graphics();
    this.progressBox.fillStyle(0xd4c4a1, 0.8);
    this.progressBox.fillRect(centerX - 160, centerY - 25, 320, 50);

    // 进度条
    this.progressBar = this.add.graphics();
  }

  /**
   * 设置加载进度回调
   */
  private setupLoadingCallbacks(): void {
    const centerX = this.cameras.main.width / 2;
    const centerY = this.cameras.main.height / 2;

    this.load.on('progress', (value: number) => {
      // 更新进度条
      this.progressBar.clear();
      this.progressBar.fillStyle(0x8b7355, 1);
      this.progressBar.fillRect(centerX - 150, centerY - 15, 300 * value, 30);

      // 更新加载文本
      const percent = Math.floor(value * 100);
      this.loadingText.setText(`加载中... ${percent}%`);
    });

    this.load.on('complete', () => {
      console.log('[PreloadScene] All assets loaded');
    });

    this.load.on('loaderror', (fileObj: any) => {
      console.error('[PreloadScene] Failed to load:', fileObj.key);
    });
  }

  /**
   * 加载测试资源
   *
   * 后续会从 Asset Manifest 读取并加载实际资源
   * DOC-RENDER-011: Asset Manifest 与 fallback
   */
  private loadTestAssets(): void {
    // 这里暂时为空，后续会添加实际的资源加载逻辑
    // 例如：
    // - 地图切片（Ground Art、Structure）
    // - 角色 Sprite
    // - UI 素材
    // - 音频资源

    // 模拟一些加载时间（测试用）
    for (let i = 0; i < 10; i++) {
      this.load.image(`dummy_${i}`, 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==');
    }
  }
}
