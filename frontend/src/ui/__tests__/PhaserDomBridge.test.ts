import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PhaserDomBridge } from '../PhaserDomBridge';
import type { UiRenderProjection } from '../../types/ui_projection';

type Listener = (event: FakeEvent) => void;

class FakeEvent {
  public defaultPrevented = false;

  constructor(
    public readonly type: string,
    public readonly key = '',
    public readonly shiftKey = false,
  ) {}

  preventDefault(): void {
    this.defaultPrevented = true;
  }
}

class FakeElement {
  public readonly children: FakeElement[] = [];
  public parentElement: FakeElement | null = null;
  public className = '';
  public id = '';
  public textContent: string | null = null;
  public disabled = false;
  public clientWidth = 0;
  public clientHeight = 0;
  public readonly style = {
    values: new Map<string, string>(),
    setProperty: (name: string, value: string): void => {
      this.style.values.set(name, value);
    },
    removeProperty: (name: string): void => {
      this.style.values.delete(name);
    },
    getPropertyValue: (name: string): string =>
      this.style.values.get(name) ?? '',
  };
  public readonly classList = {
    values: new Set<string>(),
    toggle: (name: string, force?: boolean): boolean => {
      const enabled = force ?? !this.classList.values.has(name);
      if (enabled) this.classList.values.add(name);
      else this.classList.values.delete(name);
      return enabled;
    },
    contains: (name: string): boolean => this.classList.values.has(name),
  };
  public requestFullscreen = vi.fn(async (): Promise<void> => {
    fakeDocument.fullscreenElement = this;
  });
  private attributes = new Map<string, string>();
  private listeners = new Map<string, Set<Listener>>();

  constructor(public readonly tagName = 'div') {}

  set innerHTML(_value: string) {
    this.replaceChildren();
  }

  get innerHTML(): string {
    return '';
  }

  appendChild(child: FakeElement): FakeElement {
    child.parentElement = this;
    this.children.push(child);
    return child;
  }

  replaceChildren(...children: FakeElement[]): void {
    for (const child of this.children) {
      child.parentElement = null;
    }
    this.children.length = 0;
    for (const child of children) {
      this.appendChild(child);
    }
  }

  remove(): void {
    const parent = this.parentElement;
    if (!parent) return;
    const index = parent.children.indexOf(this);
    if (index >= 0) parent.children.splice(index, 1);
    this.parentElement = null;
  }

  setAttribute(name: string, value: string): void {
    this.attributes.set(name, value);
  }

  addEventListener(type: string, listener: Listener): void {
    const listeners = this.listeners.get(type) ?? new Set();
    listeners.add(listener);
    this.listeners.set(type, listeners);
  }

  removeEventListener(type: string, listener: Listener): void {
    this.listeners.get(type)?.delete(listener);
  }

  dispatchEvent(event: FakeEvent): boolean {
    for (const listener of this.listeners.get(event.type) ?? []) {
      listener(event);
    }
    return !event.defaultPrevented;
  }

  contains(candidate: FakeElement): boolean {
    return candidate === this || this.children.some(child => child.contains(candidate));
  }

  querySelector(selector: string): FakeElement | null {
    return this.querySelectorAll(selector)[0] ?? null;
  }

  querySelectorAll(selector: string): FakeElement[] {
    const matches = (element: FakeElement): boolean => {
      if (selector.includes('button') && element.tagName === 'button') {
        return !selector.includes(':not([disabled])') || !element.disabled;
      }
      if (selector.includes('[data-autofocus]')) {
        return element.attributes.has('data-autofocus');
      }
      return false;
    };
    return this.children.flatMap(child => [
      ...(matches(child) ? [child] : []),
      ...child.querySelectorAll(selector),
    ]);
  }

  focus(): void {
    fakeDocument.activeElement = this;
  }
}

