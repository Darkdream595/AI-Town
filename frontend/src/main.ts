/**
 * AI Town 前端主入口
 * 初始化 Phaser 游戏引擎
 */
import Phaser from 'phaser';
import { BootScene } from './scenes/BootScene';
import { PreloadScene } from './scenes/PreloadScene';
import { WorldScene } from './scenes/WorldScene';
import { UIScene } from './scenes/UIScene';

const config: Phaser.Types.Core.GameConfig = {
  type: Phaser.AUTO,
  parent: 'game-container',
  width: 1280,
  height: 720,
  backgroundColor: '#2d2d2d',
  // 像素美术需要 nearest-neighbor 采样，避免缩放时糊边
  pixelArt: true,
  scene: [BootScene, PreloadScene, WorldScene, UIScene],
  physics: {
    default: 'arcade',
    arcade: {
      gravity: { x: 0, y: 0 },
      debug: false,
    },
  },
  scale: {
    mode: Phaser.Scale.FIT,
    autoCenter: Phaser.Scale.CENTER_BOTH,
  },
};

// 创建游戏实例
const game = new Phaser.Game(config);

// 隐藏加载提示
window.addEventListener('load', () => {
  const loading = document.getElementById('loading');
  if (loading) {
    loading.style.display = 'none';
  }
});

// 全屏提示
console.log('按 F11 进入全屏模式以获得最佳体验');

export default game;
