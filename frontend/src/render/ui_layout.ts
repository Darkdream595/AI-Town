export interface ViewportSize {
  width: number;
  height: number;
}

export const FULLSCREEN_TARGET_ID = 'game-shell';
export const MAX_TEXT_SCALE = 1.25;

export function computeSafeArea(viewport: ViewportSize): number {
  return viewport.width >= 1920 && viewport.height >= 1080 ? 24 : 16;
}

export function isCompactLayout(viewport: ViewportSize): boolean {
  return viewport.width < 1280 || viewport.height < 720;
}

export function clampTextScale(scale: number): number {
  if (!Number.isFinite(scale)) {
    return 1;
  }
  return Math.min(MAX_TEXT_SCALE, Math.max(1, scale));
}

export function computeTextScale(viewport: ViewportSize): number {
  const widthScale = viewport.width / 1280;
  const heightScale = viewport.height / 720;
  return clampTextScale(Math.min(widthScale, heightScale));
}

export class UiInputGate {
  private domFocusActive = false;
  private modalActive = false;

  setDomFocusActive(active: boolean): void {
    this.domFocusActive = active;
  }

  setModalActive(active: boolean): void {
    this.modalActive = active;
  }

  isWorldInputAllowed(): boolean {
    return !this.domFocusActive && !this.modalActive;
  }

  reset(): void {
    this.domFocusActive = false;
    this.modalActive = false;
  }
}

export type FullscreenDecision =
  | { action: 'request'; targetId: string }
  | { action: 'exit'; targetId: string }
  | { action: 'reject_no_user_gesture'; targetId: string };

export function planFullscreenRequest(
  hasUserGesture: boolean,
  currentlyFullscreen: boolean,
): FullscreenDecision {
  if (!hasUserGesture) {
    return {
      action: 'reject_no_user_gesture',
      targetId: FULLSCREEN_TARGET_ID,
    };
  }
  return {
    action: currentlyFullscreen ? 'exit' : 'request',
    targetId: FULLSCREEN_TARGET_ID,
  };
}
