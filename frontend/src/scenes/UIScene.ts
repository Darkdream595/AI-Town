/**
 * UIScene - 常驻 UI orchestrator
 *
 * 符合 DOC-RENDER-001、DOC-RENDER-002 规范：
 * - RULE-RENDER-001: UIScene 与 WorldScene 并行运行
 * - 职责：管理所有 UI 元素，不参与地图/实体渲染
 *
 * 职责：
 * - 显示 HUD（时间、天气、季节）
 * - 显示对话框和居民卡片
 * - 显示交互提示
 * - 显示调试信息（可选）
 * - 处理 UI 输入事件
 */

import Phaser from 'phaser';
import type { RenderEventEnvelope } from '../types/rendering';

export class UIScene extends Phaser.Scene {
  // HUD 元素
  private hudContainer!: Phaser.GameObjects.Container;
  private timeText!: Phaser.GameObjects.Text;
  private weatherText!: Phaser.GameObjects.Text;
  private seasonText!: Phaser.GameObjects.Text;

  // 调试信息
  private debugContainer!: Phaser.GameObjects.Container;
  private debugText!: Phaser.GameObjects.Text;
  private debugEnabled: boolean = false;

  // 对话框容器
  private dialogueContainer!: Phaser.GameObjects.Container;

  constructor() {
    super({ key: 'UIScene' });
  }

  create(): void {
    console.log('[UIScene] Initializing...');

    // 创建 HUD
    this.createHUD();

    // 创建调试面板
    this.createDebugPanel();

    // 创建对话框容器
    this.createDialogueContainer();

    // 设置输入
    this.setupInput();

    console.log('[UIScene] Ready');
  }

  /**
   * 创建 HUD
   *
   * 显示时间、天气、季节等基础信息
   */
  private createHUD(): void {
    const width = this.cameras.main.width;

    this.hudContainer = this.add.container(0, 0);
    this.hudContainer.setDepth(200000); // UI 层级最高

    // HUD 背景（羊皮纸风格）
    const hudBg = this.add.rectangle(0, 0, width, 60, 0xf4e4c1, 0.9);
    hudBg.setOrigin(0, 0);
    this.hudContainer.add(hudBg);

    // 时间显示
    this.timeText = this.add.text(20, 20, '时间: --:--', {
      fontSize: '18px',
      color: '#5a4a3a',
      fontFamily: 'serif',
    });
    this.hudContainer.add(this.timeText);

    // 天气显示
    this.weatherText = this.add.text(200, 20, '天气: 晴朗', {
      fontSize: '18px',
      color: '#5a4a3a',
      fontFamily: 'serif',
    });
    this.hudContainer.add(this.weatherText);

    // 季节显示
    this.seasonText = this.add.text(380, 20, '季节: 春季', {
      fontSize: '18px',
      color: '#5a4a3a',
      fontFamily: 'serif',
    });
    this.hudContainer.add(this.seasonText);
  }

  /**
   * 创建调试面板
   *
   * 显示 FPS、实体数量、相机位置等调试信息
   */
  private createDebugPanel(): void {
    const width = this.cameras.main.width;

    this.debugContainer = this.add.container(0, 0);
    this.debugContainer.setDepth(300000); // 调试层级更高
    this.debugContainer.setVisible(false); // 默认隐藏

    // 调试背景
    const debugBg = this.add.rectangle(width - 250, 70, 240, 200, 0x000000, 0.7);
    debugBg.setOrigin(0, 0);
    this.debugContainer.add(debugBg);

    // 调试文本
    this.debugText = this.add.text(width - 240, 80, '', {
      fontSize: '14px',
      color: '#00ff00',
      fontFamily: 'monospace',
    });
    this.debugContainer.add(this.debugText);
  }

  /**
   * 创建对话框容器
   *
   * 用于显示 NPC 对话、系统提示等
   */
  private createDialogueContainer(): void {
    const width = this.cameras.main.width;
    const height = this.cameras.main.height;

    this.dialogueContainer = this.add.container(0, 0);
    this.dialogueContainer.setDepth(250000);
    this.dialogueContainer.setVisible(false); // 默认隐藏

    // 对话框背景（羊皮纸风格，底部居中）
    const dialogueBg = this.add.rectangle(width / 2, height - 120, width - 200, 200, 0xf4e4c1, 0.95);
    dialogueBg.setOrigin(0.5, 0.5);
    dialogueBg.setStrokeStyle(4, 0x8b7355);
    this.dialogueContainer.add(dialogueBg);

    // 对话框文本（暂时留空，后续会根据事件填充）
  }

