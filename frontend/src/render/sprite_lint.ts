export type SpriteDirection = 'north' | 'east' | 'south' | 'west';

export interface SpriteCatalogSpec {
  asset_id: string;
  directions: string[];
  walk_frames: Record<SpriteDirection, string[]>;
  frame_size_px: {
    width: number;
    height: number;
  };
  anchor: {
    x: number;
    y: number;
  };
}

export type SpriteLintIssue =
  | 'SPRITE_ASSET_ID_INVALID'
  | 'SPRITE_ASSET_ID_LOCALE_TEXT_FORBIDDEN'
  | 'SPRITE_DIRECTIONS_INVALID'
  | 'SPRITE_WALK_FRAME_COUNT_INVALID'
  | 'SPRITE_FRAME_SIZE_INVALID'
  | 'SPRITE_ANCHOR_INVALID';

export interface SpriteLintDiagnostic {
  issue: SpriteLintIssue;
  reason: string;
}

const STABLE_CATALOG_ID_PATTERN =
  /^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$/;
const DIRECTIONS: readonly SpriteDirection[] = [
  'north',
  'east',
  'south',
  'west',
];

export function lintSpriteSpec(
  spec: SpriteCatalogSpec,
): SpriteLintDiagnostic[] {
  const diagnostics: SpriteLintDiagnostic[] = [];

  if (/[^\x00-\x7F]/.test(spec.asset_id)) {
    diagnostics.push({
      issue: 'SPRITE_ASSET_ID_LOCALE_TEXT_FORBIDDEN',
      reason: 'asset_id must not contain locale display text',
    });
  } else if (!STABLE_CATALOG_ID_PATTERN.test(spec.asset_id)) {
    diagnostics.push({
      issue: 'SPRITE_ASSET_ID_INVALID',
      reason:
        'asset_id must match namespace.segment[.segment...] using lowercase ASCII segments',
    });
  }

  if (
    spec.directions.length !== DIRECTIONS.length ||
    new Set(spec.directions).size !== DIRECTIONS.length ||
    !DIRECTIONS.every(direction => spec.directions.includes(direction))
  ) {
    diagnostics.push({
      issue: 'SPRITE_DIRECTIONS_INVALID',
      reason: 'directions must contain exactly north, east, south, west',
    });
  }

  for (const direction of DIRECTIONS) {
    if (spec.walk_frames[direction]?.length !== 6) {
      diagnostics.push({
        issue: 'SPRITE_WALK_FRAME_COUNT_INVALID',
        reason: `walk_frames.${direction} must contain exactly 6 frames`,
      });
    }
  }

  if (
    !Number.isInteger(spec.frame_size_px.width) ||
    spec.frame_size_px.width <= 0 ||
    !Number.isInteger(spec.frame_size_px.height) ||
    spec.frame_size_px.height <= 0
  ) {
    diagnostics.push({
      issue: 'SPRITE_FRAME_SIZE_INVALID',
      reason: 'frame_size_px width and height must be positive integers',
    });
  }

  if (spec.anchor.x !== 0.5 || spec.anchor.y !== 1) {
    diagnostics.push({
      issue: 'SPRITE_ANCHOR_INVALID',
      reason: 'anchor must be exactly {x:0.5,y:1}',
    });
  }

  return diagnostics;
}
