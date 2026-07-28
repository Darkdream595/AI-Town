export const STRUCTURE_STAGES = [
  'foundation',
  'construction',
  'complete',
  'damaged',
  'ruined',
  'repairing',
] as const;

export type StructureStage = (typeof STRUCTURE_STAGES)[number];

export interface StructureRenderProjection {
  building_id: string;
  stage: StructureStage;
  asset_id: string;
  footprint_version: number;
  shadow_asset_id: string;
  occluder_asset_ids: string[];
  affected_slice_ids: string[];
  confirmed: boolean;
}

export interface StructureDisplayGroup {
  building_id: string;
  stage: StructureStage;
  visible_piece_ids: string[];
}

export const STRUCTURE_DEPTH = {
  ground: 0,
  shadow: 500,
  structure: 1000,
  entity: 2000,
  occluder: 3000,
} as const;

export const OCCLUDER_OCCUPIED_ALPHA = 0.45;

export interface OccluderAlphaPlan {
  kind: 'set_occluder_alpha';
  updates: Array<{
    piece_id: string;
    alpha: number;
  }>;
}

export function createOccluderAlphaPlan(
  occluderPieceIds: readonly string[],
  occupied: boolean,
): OccluderAlphaPlan {
  const alpha = occupied ? OCCLUDER_OCCUPIED_ALPHA : 1;
  return {
    kind: 'set_occluder_alpha',
    updates: occluderPieceIds.map(pieceId => ({
      piece_id: pieceId,
      alpha,
    })),
  };
}

export interface StructureVisiblePiece {
  piece_id: string;
  asset_id: string;
  role: 'structure' | 'shadow' | 'occluder';
  depth: number;
}

export interface ReplaceStagePlan {
  kind: 'replace_stage';
  building_id: string;
  from_stage: StructureStage;
  to_stage: StructureStage;
  footprint_version: number;
  affected_slice_ids: string[];
  replacement: {
    atomic: true;
    remove_piece_ids: string[];
    add_pieces: StructureVisiblePiece[];
  };
  missing_asset_ids?: never;
  fallback_notice_asset_id?: never;
}

export interface RetainStagePlan {
  kind: 'retain_stage';
  building_id: string;
  from_stage: StructureStage;
  to_stage: StructureStage;
  missing_asset_ids: string[];
  fallback_notice_asset_id: 'asset.fallback.structure_notice';
  replacement?: never;
}

export type StructureTransitionPlan = ReplaceStagePlan | RetainStagePlan;

export function isStructureStage(value: unknown): value is StructureStage {
  return (
    typeof value === 'string' &&
    (STRUCTURE_STAGES as readonly string[]).includes(value)
  );
}

export function createStructureTransitionPlan(
  previous: StructureDisplayGroup,
  projection: StructureRenderProjection,
  assetExists: (assetId: string) => boolean,
): StructureTransitionPlan | null {
  if (
    !projection.confirmed ||
    !isStructureStage(projection.stage) ||
    projection.building_id !== previous.building_id
  ) {
    return null;
  }

  const requiredAssetIds = [
    projection.asset_id,
    projection.shadow_asset_id,
    ...projection.occluder_asset_ids,
  ];
  const missingAssetIds = requiredAssetIds.filter(
    assetId => !assetExists(assetId),
  );
  if (missingAssetIds.length > 0) {
    return {
      kind: 'retain_stage',
      building_id: previous.building_id,
      from_stage: previous.stage,
      to_stage: previous.stage,
      missing_asset_ids: missingAssetIds,
      fallback_notice_asset_id: 'asset.fallback.structure_notice',
    };
  }

  const addPieces: StructureVisiblePiece[] = [
    {
      piece_id: `${projection.building_id}:structure:${projection.asset_id}`,
      asset_id: projection.asset_id,
      role: 'structure',
      depth: STRUCTURE_DEPTH.structure,
    },
    {
      piece_id: `${projection.building_id}:shadow:${projection.shadow_asset_id}`,
      asset_id: projection.shadow_asset_id,
      role: 'shadow',
      depth: STRUCTURE_DEPTH.shadow,
    },
    ...projection.occluder_asset_ids.map(assetId => ({
      piece_id: `${projection.building_id}:occluder:${assetId}`,
      asset_id: assetId,
      role: 'occluder' as const,
      depth: STRUCTURE_DEPTH.occluder,
    })),
  ];

  return {
    kind: 'replace_stage',
    building_id: projection.building_id,
    from_stage: previous.stage,
    to_stage: projection.stage,
    footprint_version: projection.footprint_version,
    affected_slice_ids: [...projection.affected_slice_ids],
    replacement: {
      atomic: true,
      remove_piece_ids: [...previous.visible_piece_ids],
      add_pieces: addPieces,
    },
  };
}