class FakeDocument {
  public activeElement: FakeElement | null = null;
  public fullscreenElement: FakeElement | null = null;
  public exitFullscreen = vi.fn(async (): Promise<void> => {
    this.fullscreenElement = null;
  });
  private elements = new Map<string, FakeElement>();
  private listeners = new Map<string, Set<Listener>>();

  createElement(tagName: string): FakeElement {
    return new FakeElement(tagName);
  }

  getElementById(id: string): FakeElement | null {
    return this.elements.get(id) ?? null;
  }

  register(id: string, element: FakeElement): void {
    element.id = id;
    this.elements.set(id, element);
  }

  contains(element: FakeElement): boolean {
    return [...this.elements.values()].some(root => root.contains(element));
  }

  addEventListener(type: string, listener: Listener): void {
    const listeners = this.listeners.get(type) ?? new Set();
    listeners.add(listener);
    this.listeners.set(type, listeners);
  }

  removeEventListener(type: string, listener: Listener): void {
    this.listeners.get(type)?.delete(listener);
  }

  dispatchEvent(event: FakeEvent): boolean {
    for (const listener of this.listeners.get(event.type) ?? []) {
      listener(event);
    }
    return !event.defaultPrevented;
  }

  listenerCount(type: string): number {
    return this.listeners.get(type)?.size ?? 0;
  }
}

let fakeDocument: FakeDocument;
let resizeObserverCallback: (() => void) | null;
let resizeObserverDisconnect: ReturnType<typeof vi.fn>;

class FakeResizeObserver {
  public readonly disconnect = resizeObserverDisconnect;

  constructor(callback: () => void) {
    resizeObserverCallback = callback;
  }

  observe(): void {}
}

function projection(revision: number, modal: boolean): UiRenderProjection {
  return {
    protocol_version: 'ui.v1',
    world_id: 'world',
    revision,
    game_time: 0,
    hud: {
      player_name: 'Player',
      season: 'Spring',
      weather: 'Clear',
      time_display: '08:00',
    },
    dialogue: modal
      ? {
          conversation_id: 'conversation',
          speaker_name: 'Mayor',
          speaker_entity_id: 'mayor',
          text: 'Welcome',
          options: [{ option_id: 'ok', text: 'OK', enabled: true }],
        }
      : undefined,
  };
}

