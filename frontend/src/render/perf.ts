export const FRAME_P95_BUDGET_MS = 16.67;
export const FRAME_P99_BUDGET_MS = 25;
export const TEXTURE_BUDGET_BYTES = 268_435_456;
export const TEXTURE_SAFETY_MARGIN = 1.1;

export function nearestRankPercentile(
  samples: readonly number[],
  percentile: number,
): number {
  if (samples.length === 0) {
    throw new Error('samples_required');
  }
  if (!(percentile > 0 && percentile <= 1)) {
    throw new Error('percentile_out_of_range');
  }
  const sorted = [...samples].sort((a, b) => a - b);
  return sorted[Math.ceil(percentile * sorted.length) - 1];
}

export interface PerformanceIteration {
  p95: number;
  p99: number;
  pass: boolean;
}

export function evaluatePerformanceGate(
  iterations: readonly (readonly number[])[],
): { pass: boolean; iterations: PerformanceIteration[] } {
  const results = iterations.map(samples => {
    const p95 = nearestRankPercentile(samples, 0.95);
    const p99 = nearestRankPercentile(samples, 0.99);
    return {
      p95,
      p99,
      pass: p95 <= FRAME_P95_BUDGET_MS && p99 <= FRAME_P99_BUDGET_MS,
    };
  });
  return {
    pass: results.length === 3 && results.every(result => result.pass),
    iterations: results,
  };
}

interface BlockFormat {
  width: number;
  height: number;
  bytes: number;
}

export interface TextureDescription {
  width: number;
  height: number;
  bytesPerPixel?: number;
  block?: BlockFormat;
  mipLevels?: number;
  layers?: number;
  faces?: number;
}

export function estimateTextureBytes(description: TextureDescription): number {
  const levels = description.mipLevels ?? 1;
  const layers = description.layers ?? 1;
  const faces = description.faces ?? 1;
  if (
    !Number.isInteger(levels) ||
    levels < 1 ||
    !Number.isInteger(layers) ||
    layers < 1 ||
    !Number.isInteger(faces) ||
    faces < 1
  ) {
    throw new Error('texture_dimensions_invalid');
  }

  let width = description.width;
  let height = description.height;
  let total = 0;
  for (let level = 0; level < levels; level += 1) {
    if (description.block) {
      total +=
        Math.ceil(width / description.block.width) *
        Math.ceil(height / description.block.height) *
        description.block.bytes;
    } else {
      total += width * height * (description.bytesPerPixel ?? 4);
    }
    width = Math.max(1, Math.floor(width / 2));
    height = Math.max(1, Math.floor(height / 2));
  }
  return total * layers * faces;
}

export class TextureBudgetLedger {
  private readonly allocations = new Map<string, number>();

  constructor(
    private readonly budgetBytes = TEXTURE_BUDGET_BYTES,
    private readonly safetyMargin = TEXTURE_SAFETY_MARGIN,
  ) {}

  add(textureId: string, bytes: number): void {
    if (!this.allocations.has(textureId)) {
      this.allocations.set(textureId, bytes);
    }
  }

  get rawBytes(): number {
    return [...this.allocations.values()].reduce((sum, bytes) => sum + bytes, 0);
  }

  get totalBytes(): number {
    return Math.ceil(this.rawBytes * this.safetyMargin);
  }

  withinBudget(): boolean {
    return this.totalBytes <= this.budgetBytes;
  }

  resetAfterContextLoss(): void {
    this.allocations.clear();
  }
}
