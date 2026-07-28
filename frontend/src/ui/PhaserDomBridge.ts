/**
 * Phaser DOM Bridge
 *
 * 符合 DOC-RENDER-009:58 规范：
 * - 通过 keyed DOM patch 更新 #ui-overlay
 * - Modal 打开时保存 document.activeElement
 * - 实现 Tab/Shift+Tab focus trap
 * - Modal 关闭时恢复焦点
 */

import type { UiRenderProjection, DialogueProjection } from '../types/ui_projection';
import {
  UiInputGate,
  computeSafeArea,
  computeTextScale,
  isCompactLayout,
  planFullscreenRequest,
} from '../render/ui_layout';

export interface UiLayoutTransaction {
  width: number;
  height: number;
}

export class PhaserDomBridge {
  private overlayElement: HTMLElement;
  private gameShellElement: HTMLElement;
  private fullscreenButton: HTMLElement | null;
  private resizeObserver: ResizeObserver | null = null;
  private layoutFrame: number | null = null;
  private currentRevision: number = -1;
  private savedActiveElement: Element | null = null;
  private currentModal: HTMLElement | null = null;
  private focusTrapHandler: ((event: KeyboardEvent) => void) | null = null;
  private escapeHandler: ((event: KeyboardEvent) => void) | null = null;
  private disposed = false;
  private readonly handleResize = (): void => {
    this.scheduleLayout();
  };
  private readonly handleFullscreenChange = (): void => {
    this.updateFullscreenControl();
    this.scheduleLayout();
  };
  private readonly handleFullscreenToggle = (): void => {
    void this.toggleFullscreenFromUserGesture();
  };
  private readonly handleFocusIn = (): void => {
    this.inputGate.setDomFocusActive(true);
    this.notifyInputGate();
  };
  private readonly handleFocusOut = (): void => {
    queueMicrotask(() => {
      if (this.disposed) {
        return;
      }
      const activeElement = document.activeElement;
      const focusRemainsInside =
        activeElement instanceof Node &&
        this.overlayElement.contains(activeElement);
      this.inputGate.setDomFocusActive(focusRemainsInside);
      this.notifyInputGate();
    });
  };

  constructor(
    private readonly inputGate = new UiInputGate(),
    private readonly onWorldInputAllowedChanged?: (allowed: boolean) => void,
    private readonly onLayoutChanged?: (layout: UiLayoutTransaction) => void,
  ) {
    const overlay = document.getElementById('ui-overlay');
    if (!overlay) {
      throw new Error('#ui-overlay not found in DOM');
    }
    this.overlayElement = overlay;
    const gameShell = document.getElementById('game-shell');
    if (!gameShell) {
      throw new Error('#game-shell not found in DOM');
    }
    this.gameShellElement = gameShell;
    this.fullscreenButton = document.getElementById('fullscreen-toggle');
    this.overlayElement.addEventListener('focusin', this.handleFocusIn);
    this.overlayElement.addEventListener('focusout', this.handleFocusOut);
    this.fullscreenButton?.addEventListener(
      'click',
      this.handleFullscreenToggle,
    );
    document.addEventListener(
      'fullscreenchange',
      this.handleFullscreenChange,
    );
    if (typeof ResizeObserver !== 'undefined') {
      this.resizeObserver = new ResizeObserver(this.handleResize);
      this.resizeObserver.observe(this.gameShellElement);
    }
    this.applyLayout();
    this.updateFullscreenControl();
  }

  private scheduleLayout(): void {
    if (this.disposed || this.layoutFrame !== null) {
      return;
    }
    let completedSynchronously = false;
    const frame = requestAnimationFrame(() => {
      completedSynchronously = true;
      this.layoutFrame = null;
      this.applyLayout();
    });
    if (!completedSynchronously) {
      this.layoutFrame = frame;
    }
  }

  private applyLayout(): void {
    const viewport = {
      width: this.gameShellElement.clientWidth,
      height: this.gameShellElement.clientHeight,
    };
    this.overlayElement.style.setProperty(
      '--ui-safe-area',
      `${computeSafeArea(viewport)}px`,
    );
    this.overlayElement.style.setProperty(
      '--ui-text-scale',
      String(computeTextScale(viewport)),
    );
    this.overlayElement.classList.toggle(
      'ui-layout-compact',
      isCompactLayout(viewport),
    );
    this.onLayoutChanged?.(viewport);
  }

  private async toggleFullscreenFromUserGesture(): Promise<void> {
    const decision = planFullscreenRequest(
      true,
      document.fullscreenElement === this.gameShellElement,
    );
    try {
      if (decision.action === 'request') {
        await this.gameShellElement.requestFullscreen();
      } else if (decision.action === 'exit') {
        await document.exitFullscreen();
      }
    } catch {
      this.fullscreenButton?.setAttribute(
        'data-fullscreen-status',
        'failed',
      );
    }
  }

