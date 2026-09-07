import { NO_DATA, num, signed, titleise } from '../../lib/format';
import type { RewardBreakdown } from '../../lib/types';
import { Bar, Empty } from './Primitives';

/**
 * Renders a reward breakdown exactly as the backend computed it: one bar per weighted
 * component plus the total. Components are never rescaled or re-signed for looks - the
 * axis is symmetric around the largest observed magnitude so the signs stay readable
 * (MASTER_PROMPT section 84).
 */
export function RewardBars({
  breakdown,
  color,
}: {
  breakdown: RewardBreakdown | null | undefined;
  color: string;
}) {
  if (!breakdown || breakdown.components.length === 0) {
    return <Empty>No reward computed yet. The reward for a decision is realised at the next decision.</Empty>;
  }

  const span = Math.max(
    0.01,
    ...breakdown.components.map((c) => Math.abs(c.contribution)),
    Math.abs(breakdown.total),
  );

  return (
    <div>
      {breakdown.components.map((c) => (
        <Bar
          key={c.name}
          label={titleise(c.name)}
          value={c.contribution}
          min={-span}
          max={span}
          color={c.contribution >= 0 ? 'var(--green)' : 'var(--red)'}
          display={signed(c.contribution)}
        />
      ))}
      <div className="divider" />
      <Bar
        label="TOTAL"
        value={breakdown.total}
        min={-span}
        max={span}
        color={color}
        selected
        display={signed(breakdown.total)}
      />
      <p className="stat-note" style={{ marginTop: 4 }}>
        {breakdown.components
          .map((c) => `${titleise(c.name)} raw ${num(c.raw, 2)} × w ${num(c.weight, 2)}`)
          .join(' · ') || NO_DATA}
      </p>
    </div>
  );
}
