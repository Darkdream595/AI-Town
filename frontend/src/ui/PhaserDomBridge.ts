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

export class PhaserDomBridge {
  private overlayElement: HTMLElement;
  private currentRevision: number = -1;
  private savedActiveElement: Element | null = null;
  private currentModal: HTMLElement | null = null;

  constructor() {
    const overlay = document.getElementById('ui-overlay');
    if (!overlay) {
      throw new Error('#ui-overlay not found in DOM');
    }
    this.overlayElement = overlay;
  }

  /**
   * 更新 UI projection
   *
   * @param projection UI 投影数据
   */
  public patch(projection: UiRenderProjection): void {
    // RULE: 只接受同 Revision 或更高 Revision 的 projection
    if (projection.revision < this.currentRevision) {
      console.warn(`Rejected stale UI projection: ${projection.revision} < ${this.currentRevision}`);
      return;
    }

    this.currentRevision = projection.revision;

    // 清空并重建（简化版 keyed patch，真实实现应该用 diff）
    this.overlayElement.innerHTML = '';

    // 渲染 HUD
    this.renderHUD(projection.hud, projection.game_time);

    // 渲染对话框（如果存在）
    if (projection.dialogue) {
      this.renderDialogue(projection.dialogue);
    }

    // 渲染镇长面板（如果存在）
    if (projection.mayor_panel) {
      this.renderMayorPanel(projection.mayor_panel);
    }
  }

  private renderHUD(hud: any, gameTime: number): void {
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
    // 保存当前焦点元素
    this.savedActiveElement = document.activeElement;
    this.currentModal = modalElement;

    // 聚焦第一个可操作元素
    const firstFocusable = modalElement.querySelector('[data-autofocus], button:not([disabled]), input, textarea, select') as HTMLElement;
    if (firstFocusable) {
      setTimeout(() => firstFocusable.focus(), 0);
    }

    // 设置 focus trap
    this.setupFocusTrap(modalElement);

    // Esc 关闭
    const escapeHandler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        this.closeModal();
        document.removeEventListener('keydown', escapeHandler);
      }
    };
    document.addEventListener('keydown', escapeHandler);
  }

  /**
   * 关闭 Modal，恢复焦点
   */
  private closeModal(): void {
    if (this.currentModal) {
      this.currentModal.remove();
      this.currentModal = null;
    }

    // 恢复焦点
    if (this.savedActiveElement && this.savedActiveElement instanceof HTMLElement) {
      // 检查元素是否仍在 DOM 中
      if (document.contains(this.savedActiveElement)) {
        this.savedActiveElement.focus();
      } else {
        // 元素已不存在，聚焦 #game-container
        const gameContainer = document.getElementById('game-container');
        if (gameContainer) {
          gameContainer.focus();
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

    const handleTab = (e: KeyboardEvent) => {
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

    container.addEventListener('keydown', handleTab);
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
}