  private updateFullscreenControl(): void {
    const fullscreen =
      document.fullscreenElement === this.gameShellElement;
    this.fullscreenButton?.setAttribute(
      'aria-pressed',
      String(fullscreen),
    );
    if (this.fullscreenButton) {
      this.fullscreenButton.textContent = fullscreen
        ? '退出全屏'
        : '进入全屏';
    }
  }

  /**
   * 更新 UI projection
   *
   * @param projection UI 投影数据
   */
  public patch(projection: UiRenderProjection): void {
    if (this.disposed) {
      return;
    }

    // RULE: 只接受同 Revision 或更高 Revision 的 projection
    if (projection.revision < this.currentRevision) {
      console.warn(`Rejected stale UI projection: ${projection.revision} < ${this.currentRevision}`);
      return;
    }

    this.currentRevision = projection.revision;

    // A projection replaces the complete DOM projection. Close the previous
    // modal first so its document listeners and input-gate state cannot outlive it.
    this.closeModal();

    // 清空并重建（简化版 keyed patch，真实实现应该用 diff）
    this.overlayElement.innerHTML = '';

    // 渲染 HUD
    this.renderHUD(projection.hud);

    // 渲染对话框（如果存在）
    if (projection.dialogue) {
      this.renderDialogue(projection.dialogue);
    }

    // 渲染镇长面板（如果存在）
    if (projection.mayor_panel) {
      this.renderMayorPanel(projection.mayor_panel);
    }
  }

  private renderHUD(hud: any): void {
    const hudContainer = document.createElement('div');
    hudContainer.className = 'hud-container';
    hudContainer.setAttribute('role', 'banner');

    hudContainer.innerHTML = `
      <div class="hud-item">
        <span class="hud-label">玩家：</span>
        <span class="hud-value">${this.escapeHTML(hud.player_name || '未知')}</span>
      </div>
      <div class="hud-item">
        <span class="hud-label">时间：</span>
        <span class="hud-value">${this.escapeHTML(hud.time_display || '--:--')}</span>
      </div>
      <div class="hud-item">
        <span class="hud-label">天气：</span>
        <span class="hud-value">${this.escapeHTML(hud.weather || '未知')}</span>
      </div>
      <div class="hud-item">
        <span class="hud-label">季节：</span>
        <span class="hud-value">${this.escapeHTML(hud.season || '未知')}</span>
      </div>
    `;

    this.overlayElement.appendChild(hudContainer);
  }

  private renderDialogue(dialogue: DialogueProjection): void {
    const dialogueBox = document.createElement('div');
    dialogueBox.className = 'dialogue-box';
    dialogueBox.setAttribute('role', 'dialog');
    dialogueBox.setAttribute('aria-labelledby', 'dialogue-speaker');

    const speaker = document.createElement('div');
    speaker.id = 'dialogue-speaker';
    speaker.className = 'dialogue-speaker';
    speaker.textContent = dialogue.speaker_name;

    const text = document.createElement('div');
    text.className = 'dialogue-text';
    text.textContent = dialogue.text;

    dialogueBox.appendChild(speaker);
    dialogueBox.appendChild(text);

    // 对话选项
    if (dialogue.options && dialogue.options.length > 0) {
      const optionsContainer = document.createElement('div');
      optionsContainer.className = 'dialogue-options';

      dialogue.options.forEach((option, index) => {
        const button = document.createElement('button');
        button.className = 'dialogue-option';
        button.textContent = option.text;
        button.disabled = !option.enabled;
        button.setAttribute('data-option-id', option.option_id);

        // 第一个按钮自动聚焦
        if (index === 0 && option.enabled) {
          button.setAttribute('data-autofocus', 'true');
        }

        button.addEventListener('click', () => {
          this.handleDialogueOption(option.option_id);
        });

        optionsContainer.appendChild(button);
      });

      dialogueBox.appendChild(optionsContainer);
    }

    // 关闭按钮
    const closeButton = document.createElement('button');
    closeButton.className = 'dialogue-close';
    closeButton.textContent = '关闭 (Esc)';
    closeButton.addEventListener('click', () => {
      this.closeModal();
    });
    dialogueBox.appendChild(closeButton);

    this.overlayElement.appendChild(dialogueBox);
    this.openModal(dialogueBox);
  }

