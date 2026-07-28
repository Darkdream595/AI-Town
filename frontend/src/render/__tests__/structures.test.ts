import { describe, expect, it } from 'vitest';
import {
  OCCLUDER_OCCUPIED_ALPHA,
  STRUCTURE_DEPTH,
  createOccluderAlphaPlan,
  createStructureTransitionPlan,
  isStructureStage,
  type StructureDisplayGroup,
  type StructureRenderProjection,
} from '../structures';

const previous: StructureDisplayGroup = {
  building_id: 'building_01',
  stage: 'foundation',
  visible_piece_ids: ['old-body', 'old-shadow', 'old-roof'],
};

function projection(
  overrides: Partial<StructureRenderProjection> = {},
): StructureRenderProjection {
  return {
    building_id: 'building_01',
    stage: 'construction',
    asset_id: 'structure.workshop.construction',
    footprint_version: 2,
    shadow_asset_id: 'shadow.structure.workshop',
    occluder_asset_ids: ['occluder.structure.workshop.roof'],
    affected_slice_ids: ['slice.town.0_0'],
    confirmed: true,
    ...overrides,
  };
}

describe('TEST-RENDER-006 structure transition planning', () => {
  it('recognizes only canonical structure stages', () => {
    for (const stage of [
      'foundation',
      'construction',
      'complete',
      'damaged',
      'ruined',
      'repairing',
    ]) {
      expect(isStructureStage(stage)).toBe(true);
    }
    expect(isStructureStage('preview')).toBe(false);
  });

  it('creates plans only from confirmed projections', () => {
    expect(
      createStructureTransitionPlan(previous, projection({ confirmed: false }), () => true),
    ).toBeNull();
    expect(
      createStructureTransitionPlan(
        previous,
        projection({ stage: 'preview' as StructureRenderProjection['stage'] }),
        () => true,
      ),
    ).toBeNull();
  });

  it('replaces every visible piece for one building in one atomic operation', () => {
    const plan = createStructureTransitionPlan(previous, projection(), () => true);

    expect(plan).toMatchObject({
      kind: 'replace_stage',
      building_id: 'building_01',
      from_stage: 'foundation',
      to_stage: 'construction',
      replacement: {
        remove_piece_ids: ['old-body', 'old-shadow', 'old-roof'],
      },
    });
    expect(plan?.replacement?.add_pieces.map(piece => piece.role)).toEqual([
      'structure',
      'shadow',
      'occluder',
    ]);
    expect(plan?.replacement?.atomic).toBe(true);
    expect(JSON.stringify(plan)).not.toContain('collision');
  });

  it('retains the previous stage and emits a fallback notice when any asset is missing', () => {
    const plan = createStructureTransitionPlan(
      previous,
      projection(),
      assetId => assetId !== 'shadow.structure.workshop',
    );

    expect(plan).toEqual({
      kind: 'retain_stage',
      building_id: 'building_01',
      from_stage: 'foundation',
      to_stage: 'foundation',
      missing_asset_ids: ['shadow.structure.workshop'],
      fallback_notice_asset_id: 'asset.fallback.structure_notice',
    });
  });

  it('places shadows between ground and entities and fixes occupied occluder alpha', () => {
    expect(STRUCTURE_DEPTH.shadow).toBeGreaterThan(STRUCTURE_DEPTH.ground);
    expect(STRUCTURE_DEPTH.shadow).toBeLessThan(STRUCTURE_DEPTH.entity);
    expect(STRUCTURE_DEPTH.occluder).toBeGreaterThan(STRUCTURE_DEPTH.entity);
    expect(OCCLUDER_OCCUPIED_ALPHA).toBe(0.45);
  });

  it('creates executable alpha updates from current occluder occupancy', () => {
    expect(
      createOccluderAlphaPlan(['roof-west', 'roof-east'], true),
    ).toEqual({
      kind: 'set_occluder_alpha',
      updates: [
        { piece_id: 'roof-west', alpha: 0.45 },
        { piece_id: 'roof-east', alpha: 0.45 },
      ],
    });
    expect(createOccluderAlphaPlan(['roof-west'], false)).toEqual({
      kind: 'set_occluder_alpha',
      updates: [{ piece_id: 'roof-west', alpha: 1 }],
    });
  });
});
