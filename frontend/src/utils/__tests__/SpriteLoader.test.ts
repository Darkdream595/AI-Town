import { describe, expect, it, vi } from 'vitest';
import type Phaser from 'phaser';
import type { SpriteCatalogSpec } from '../../render/sprite_lint';
import { SpriteLoader } from '../SpriteLoader';

function validSpec(assetId = 'sprite.resident.test'): SpriteCatalogSpec {
  return {
    asset_id: assetId,
    directions: ['north', 'east', 'south', 'west'],
    walk_frames: {
      north: ['n0', 'n1', 'n2', 'n3', 'n4', 'n5'],
      east: ['e0', 'e1', 'e2', 'e3', 'e4', 'e5'],
      south: ['s0', 's1', 's2', 's3', 's4', 's5'],
      west: ['w0', 'w1', 'w2', 'w3', 'w4', 'w5'],
    },
    frame_size_px: { width: 32, height: 48 },
    anchor: { x: 0.5, y: 1 },
  };
}

function createScene(characterName: string) {
  const sprite = {
    setOrigin: vi.fn(),
    play: vi.fn(),
  };
  const atlasConfig = {
    frames: [
      {
        filename: 'idle_south_0',
        frame: { x: 0, y: 0, w: 32, h: 48 },
        rotated: false,
        trimmed: false,
        spriteSourceSize: { x: 0, y: 0, w: 32, h: 48 },
        sourceSize: { w: 32, h: 48 },
        pivot: { x: 0.5, y: 1 },
      },
    ],
    meta: {
      app: 'test',
      version: '1',
      image: `${characterName}.png`,
      format: 'RGBA8888',
      size: { w: 32, h: 48 },
      scale: 1,
    },
  };
  const animationConfig = {
    idle_south: {
      frames: ['idle_south_0'],
      frameRate: 4,
      repeat: -1,
    },
  };
  const scene = {
    cache: {
      json: {
        get: vi.fn((key: string) => {
          if (key === `${characterName}_atlas`) return atlasConfig;
          if (key === `${characterName}_animations`) return animationConfig;
          return undefined;
        }),
      },
    },
    load: {
      image: vi.fn(),
      once: vi.fn(),
      start: vi.fn(),
    },
    anims: {
      exists: vi.fn(),
      create: vi.fn(),
    },
    textures: {
      exists: vi.fn(() => true),
    },
    add: {
      sprite: vi.fn(() => sprite),
    },
  };

  return {
    scene: scene as unknown as Phaser.Scene,
    sprite,
    loadImage: scene.load.image,
    loadStart: scene.load.start,
    animationExists: scene.anims.exists,
    textureExists: scene.textures.exists,
  };
}

describe('SpriteLoader linted catalog integration', () => {
  it.each([
    ['sprite.resident.human_farmer', 'human_farmer'],
    ['sprite.resident.elf_mage', 'elf_mage'],
    ['sprite.resident.unknown', null],
  ])('maps stable asset id %s to a loaded character key', (assetId, expected) => {
    expect(SpriteLoader.resolveCharacterName(assetId)).toBe(expected);
  });

  it('creates a character sprite for a stable asset id instead of always using fallback', () => {
    const fixture = createScene('human_farmer');

    SpriteLoader.createSpriteForAsset(
      fixture.scene,
      10,
      20,
      'sprite.resident.human_farmer',
    );

    expect(fixture.scene.add.sprite).toHaveBeenCalledWith(
      10,
      20,
      'human_farmer_idle_south_0',
    );
  });

  it('uses the stable fallback when a mapped character texture was not loaded', () => {
    const fixture = createScene('human_farmer');
    fixture.textureExists.mockReturnValue(false);

    SpriteLoader.createSpriteForAsset(
      fixture.scene,
      10,
      20,
      'sprite.resident.human_farmer',
    );

    expect(fixture.scene.add.sprite).toHaveBeenCalledWith(
      10,
      20,
      'asset.fallback.resident_silhouette',
    );
  });

  it('allows a valid registered sprite spec into the existing loading and creation path', () => {
    const characterName = 'valid_catalog_character';
    const registration = SpriteLoader.registerCharacterCatalog(
      characterName,
      validSpec('sprite.resident.valid_catalog_character'),
    );
    const fixture = createScene(characterName);

    SpriteLoader.loadCharacter(fixture.scene, characterName);
    SpriteLoader.createSprite(fixture.scene, 10, 20, characterName);

    expect(registration).toEqual({ accepted: true, diagnostics: [] });
    expect(fixture.loadImage).toHaveBeenCalledWith(
      `${characterName}_idle_south_0`,
      `assets/sprites/extracted/${characterName}/${characterName}_idle_south_0.png`,
    );
    expect(fixture.loadStart).toHaveBeenCalledOnce();
    expect(fixture.sprite.setOrigin).toHaveBeenCalledWith(0.5, 1);
  });

  it.each([
    [
      'anchor',
      (spec: SpriteCatalogSpec) => {
        spec.anchor = { x: 0, y: 0.5 };
      },
      'SPRITE_ANCHOR_INVALID',
    ],
    [
      'frame count',
      (spec: SpriteCatalogSpec) => {
        spec.walk_frames.north = ['n0'];
      },
      'SPRITE_WALK_FRAME_COUNT_INVALID',
    ],
    [
      'directions',
      (spec: SpriteCatalogSpec) => {
        spec.directions = ['north', 'east', 'south'];
      },
      'SPRITE_DIRECTIONS_INVALID',
    ],
  ])(
    'blocks an invalid %s spec from loading and creates the stable silhouette fallback',
    (_label, mutate, expectedIssue) => {
      const characterName = `invalid_${_label.toString().replace(' ', '_')}`;
      const spec = validSpec(`sprite.resident.${characterName}`);
      mutate(spec);
      const fixture = createScene(characterName);

      const registration = SpriteLoader.registerCharacterCatalog(characterName, spec);
      SpriteLoader.loadCharacter(fixture.scene, characterName);
      SpriteLoader.createSprite(fixture.scene, 10, 20, characterName);

      expect(registration.accepted).toBe(false);
      expect(registration.diagnostics).toEqual(
        expect.arrayContaining([
          expect.objectContaining({ issue: expectedIssue }),
        ]),
      );
      expect(fixture.loadImage).not.toHaveBeenCalled();
      expect(fixture.loadStart).not.toHaveBeenCalled();
      expect(fixture.scene.add.sprite).toHaveBeenCalledWith(
        10,
        20,
        'asset.fallback.resident_silhouette',
      );
      expect(fixture.sprite.setOrigin).toHaveBeenCalledWith(0.5, 1);
    },
  );

  it('falls back to the same character south idle when an animation is missing', () => {
    const characterName = 'missing_animation_character';
    const fixture = createScene(characterName);
    fixture.animationExists.mockImplementation(
      (key: string) => key === `${characterName}_idle_south`,
    );
    const sprite = {
      scene: fixture.scene,
      play: vi.fn(),
    } as unknown as Phaser.GameObjects.Sprite;

    SpriteLoader.registerCharacterCatalog(
      characterName,
      validSpec('sprite.resident.missing_animation_character'),
    );
    SpriteLoader.playAnimation(sprite, characterName, 'attack', 'north');

    expect(sprite.play).toHaveBeenCalledWith(
      `${characterName}_idle_south`,
      true,
    );
  });
});
