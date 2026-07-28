import { describe, expect, it, vi } from 'vitest';

vi.mock('phaser', () => {
  class Scene {
    constructor(_configuration?: unknown) {}
  }
  return { default: { Scene } };
});

vi.mock('../../utils/SpriteLoader', () => ({
  SpriteLoader: {
    getSupportedCharacters: () => [],
    loadCharacter: vi.fn(),
  },
}));

import { PreloadScene } from '../PreloadScene';

describe('PreloadScene runtime assets', () => {
  it('queues the Crown Creek ground and stable resident fallback textures', () => {
    const scene = new PreloadScene();
    const image = vi.fn();
    Object.defineProperty(scene, 'load', {
      configurable: true,
      value: {
        image,
        json: vi.fn(),
      },
    });

    (scene as any).loadTestAssets();

    expect(image).toHaveBeenCalledWith(
      'crown_creek_town_base',
      'assets/maps/crown_creek_town_base.png',
    );
    expect(image).toHaveBeenCalledWith(
      'asset.fallback.resident_silhouette',
      'assets/sprites/extracted/human_farmer/human_farmer_idle_south_0.png',
    );
  });
});
