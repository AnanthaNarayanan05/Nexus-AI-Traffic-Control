import { useMetricTrail } from '../hooks/useMetricTrail';
import type { MetricTrails } from '../hooks/useMetricTrail';
import { NO_DATA, int, num } from '../lib/format';
import { useSimStore } from '../store';

/**
 * Customer-understandable metrics (R11 §17, §18). Every figure is read straight from
 * the backend snapshot. The small trend glyph reflects the direction of the samples
 * this browser has actually seen — it is never coloured "good" or "bad", and never
 * shown before there are enough samples to have a direction.
 */

interface Card {
  label: string;
  value: string;
  unit?: string;
  trend?: keyof MetricTrails;
  estimated?: boolean;
}

function trendGlyph(series: number[] | undefined): string {
  if (!series || series.length < 4) return '';
  const first = series[0];
  const last = series[series.length - 1];
  const span = Math.max(Math.abs(first), Math.abs(last), 1e-6);
  const rel = (last - first) / span;
  if (rel > 0.05) return '▲';
  if (rel < -0.05) return '▼';
  return '▬';
}

export function CustomerMetrics() {
  const metrics = useSimStore((s) => s.metrics);
  const trails = useMetricTrail();
  const t = metrics?.traffic;
  const env = metrics?.environmental;
  const em = metrics?.emergency;
  const safety = metrics?.safety;

  const safetyEvents = safety
    ? safety.red_light_violations + safety.other_violations + safety.unsafe_transitions
    : null;

  const cards: Card[] = [
    { label: 'Waiting time', value: num(t?.avg_waiting_s), unit: 's', trend: 'avg_waiting_s' },
    { label: 'Queue length', value: num(t?.avg_queue), unit: 'veh', trend: 'avg_queue' },
    { label: 'Throughput', value: int(t?.throughput_vph), unit: 'veh/h', trend: 'throughput_vph' },
    { label: 'Average speed', value: num(t?.avg_speed_mps), unit: 'm/s', trend: 'avg_speed_mps' },
    { label: 'Stops per vehicle', value: num(t?.stops_per_veh, 2), trend: 'stops_per_veh' },
    { label: 'Emergency delay', value: num(em?.emergency_delay_s), unit: 's' },
    {
      label: 'Safety events',
      value: safetyEvents === null ? NO_DATA : int(safetyEvents),
    },
  ];

  const secondary: Card[] = [
    { label: 'Estimated fuel / veh', value: num(env?.fuel_l_per_veh, 3), unit: 'L', estimated: true },
    { label: 'Estimated CO₂ / veh', value: num(env?.co2_kg_per_veh, 3), unit: 'kg', estimated: true },
  ];

  return (
    <section className="customer-metrics" aria-label="Key metrics">
      <div className="panel-kicker-row">
        <h2 className="panel-kicker">Key metrics</h2>
        {!metrics ? <span className="metrics-await">Waiting for the first reading…</span> : null}
      </div>
      <div className="metric-cards">
        {cards.map((c) => (
          <div className="metric-card" key={c.label}>
            <span className="metric-card-value">
              {c.value}
              {c.unit && c.value !== NO_DATA ? <span className="metric-card-unit">{c.unit}</span> : null}
              {c.trend ? <span className="metric-card-trend">{trendGlyph(trails[c.trend])}</span> : null}
            </span>
            <span className="metric-card-label">{c.label}</span>
          </div>
        ))}
      </div>
      <div className="metric-cards secondary">
        {secondary.map((c) => (
          <div className="metric-card" key={c.label}>
            <span className="metric-card-value">
              {c.value}
              {c.unit && c.value !== NO_DATA ? <span className="metric-card-unit">{c.unit}</span> : null}
            </span>
            <span className="metric-card-label">
              {c.label} <span className="estimated-tag">ESTIMATED</span>
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
