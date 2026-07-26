/**
 * UIScene - UI 场景
 *
 * 符合 DOC-RENDER-009 规范：
 * - 通过 PhaserDomBridge 更新 #ui-overlay
 * - 不再使用 Phaser 绘图
 * - 保留 EventBus 通信和场景生命周期
 */

import Phaser from 'phaser';
import { EventBus } from '../core/EventBus';
import { PhaserDomBridge } from '../ui/PhaserDomBridge';
import type { UiRenderProjection } from '../types/ui_projection';

export class UIScene extends Phaser.Scene {
  private domBridge!: PhaserDomBridge;
  private currentRevision: number = -1;
  private debugEnabled: boolean = false;

  constructor() {
    super({ key: 'UIScene' });
  }

  create(): void {
    console.log('UIScene created');

    // 初始化 DOM Bridge
    this.domBridge = new PhaserDomBridge();

    // 监听 EventBus 事件
    EventBus.on('ui:update', this.handleUiUpdate, this);
    EventBus.on('ui:show-dialogue', this.handleShowDialogue, this);
    EventBus.on('ui:show-mayor-panel', this.handleShowMayorPanel, this);

    // F3 切换调试信息
    this.input.keyboard?.on('keydown-F3', () => {
      this.debugEnabled = !this.debugEnabled;
      EventBus.emit('ui:toggle-debug', this.debugEnabled);
    });

    // 初始 UI projection（占位数据）
    this.updateUI({
      protocol_version: 'ui.v1',
      world_id: 'test_world',
      revision: 0,
      game_time: 0,
      hud: {
        player_name: '玩家',
        season: '春季',
        weather: '晴朗',
        time_display: '第0年1月1日 00:00',
      },
    });

    EventBus.emit('ui-scene-ready');
  }

  /**
   * 更新 UI projection
   */
  private handleUiUpdate(projection: UiRenderProjection): void {
    this.updateUI(projection);
  }

  /**
   * 显示对话框
   */
  private handleShowDialogue(data: { speaker: string; text: string }): void {
    const projection: UiRenderProjection = {
      protocol_version: 'ui.v1',
      world_id: 'test_world',
      revision: ++this.currentRevision,
      game_time: 0,
      hud: this.getCurrentHud(),
      dialogue: {
        conversation_id: 'temp_conversation',
        speaker_name: data.speaker,
        speaker_entity_id: 'temp_entity',
        text: data.text,
      },
    };

    this.updateUI(projection);
  }

  /**
   * 显示镇长面板
   */
  private handleShowMayorPanel(): void {
    const projection: UiRenderProjection = {
      protocol_version: 'ui.v1',
      world_id: 'test_world',
      revision: ++this.currentRevision,
      game_time: 0,
      hud: this.getCurrentHud(),
      mayor_panel: {
        budget_copper: 10000,
        population: 12,
        satisfaction: 75,
        available_commands: [
          {
            command_id: 'build_house',
            display_name: '建造房屋',
            description: '为新居民建造住所',
            cost_copper: 5000,
          },
          {
            command_id: 'host_festival',
            display_name: '举办节日',
            description: '提升居民满意度',
            cost_copper: 2000,
          },
        ],
      },
    };

    this.updateUI(projection);
  }

  /**
   * 更新 UI（通过 DOM Bridge）
   */
  private updateUI(projection: UiRenderProjection): void {
    this.domBridge.patch(projection);
    this.currentRevision = projection.revision;
  }

  /**
   * 获取当前 HUD 数据
   */
  private getCurrentHud() {
    return {
      player_name: '玩家',
      season: '春季',
      weather: '晴朗',
      time_display: '第0年1月1日 00:00',
    };
  }

  /**
   * 更新游戏时间显示
   */
  public updateTime(timeDisplay: string): void {
    const projection: UiRenderProjection = {
      protocol_version: 'ui.v1',
      world_id: 'test_world',
      revision: ++this.currentRevision,
      game_time: 0,
      hud: {
        ...this.getCurrentHud(),
        time_display: timeDisplay,
      },
    };

    this.updateUI(projection);
  }

  /**
   * 更新天气显示
   */
  public updateWeather(weather: string): void {
    const projection: UiRenderProjection = {
      protocol_version: 'ui.v1',
      world_id: 'test_world',
      revision: ++this.currentRevision,
      game_time: 0,
      hud: {
        ...this.getCurrentHud(),
        weather,
      },
    };

    this.updateUI(projection);
  }

  /**
   * 更新季节显示
   */
  public updateSeason(season: string): void {
    const projection: UiRenderProjection = {
      protocol_version: 'ui.v1',
      world_id: 'test_world',
      revision: ++this.currentRevision,
      game_time: 0,
      hud: {
        ...this.getCurrentHud(),
        season,
      },
    };

    this.updateUI(projection);
  }

  shutdown(): void {
    EventBus.off('ui:update', this.handleUiUpdate, this);
    EventBus.off('ui:show-dialogue', this.handleShowDialogue, this);
    EventBus.off('ui:show-mayor-panel', this.handleShowMayorPanel, this);
  }
}
