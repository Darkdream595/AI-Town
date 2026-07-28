import { describe, expect, it } from 'vitest';
import {
  FULLSCREEN_TARGET_ID,
  UiInputGate,
  clampTextScale,
  computeTextScale,
  computeSafeArea,
  isCompactLayout,
  planFullscreenRequest,
} from '../ui_layout';

describe('TEST-RENDER-009 UI layout and input gate', () => {
  it('uses 16px safe area at 720p and 24px at 1080p', () => {
    expect(computeSafeArea({ width: 1280, height: 720 })).toBe(16);
    expect(computeSafeArea({ width: 1920, height: 1080 })).toBe(24);
  });

  it('uses compact layout below the 1280x720 minimum', () => {
    expect(isCompactLayout({ width: 1279, height: 720 })).toBe(true);
    expect(isCompactLayout({ width: 1280, height: 719 })).toBe(true);
    expect(isCompactLayout({ width: 1280, height: 720 })).toBe(false);
    expect(clampTextScale(2)).toBe(1.25);
  });

  it('scales text from 720p to 1080p without exceeding 1.25', () => {
    expect(computeTextScale({ width: 1280, height: 720 })).toBe(1);
    expect(computeTextScale({ width: 1920, height: 1080 })).toBe(1.25);
    expect(computeTextScale({ width: 3840, height: 2160 })).toBe(1.25);
  });

  it('suppresses world input while DOM focus or a modal is active', () => {
    const gate = new UiInputGate();
    expect(gate.isWorldInputAllowed()).toBe(true);
    gate.setDomFocusActive(true);
    expect(gate.isWorldInputAllowed()).toBe(false);
    gate.setDomFocusActive(false);
    gate.setModalActive(true);
    expect(gate.isWorldInputAllowed()).toBe(false);
    gate.reset();
    expect(gate.isWorldInputAllowed()).toBe(true);
  });

  it('only targets game-shell from a user gesture', () => {
    expect(FULLSCREEN_TARGET_ID).toBe('game-shell');
    expect(planFullscreenRequest(false, false)).toEqual({
      action: 'reject_no_user_gesture',
      targetId: FULLSCREEN_TARGET_ID,
    });
    expect(planFullscreenRequest(true, false)).toEqual({
      action: 'request',
      targetId: FULLSCREEN_TARGET_ID,
    });
    expect(planFullscreenRequest(true, true).action).toBe('exit');
  });
});
