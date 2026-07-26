/**
 * BootScene - 启动场景
 * 负责初始化和资源加载
 */
import Phaser from 'phaser';

export class BootScene extends Phaser.Scene {
  constructor() {
    super({ key: 'BootScene' });
  }

  preload(): void {
    // 显示加载进度
    this.createLoadingBar();
  }

  create(): void {
    console.log('AI Town 启动场景已初始化');

    // 显示欢迎信息
    const centerX = this.cameras.main.width / 2;
    const centerY = this.cameras.main.height / 2;

    this.add.text(centerX, centerY - 50, 'AI 小镇', {
      fontSize: '48px',
      color: '#ffffff',
      fontFamily: 'Microsoft YaHei',
    }).setOrigin(0.5);

    this.add.text(centerX, centerY + 20, '后端连接中...', {
      fontSize: '20px',
      color: '#888888',
      fontFamily: 'Microsoft YaHei',
    }).setOrigin(0.5);

    this.add.text(centerX, centerY + 60, '按 F11 进入全屏', {
      fontSize: '16px',
      color: '#666666',
      fontFamily: 'Microsoft YaHei',
    }).setOrigin(0.5);

    // 测试后端连接
    this.testBackendConnection();
  }

  private createLoadingBar(): void {
    const centerX = this.cameras.main.width / 2;
    const centerY = this.cameras.main.height / 2;

    const progressBar = this.add.graphics();
    const progressBox = this.add.graphics();
    progressBox.fillStyle(0x222222, 0.8);
    progressBox.fillRect(centerX - 160, centerY - 30, 320, 50);

    this.load.on('progress', (value: number) => {
      progressBar.clear();
      progressBar.fillStyle(0xffffff, 1);
      progressBar.fillRect(centerX - 150, centerY - 20, 300 * value, 30);
    });

    this.load.on('complete', () => {
      progressBar.destroy();
      progressBox.destroy();
    });
  }

  private async testBackendConnection(): Promise<void> {
    try {
      const response = await fetch('http://localhost:8000/api/health');
      const data = await response.json();
      console.log('后端连接成功:', data);
    } catch (error) {
      console.error('后端连接失败:', error);
      console.log('请确保后端服务已启动: python backend/src/main.py');
    }
  }
}
