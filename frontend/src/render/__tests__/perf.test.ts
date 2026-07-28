import { describe, expect, it } from 'vitest';
import {
  TextureBudgetLedger,
  evaluatePerformanceGate,
  estimateTextureBytes,
  nearestRankPercentile,
} from '../perf';

describe('TEST-RENDER-012 performance and texture gates', () => {
  it('uses nearest-rank percentiles without dropping long frames', () => {
    expect(nearestRankPercentile([1, 2, 3, 4, 100], 0.95)).toBe(100);
    expect(nearestRankPercentile([4, 1, 3, 2], 0.5)).toBe(2);
  });

  it('requires every iteration to pass p95 and p99 budgets', () => {
    const passing = Array.from({ length: 100 }, () => 10);
    const failing = [...Array.from({ length: 98 }, () => 10), 30, 40];
    expect(evaluatePerformanceGate([passing, passing, passing]).pass).toBe(true);
    expect(evaluatePerformanceGate([passing, failing, passing]).pass).toBe(false);
  });

  it('estimates uncompressed mip levels and block-compressed textures', () => {
    expect(
      estimateTextureBytes({
        width: 4,
        height: 4,
        bytesPerPixel: 4,
        mipLevels: 3,
      }),
    ).toBe(84);
    expect(
      estimateTextureBytes({
        width: 5,
        height: 5,
        block: { width: 4, height: 4, bytes: 16 },
      }),
    ).toBe(64);
  });

  it('deduplicates shared textures and applies the 1.10 safety margin', () => {
    const ledger = new TextureBudgetLedger(110);
    ledger.add('shared.atlas', 50);
    ledger.add('shared.atlas', 50);
    ledger.add('other', 50);
    expect(ledger.rawBytes).toBe(100);
    expect(ledger.totalBytes).toBe(111);
    expect(ledger.withinBudget()).toBe(false);
    ledger.resetAfterContextLoss();
    expect(ledger.totalBytes).toBe(0);
  });
});
