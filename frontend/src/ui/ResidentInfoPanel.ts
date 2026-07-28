/**
 * 居民信息面板
 *
 * 显示居民的详细信息
 */

import { ResidentDetail } from '../api/residents';

export class ResidentInfoPanel {
  private scene: Phaser.Scene;
  private container: Phaser.GameObjects.Container;
  private background: Phaser.GameObjects.Rectangle;
  private closeButton: Phaser.GameObjects.Text;
  private contentText: Phaser.GameObjects.Text;
  private visible: boolean = false;

  constructor(scene: Phaser.Scene) {
    this.scene = scene;

    // 创建容器
    this.container = scene.add.container(0, 0);
    this.container.setDepth(1000);
    this.container.setVisible(false);

    // 背景面板
    this.background = scene.add.rectangle(0, 0, 400, 500, 0x2c3e50, 0.95);
    this.background.setOrigin(0, 0);
    this.background.setStrokeStyle(2, 0xecf0f1);

    // 关闭按钮
    this.closeButton = scene.add.text(370, 10, '✕', {
      fontSize: '24px',
      color: '#ecf0f1',
    });
    this.closeButton.setInteractive({ useHandCursor: true });
    this.closeButton.on('pointerdown', () => this.hide());
    this.closeButton.on('pointerover', () => this.closeButton.setColor('#e74c3c'));
    this.closeButton.on('pointerout', () => this.closeButton.setColor('#ecf0f1'));

    // 内容文本
    this.contentText = scene.add.text(20, 50, '', {
      fontSize: '16px',
      color: '#ecf0f1',
      wordWrap: { width: 360 },
      lineSpacing: 8,
    });

    // 添加到容器
    this.container.add([this.background, this.closeButton, this.contentText]);

    // 设置位置（右侧）
    const camera = scene.cameras.main;
    this.container.setPosition(camera.width - 420, 20);
  }

  /**
   * 显示居民信息
   */
  show(resident: ResidentDetail): void {
    // 构建显示内容
    const content = this.formatResidentInfo(resident);
    this.contentText.setText(content);

    // 显示面板
    this.container.setVisible(true);
    this.visible = true;

    // 添加淡入动画
    this.container.setAlpha(0);
    this.scene.tweens.add({
      targets: this.container,
      alpha: 1,
      duration: 200,
      ease: 'Power2',
    });
  }

  /**
   * 隐藏面板
   */
  hide(): void {
    this.scene.tweens.add({
      targets: this.container,
      alpha: 0,
      duration: 200,
      ease: 'Power2',
      onComplete: () => {
        this.container.setVisible(false);
        this.visible = false;
      },
    });
  }

  /**
   * 切换显示状态
   */
  toggle(resident?: ResidentDetail): void {
    if (this.visible) {
      this.hide();
    } else if (resident) {
      this.show(resident);
    }
  }

  /**
   * 格式化居民信息
   */
  private formatResidentInfo(resident: ResidentDetail): string {
    const lines: string[] = [];

    // 基本信息
    lines.push(`【${resident.name}】`);
    lines.push('');
    lines.push(`种族: ${this.translateRace(resident.race)}`);
    lines.push(`性别: ${this.translateGender(resident.gender)}`);
    lines.push(`年龄: ${resident.age_years} 岁`);
    if (resident.profession) {
      lines.push(`职业: ${this.translateProfession(resident.profession)}`);
    }
    lines.push('');

    // 外观
    lines.push('【外观】');
    lines.push(`精灵: ${resident.sprite_id}`);
    lines.push(`肤色: ${resident.skin_tone}`);
    lines.push(`发色: ${resident.hair_color}`);
    lines.push('');

    // 健康状态
    lines.push('【健康】');
    lines.push(`状态: ${this.translateHealthStatus(resident.health_status)}`);
    lines.push(`HP: ${resident.current_hp}/${resident.max_hp}`);
    this.addProgressBar(lines, resident.current_hp, resident.max_hp);
    lines.push('');

    // 需求
    lines.push('【需求】');
    lines.push(`饥饿: ${resident.hunger}/100`);
    this.addProgressBar(lines, resident.hunger, 100);
    lines.push(`精力: ${resident.energy}/100`);
    this.addProgressBar(lines, resident.energy, 100);
    lines.push(`社交: ${resident.social}/100`);
    this.addProgressBar(lines, resident.social, 100);
    lines.push('');

    // 情绪
    lines.push('【情绪】');
    lines.push(`喜悦: ${resident.joy}/100`);
    lines.push(`恐惧: ${resident.fear}/100`);
    lines.push(`愤怒: ${resident.anger}/100`);

    return lines.join('\n');
  }

  /**
   * 添加进度条
   */
  private addProgressBar(lines: string[], current: number, max: number): void {
    const barLength = 20;
    const filled = Math.floor((current / max) * barLength);
    const empty = barLength - filled;
    const bar = '█'.repeat(filled) + '░'.repeat(empty);
    lines.push(`  ${bar}`);
  }

  /**
   * 翻译种族
   */
  private translateRace(race: string): string {
    const map: Record<string, string> = {
      human: '人类',
      elf: '精灵',
      dwarf: '矮人',
      halfling: '半身人',
    };
    return map[race] || race;
  }

  /**
   * 翻译性别
   */
  private translateGender(gender: string): string {
    const map: Record<string, string> = {
      male: '男',
      female: '女',
      other: '其他',
    };
    return map[gender] || gender;
  }

  /**
   * 翻译职业
   */
  private translateProfession(profession: string): string {
    const map: Record<string, string> = {
      farmer: '农夫',
      mage: '法师',
      blacksmith: '铁匠',
      merchant: '商人',
      guard: '守卫',
      priest: '牧师',
      innkeeper: '旅店老板',
      alchemist: '炼金术士',
      hunter: '猎人',
      miner: '矿工',
    };
    return map[profession] || profession;
  }

  /**
   * 翻译健康状态
   */
  private translateHealthStatus(status: string): string {
    const map: Record<string, string> = {
      healthy: '健康',
      injured: '受伤',
      sick: '生病',
      dead: '死亡',
    };
    return map[status] || status;
  }

  /**
   * 销毁面板
   */
  destroy(): void {
    this.container.destroy();
  }

  /**
   * 检查是否可见
   */
  isVisible(): boolean {
    return this.visible;
  }
}