beforeEach(() => {
  fakeDocument = new FakeDocument();
  resizeObserverCallback = null;
  resizeObserverDisconnect = vi.fn();
  const overlay = new FakeElement();
  const gameShell = new FakeElement();
  gameShell.clientWidth = 1280;
  gameShell.clientHeight = 720;
  fakeDocument.register('ui-overlay', overlay);
  fakeDocument.register('game-shell', gameShell);
  fakeDocument.register('fullscreen-toggle', new FakeElement('button'));
  vi.stubGlobal('document', fakeDocument);
  vi.stubGlobal('HTMLElement', FakeElement);
  vi.stubGlobal('Node', FakeElement);
  vi.stubGlobal('KeyboardEvent', FakeEvent);
  vi.stubGlobal('ResizeObserver', FakeResizeObserver);
  vi.stubGlobal('requestAnimationFrame', (callback: () => void) => {
    callback();
    return 1;
  });
  vi.stubGlobal('cancelAnimationFrame', vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('PhaserDomBridge lifecycle', () => {
  it('applies 720p and 1080p layout values to the real overlay', () => {
    const layouts: Array<{ width: number; height: number }> = [];
    const shell = fakeDocument.getElementById('game-shell')!;
    const overlay = fakeDocument.getElementById('ui-overlay')!;
    const bridge = new PhaserDomBridge(
      undefined,
      undefined,
      layout => layouts.push(layout),
    );

    expect(overlay.style.getPropertyValue('--ui-safe-area')).toBe('16px');
    expect(overlay.style.getPropertyValue('--ui-text-scale')).toBe('1');
    expect(overlay.classList.contains('ui-layout-compact')).toBe(false);

    shell.clientWidth = 1920;
    shell.clientHeight = 1080;
    resizeObserverCallback?.();

    expect(overlay.style.getPropertyValue('--ui-safe-area')).toBe('24px');
    expect(overlay.style.getPropertyValue('--ui-text-scale')).toBe('1.25');
    expect(layouts.at(-1)).toEqual({ width: 1920, height: 1080 });

    shell.clientWidth = 1279;
    resizeObserverCallback?.();
    expect(overlay.classList.contains('ui-layout-compact')).toBe(true);
    bridge.dispose();
  });

  it('requests and exits fullscreen only from the fullscreen button click', async () => {
    const shell = fakeDocument.getElementById('game-shell')!;
    const button = fakeDocument.getElementById('fullscreen-toggle')!;
    const bridge = new PhaserDomBridge();

    expect(shell.requestFullscreen).not.toHaveBeenCalled();
    button.dispatchEvent(new FakeEvent('click'));
    await Promise.resolve();
    expect(shell.requestFullscreen).toHaveBeenCalledTimes(1);

    button.dispatchEvent(new FakeEvent('click'));
    await Promise.resolve();
    expect(fakeDocument.exitFullscreen).toHaveBeenCalledTimes(1);
    bridge.dispose();
  });

  it('removes resize and fullscreen listeners during dispose', () => {
    const button = fakeDocument.getElementById('fullscreen-toggle')!;
    const shell = fakeDocument.getElementById('game-shell')!;
    const bridge = new PhaserDomBridge();

    bridge.dispose();
    button.dispatchEvent(new FakeEvent('click'));

    expect(shell.requestFullscreen).not.toHaveBeenCalled();
    expect(resizeObserverDisconnect).toHaveBeenCalledTimes(1);
    expect(fakeDocument.listenerCount('fullscreenchange')).toBe(0);
  });

  it('closes an existing modal before a HUD-only patch and restores world input', () => {
    const allowedChanges: boolean[] = [];
    const bridge = new PhaserDomBridge(
      undefined,
      allowed => allowedChanges.push(allowed),
    );

    bridge.patch(projection(1, true));
    expect(fakeDocument.listenerCount('keydown')).toBe(1);
    expect(allowedChanges.at(-1)).toBe(false);

    bridge.patch(projection(2, false));

    expect(fakeDocument.listenerCount('keydown')).toBe(0);
    expect(allowedChanges.at(-1)).toBe(true);
  });

  it('replaces repeated modal patches without accumulating document listeners', () => {
    const bridge = new PhaserDomBridge();

    bridge.patch(projection(1, true));
    bridge.patch(projection(2, true));

    expect(fakeDocument.listenerCount('keydown')).toBe(1);
    fakeDocument.dispatchEvent(new FakeEvent('keydown', 'Escape'));
    expect(fakeDocument.listenerCount('keydown')).toBe(0);
  });

  it('dispose is idempotent and removes modal and document listeners', () => {
    const allowedChanges: boolean[] = [];
    const bridge = new PhaserDomBridge(
      undefined,
      allowed => allowedChanges.push(allowed),
    );
    bridge.patch(projection(1, true));

    bridge.dispose();
    bridge.dispose();

    expect(fakeDocument.listenerCount('keydown')).toBe(0);
    expect(allowedChanges.at(-1)).toBe(true);
  });

  it('does not emit a queued focus update after dispose', async () => {
    const allowedChanges: boolean[] = [];
    const overlay = fakeDocument.getElementById('ui-overlay')!;
    const bridge = new PhaserDomBridge(
      undefined,
      allowed => allowedChanges.push(allowed),
    );

    overlay.dispatchEvent(new FakeEvent('focusout'));
    bridge.dispose();
    const changesAfterDispose = allowedChanges.length;
    await Promise.resolve();

    expect(allowedChanges).toHaveLength(changesAfterDispose);
  });
});