  /**
   * 设置输入
   */
  private setupInput(): void {
    // F3 切换调试面板
    this.input.keyboard?.on('keydown-F3', () => {
      this.debugEnabled = !this.debugEnabled;
      this.debugContainer.setVisible(this.debugEnabled);
    });
  }

  /**
   * 更新 HUD 信息
   *
   * 由外部调用（后续会通过 EventBus 接收状态更新）
   */
  public updateHUD(data: {
    time?: string;
    weather?: string;
    season?: string;
  }): void {
    if (data.time) {
      this.timeText.setText(`时间: ${data.time}`);
    }
    if (data.weather) {
      this.weatherText.setText(`天气: ${data.weather}`);
    }
    if (data.season) {
      this.seasonText.setText(`季节: ${data.season}`);
    }
  }

  /**
   * 显示对话框
   *
   * 后续会根据 RenderEventEnvelope 中的对话事件显示
   */
  public showDialogue(speaker: string, text: string): void {
    this.dialogueContainer.setVisible(true);

    // 清空旧内容
    this.dialogueContainer.removeAll(true);

    const width = this.cameras.main.width;
    const height = this.cameras.main.height;

    // 对话框背景
    const dialogueBg = this.add.rectangle(width / 2, height - 120, width - 200, 200, 0xf4e4c1, 0.95);
    dialogueBg.setOrigin(0.5, 0.5);
    dialogueBg.setStrokeStyle(4, 0x8b7355);
    this.dialogueContainer.add(dialogueBg);

    // 说话者名字
    const speakerText = this.add.text(width / 2 - (width - 200) / 2 + 20, height - 200, speaker, {
      fontSize: '20px',
      color: '#5a4a3a',
      fontFamily: 'serif',
      fontStyle: 'bold',
    });
    this.dialogueContainer.add(speakerText);

    // 对话内容
    const dialogueText = this.add.text(width / 2 - (width - 200) / 2 + 20, height - 170, text, {
      fontSize: '18px',
      color: '#5a4a3a',
      fontFamily: 'serif',
      wordWrap: { width: width - 240 },
    });
    this.dialogueContainer.add(dialogueText);
  }

  /**
   * 隐藏对话框
   */
  public hideDialogue(): void {
    this.dialogueContainer.setVisible(false);
  }

  /**
   * 处理渲染事件
   *
   * 根据 RenderEventEnvelope 更新 UI 状态
   */
  public handleRenderEvent(event: RenderEventEnvelope): void {
    // RenderEventEnvelope 的判别字段是 render.kind（见 DES-RENDER-001）
    // 对话/时间等 UI 状态走 UIScene 的 projection 通道，不在 render event 里
    switch (event.render.kind) {
      case 'entity_spawned':
      case 'entity_despawned':
        // 实体增删只影响 WorldScene，UI 暂无需响应
        break;
      case 'entity_moved':
      case 'entity_animation_changed':
        // 后续用于跟随选中实体的信息面板
        break;
    }
  }

  update(_time: number, _delta: number): void {
    if (this.debugEnabled) {
      this.updateDebugInfo();
    }
  }

  /**
   * 更新调试信息
   */
  private updateDebugInfo(): void {
    const worldScene = this.scene.get('WorldScene') as any;
    const camera = worldScene?.cameras?.main;

    const debugInfo = [
      `FPS: ${Math.round(this.game.loop.actualFps)}`,
      `Delta: ${this.game.loop.delta.toFixed(2)} ms`,
      camera ? `Camera: (${Math.round(camera.scrollX)}, ${Math.round(camera.scrollY)})` : 'Camera: N/A',
      camera ? `Zoom: ${camera.zoom.toFixed(2)}` : 'Zoom: N/A',
      worldScene?.entities ? `Entities: ${worldScene.entities.size}` : 'Entities: 0',
    ];

    this.debugText.setText(debugInfo.join('\n'));
  }
}
