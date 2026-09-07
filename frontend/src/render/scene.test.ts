import { describe, expect, it } from 'vitest';

import { DEFAULT_GEOMETRY, IntersectionScene } from './scene';

/**
 * The renderer's world frame must match backend/app/simulation/geometry.py exactly, or
 * vehicles drift off their lanes. These check the two pieces that are pure data: the
 * per-approach direction vectors and the fallback geometry constants.
 */

describe('IntersectionScene.direction', () => {
  it('matches APPROACH_DIR in geometry.py (+x East, +y North)', () => {
    expect(IntersectionScene.direction('N')).toEqual([0, -1]);
    expect(IntersectionScene.direction('S')).toEqual([0, 1]);
    expect(IntersectionScene.direction('E')).toEqual([-1, 0]);
    expect(IntersectionScene.direction('W')).toEqual([1, 0]);
  });

  it('gives every approach a unit vector opposite to its counterpart', () => {
    for (const [a, b] of [
      ['N', 'S'],
      ['E', 'W'],
    ] as const) {
      const da = IntersectionScene.direction(a);
      const db = IntersectionScene.direction(b);
      expect(Math.hypot(...da)).toBeCloseTo(1);
      expect([da[0] + db[0], da[1] + db[1]]).toEqual([0, 0]);
    }
  });
});

describe('DEFAULT_GEOMETRY', () => {
  it('carries the config.yaml geometry defaults', () => {
    expect(DEFAULT_GEOMETRY).toMatchObject({
      laneWidth: 3.4,
      lanes: 3,
      boxSize: 24,
      approachLength: 220,
    });
  });

  it('stop-line distance is half the box plus the offset', () => {
    // configs/config.yaml: intersection_size_m 24, stop_line_offset_m 2
    expect(DEFAULT_GEOMETRY.stopLineDist).toBe(24 / 2 + 2);
  });
});
