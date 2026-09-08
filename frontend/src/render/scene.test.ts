import { describe, expect, it } from 'vitest';

import { DEFAULT_GEOMETRY, IntersectionScene, lerpFraction, shortestArc } from './scene';

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

describe('vehicle interpolation', () => {
  it('lerpFraction walks 0 → 1 across the segment and never extrapolates past it', () => {
    expect(lerpFraction(1000, 1000, 500)).toBe(0);
    expect(lerpFraction(1250, 1000, 500)).toBeCloseTo(0.5);
    expect(lerpFraction(1500, 1000, 500)).toBe(1);
    // a late next snapshot must not push the sprite past the last confirmed pose
    expect(lerpFraction(3000, 1000, 500)).toBe(1);
    // guard against a zero/negative duration
    expect(lerpFraction(1000, 1000, 0)).toBe(1);
    expect(lerpFraction(900, 1000, 500)).toBe(0);
  });

  it('shortestArc turns the short way and stays within (-π, π]', () => {
    expect(shortestArc(0, Math.PI / 2)).toBeCloseTo(Math.PI / 2);
    // 350° → 10° is +20°, not -340°
    expect(shortestArc((350 * Math.PI) / 180, (10 * Math.PI) / 180)).toBeCloseTo(
      (20 * Math.PI) / 180,
    );
    // 10° → 350° is -20°
    expect(shortestArc((10 * Math.PI) / 180, (350 * Math.PI) / 180)).toBeCloseTo(
      (-20 * Math.PI) / 180,
    );
  });
});
