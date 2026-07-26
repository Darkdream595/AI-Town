/**
 * EventBus - Scene 间通信总线
 *
 * 用于 WorldScene、UIScene 和其他模块之间的事件通信
 * 使用简单的 EventEmitter 实现，避免直接依赖 Phaser
 */

type EventHandler = (...args: any[]) => void;

class EventBusImpl {
  private listeners: Map<string, Set<EventHandler>> = new Map();

  on(event: string, handler: EventHandler): void {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event)!.add(handler);
  }

  off(event: string, handler: EventHandler): void {
    const handlers = this.listeners.get(event);
    if (handlers) {
      handlers.delete(handler);
    }
  }

  emit(event: string, ...args: any[]): void {
    const handlers = this.listeners.get(event);
    if (handlers) {
      handlers.forEach(handler => handler(...args));
    }
  }

  clear(): void {
    this.listeners.clear();
  }
}

// 单例实例
export const EventBus = new EventBusImpl();

// 事件类型定义
export const Events = {
  // 渲染帧更新
  RENDER_FRAME_UPDATE: 'render:frame:update',

  // 渲染事件
  RENDER_EVENT: 'render:event',

  // HUD 更新
  HUD_UPDATE: 'hud:update',

  // 对话事件
  DIALOGUE_SHOW: 'dialogue:show',
  DIALOGUE_HIDE: 'dialogue:hide',

  // 场景切换
  SCENE_LOAD_START: 'scene:load:start',
  SCENE_LOAD_COMPLETE: 'scene:load:complete',
  SCENE_UNLOAD: 'scene:unload',

  // 调试事件
  DEBUG_TOGGLE: 'debug:toggle',
} as const;