  private renderMayorPanel(panel: any): void {
    const mayorBox = document.createElement('div');
    mayorBox.className = 'mayor-panel';
    mayorBox.setAttribute('role', 'dialog');
    mayorBox.setAttribute('aria-label', '镇长面板');

    mayorBox.innerHTML = `
      <h2 class="mayor-title">镇长面板</h2>
      <div class="mayor-stats">
        <div>预算：${panel.budget_copper} 铜羽</div>
        <div>人口：${panel.population}</div>
        <div>满意度：${panel.satisfaction}%</div>
      </div>
      <div class="mayor-commands">
        ${(panel.available_commands || []).map((cmd: any) => `
          <button class="mayor-command" data-command-id="${cmd.command_id}">
            ${this.escapeHTML(cmd.display_name)} (${cmd.cost_copper} 铜羽)
          </button>
        `).join('')}
      </div>
      <button class="mayor-close">关闭 (Esc)</button>
    `;

    this.overlayElement.appendChild(mayorBox);
    this.openModal(mayorBox);
  }

  /**
   * 打开 Modal，保存焦点并设置 focus trap
   */
  private openModal(modalElement: HTMLElement): void {
    if (this.currentModal) {
      this.closeModal();
    }

    // 保存当前焦点元素
    this.savedActiveElement = document.activeElement;
    this.currentModal = modalElement;
    this.inputGate.setModalActive(true);
    this.notifyInputGate();

    // 聚焦第一个可操作元素
    const firstFocusable = modalElement.querySelector('[data-autofocus], button:not([disabled]), input, textarea, select') as HTMLElement;
    if (firstFocusable) {
      setTimeout(() => firstFocusable.focus(), 0);
    }

    // 设置 focus trap
    this.setupFocusTrap(modalElement);

    // Esc 关闭
    this.escapeHandler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        this.closeModal();
      }
    };
    document.addEventListener('keydown', this.escapeHandler);
  }

  /**
   * 关闭 Modal，恢复焦点
   */
  private closeModal(): void {
    if (this.currentModal) {
      if (this.focusTrapHandler) {
        this.currentModal.removeEventListener('keydown', this.focusTrapHandler);
        this.focusTrapHandler = null;
      }
      this.currentModal.remove();
      this.currentModal = null;
    }
    if (this.escapeHandler) {
      document.removeEventListener('keydown', this.escapeHandler);
      this.escapeHandler = null;
    }
    this.inputGate.setModalActive(false);
    this.inputGate.setDomFocusActive(false);
    this.notifyInputGate();

    // 恢复焦点
    if (this.savedActiveElement && this.savedActiveElement instanceof HTMLElement) {
      // 检查元素是否仍在 DOM 中
      if (document.contains(this.savedActiveElement)) {
        this.savedActiveElement.focus();
      } else {
        const gameShell = document.getElementById('game-shell');
        if (gameShell) {
          gameShell.focus();
        }
      }
      this.savedActiveElement = null;
    }
  }

  /**
   * 设置 Focus Trap（Tab/Shift+Tab 循环）
   */
  private setupFocusTrap(container: HTMLElement): void {
    const focusableSelector = 'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), a[href]';

    this.focusTrapHandler = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return;

      const focusableElements = Array.from(container.querySelectorAll(focusableSelector)) as HTMLElement[];
      if (focusableElements.length === 0) return;

      const firstElement = focusableElements[0];
      const lastElement = focusableElements[focusableElements.length - 1];

      if (e.shiftKey) {
        // Shift+Tab：从第一个循环到最后一个
        if (document.activeElement === firstElement) {
          e.preventDefault();
          lastElement.focus();
        }
      } else {
        // Tab：从最后一个循环到第一个
        if (document.activeElement === lastElement) {
          e.preventDefault();
          firstElement.focus();
        }
      }
    };

    container.addEventListener('keydown', this.focusTrapHandler);
  }

  private handleDialogueOption(optionId: string): void {
    console.log('Dialogue option selected:', optionId);
    // TODO: 发送 Client Command 到后端
    this.closeModal();
  }

  private escapeHTML(str: string): string {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  public dispose(): void {
    if (this.disposed) {
      return;
    }
    this.disposed = true;
    this.closeModal();
    this.overlayElement.removeEventListener('focusin', this.handleFocusIn);
    this.overlayElement.removeEventListener('focusout', this.handleFocusOut);
    this.fullscreenButton?.removeEventListener(
      'click',
      this.handleFullscreenToggle,
    );
    document.removeEventListener(
      'fullscreenchange',
      this.handleFullscreenChange,
    );
    this.resizeObserver?.disconnect();
    this.resizeObserver = null;
    if (this.layoutFrame !== null) {
      cancelAnimationFrame(this.layoutFrame);
      this.layoutFrame = null;
    }
    this.inputGate.reset();
    this.notifyInputGate();
    this.overlayElement.replaceChildren();
    this.fullscreenButton = null;
  }

  private notifyInputGate(): void {
    this.onWorldInputAllowedChanged?.(
      this.inputGate.isWorldInputAllowed(),
    );
  }
}
