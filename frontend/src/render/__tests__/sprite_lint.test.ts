import { describe, expect, it } from 'vitest';
import { lintSpriteSpec, type SpriteCatalogSpec } from '../sprite_lint';

function validSpec(): SpriteCatalogSpec {
  return {
    asset_id: 'sprite.resident.apothecary',
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

describe('TEST-RENDER-004 sprite catalog lint', () => {
  it('accepts the canonical four-direction six-frame sprite contract', () => {
    expect(lintSpriteSpec(validSpec())).toEqual([]);
  });

  it('returns stable issues and reasons for invalid catalog ids and locale text', () => {
    const invalidGrammar = validSpec();
    invalidGrammar.asset_id = 'Sprite/Resident/Apothecary';
    expect(lintSpriteSpec(invalidGrammar)[0]).toEqual({
      issue: 'SPRITE_ASSET_ID_INVALID',
      reason: 'asset_id must match namespace.segment[.segment...] using lowercase ASCII segments',
    });

    const localized = validSpec();
    localized.asset_id = 'sprite.resident.药剂师';
    expect(lintSpriteSpec(localized)[0]).toEqual({
      issue: 'SPRITE_ASSET_ID_LOCALE_TEXT_FORBIDDEN',
      reason: 'asset_id must not contain locale display text',
    });
  });

  it('requires exactly north east south west and six walk frames each', () => {
    const spec = validSpec();
    spec.directions = ['north', 'east', 'south'];
    spec.walk_frames.west = ['w0'];

    expect(lintSpriteSpec(spec)).toEqual(
      expect.arrayContaining([
        {
          issue: 'SPRITE_DIRECTIONS_INVALID',
          reason: 'directions must contain exactly north, east, south, west',
        },
        {
          issue: 'SPRITE_WALK_FRAME_COUNT_INVALID',
          reason: 'walk_frames.west must contain exactly 6 frames',
        },
      ]),
    );
  });

  it('requires positive integer frame dimensions and the fixed foot anchor', () => {
    const spec = validSpec();
    spec.frame_size_px = { width: 0, height: 47.5 };
    spec.anchor = { x: 0, y: 0.5 };

    expect(lintSpriteSpec(spec)).toEqual(
      expect.arrayContaining([
        {
          issue: 'SPRITE_FRAME_SIZE_INVALID',
          reason: 'frame_size_px width and height must be positive integers',
        },
        {
          issue: 'SPRITE_ANCHOR_INVALID',
          reason: 'anchor must be exactly {x:0.5,y:1}',
        },
      ]),
    );
  });
});
