/**
 * Inline-SVG sparkline for a series of episode returns. Draws only the points it is
 * given - no smoothing, no interpolation of missing values (MASTER_PROMPT sections
 * 84, 114).
 */

export function Sparkline({
  values,
  width = 260,
  height = 48,
  color = 'var(--accent)',
}: {
  values: number[];
  width?: number;
  height?: number;
  color?: string;
}) {
  if (values.length < 2) {
    return (
      <svg className="sparkline" width={width} height={height} role="img" aria-label="no data yet">
        <line
          x1={0}
          y1={height / 2}
          x2={width}
          y2={height / 2}
          stroke="var(--border)"
          strokeDasharray="3 3"
        />
      </svg>
    );
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pad = 3;
  const dx = (width - pad * 2) / (values.length - 1);

  const points = values.map((v, i) => {
    const x = pad + i * dx;
    const y = pad + (height - pad * 2) * (1 - (v - min) / span);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  const last = values[values.length - 1];
  const [lx, ly] = points[points.length - 1].split(',').map(Number);

  return (
    <svg
      className="sparkline"
      width={width}
      height={height}
      role="img"
      aria-label={`episode returns, latest ${last.toFixed(2)}`}
    >
      <polyline points={points.join(' ')} fill="none" stroke={color} strokeWidth={1.5} />
      <circle cx={lx} cy={ly} r={2.5} fill={color} />
    </svg>
  );
}
