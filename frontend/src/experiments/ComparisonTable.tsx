/**
 * Honest Fixed-Time vs AI comparison table (MASTER_PROMPT §16, §48-56).
 *
 * Rules baked into this component:
 *  - the baseline column is ALWAYS rendered, so a percentage is never shown without the
 *    absolute values it was derived from;
 *  - a metric only counts as an improvement when it moved the *better* way for that
 *    metric - lower waiting time, higher throughput. The backend's
 *    `improvement_pct_vs_baseline` is already sign-corrected for direction, so a bare
 *    numeric increase is never coloured green on its own;
 *  - a delta whose magnitude is inside the combined 95% CI is flagged "within noise" and
 *    shown without a win/loss colour.
 *
 * Nothing here is synthesised: every mean / CI is a measured episode aggregate streamed
 * from the evaluation harness.
 */

import { Fragment } from 'react';

import { Empty } from '../components/common/Primitives';
import { AGENT_LABEL, NO_DATA, num, titleise } from '../lib/format';
import type { AgentKey, EvalComparison, ExperimentResult } from '../lib/types';

interface MetricMeta {
  label: string;
  group: string;
  unit?: string;
  digits: number;
}

const METRIC_META: Record<string, MetricMeta> = {
  'traffic.avg_waiting_s': { label: 'Avg waiting', group: 'Traffic', unit: 's', digits: 1 },
  'traffic.avg_queue': { label: 'Avg queue', group: 'Traffic', unit: 'veh', digits: 2 },
  'traffic.throughput_vph': { label: 'Throughput', group: 'Traffic', unit: 'veh/h', digits: 0 },
  'traffic.avg_travel_time_s': { label: 'Avg travel time', group: 'Traffic', unit: 's', digits: 1 },
  'traffic.avg_speed_mps': { label: 'Avg speed', group: 'Traffic', unit: 'm/s', digits: 2 },
  'traffic.stops_per_veh': { label: 'Stops / veh', group: 'Traffic', digits: 2 },
  'traffic.idle_time_s': { label: 'Idle time', group: 'Traffic', unit: 's', digits: 1 },
  'environmental.fuel_l_per_veh': { label: 'Fuel / veh', group: 'Environmental', unit: 'L', digits: 3 },
  'environmental.co2_kg_per_veh': { label: 'CO₂ / veh', group: 'Environmental', unit: 'kg', digits: 3 },
  'environmental.fuel_l_total': { label: 'Fuel total', group: 'Environmental', unit: 'L', digits: 2 },
  'environmental.co2_kg_total': { label: 'CO₂ total', group: 'Environmental', unit: 'kg', digits: 2 },
  'emergency.emergency_wait_s': { label: 'Emergency wait', group: 'Emergency', unit: 's', digits: 1 },
  'emergency.emergency_travel_time_s': {
    label: 'Emergency travel time',
    group: 'Emergency',
    unit: 's',
    digits: 1,
  },
  'emergency.emergency_delay_s': { label: 'Emergency delay', group: 'Emergency', unit: 's', digits: 1 },
  'emergency.emergency_cleared': { label: 'Emergency cleared', group: 'Emergency', digits: 2 },
  'safety.red_light_violations': { label: 'Red-light violations', group: 'Safety', digits: 2 },
  'safety.other_violations': { label: 'Other violations', group: 'Safety', digits: 2 },
  'safety.unsafe_transitions': { label: 'Unsafe transitions', group: 'Safety', digits: 2 },
};

const GROUP_ORDER = ['Traffic', 'Environmental', 'Emergency', 'Safety'];

function metaFor(key: string): MetricMeta {
  return METRIC_META[key] ?? { label: key, group: 'Other', digits: 2 };
}

/** Full column heading, e.g. "Fixed-Time", "A2C · untrained", "DQN · dqn-v1.3-dev". */
function columnLabel(label: string, byLabel: Map<string, ExperimentResult>): string {
  const r = byLabel.get(label);
  if (!r) return label;
  if (r.controller === 'fixed_time') return 'Fixed-Time';
  const base = AGENT_LABEL[r.controller as AgentKey] ?? titleise(r.controller);
  if (r.model_mode === 'untrained' || r.model_version === 'untrained' || r.model_version == null) {
    return `${base} · untrained`;
  }
  return `${base} · ${r.model_version}`;
}

/** Short winner tag - controller only, no version. */
function shortName(label: string, byLabel: Map<string, ExperimentResult>): string {
  const r = byLabel.get(label);
  if (!r) return label;
  if (r.controller === 'fixed_time') return 'Fixed-Time';
  return AGENT_LABEL[r.controller as AgentKey] ?? titleise(r.controller);
}

function fmtValue(mean: number, ci: number, digits: number): string {
  if (!Number.isFinite(mean)) return NO_DATA;
  return ci > 0 ? `${num(mean, digits)} ± ${num(ci, digits)}` : num(mean, digits);
}

export function ComparisonTable({
  comparison,
  results,
}: {
  comparison: EvalComparison;
  results?: ExperimentResult[];
}) {
  const keys = Object.keys(comparison.metrics);
  if (keys.length === 0) return <Empty>No comparison metrics were recorded.</Empty>;

  const byLabel = new Map((results ?? []).map((r) => [r.label, r] as const));
  const firstValues = comparison.metrics[keys[0]].values;
  const allLabels = Object.keys(firstValues);
  const baseline = comparison.baseline;
  const candidates = allLabels.filter((l) => l !== baseline);
  const ordered = [baseline, ...candidates];

  const grouped = GROUP_ORDER.map((group) => ({
    group,
    keys: keys.filter((k) => metaFor(k).group === group),
  })).filter((g) => g.keys.length > 0);
  const known = new Set(GROUP_ORDER);
  const leftover = keys.filter((k) => !known.has(metaFor(k).group));
  if (leftover.length) grouped.push({ group: 'Other', keys: leftover });

  const colCount = ordered.length + 3; // metric + direction + winner

  return (
    <div className="cmp">
      <p className="cmp-caption">
        {comparison.scenario} &middot; {comparison.n_episodes} episode
        {comparison.n_episodes === 1 ? '' : 's'} &middot; seeds [{comparison.seeds.join(', ')}]
        &middot; baseline <strong>{columnLabel(baseline, byLabel)}</strong>
      </p>

      <div className="table-scroll">
        <table className="cmp-table">
          <thead>
            <tr>
              <th>Metric</th>
              <th title="Which direction is better for this metric">Better</th>
              {ordered.map((l) => (
                <th key={l} className={l === baseline ? 'cmp-base-col' : ''}>
                  {columnLabel(l, byLabel)}
                  {l === baseline ? <span className="cmp-base-tag">baseline</span> : null}
                </th>
              ))}
              <th>Winner</th>
            </tr>
          </thead>
          <tbody>
            {grouped.map(({ group, keys: groupKeys }) => (
              <Fragment key={group}>
                <tr className="cmp-group">
                  <td colSpan={colCount}>{group}</td>
                </tr>
                {groupKeys.map((key) => {
                  const row = comparison.metrics[key];
                  const meta = metaFor(key);
                  const lower = row.lower_is_better;
                  const base = row.values[baseline];

                  // Winner = best mean in the better direction. It is only *called* a
                  // winner when it is separable from the runner-up by more than the
                  // combined 95% CI - otherwise the metric is a tie (this is also why an
                  // all-equal row, e.g. every controller at 0, never crowns anyone).
                  const ranked = ordered
                    .map((l) => ({ l, v: row.values[l] }))
                    .filter((x) => x.v && Number.isFinite(x.v.mean))
                    .sort((a, b) => (lower ? a.v.mean - b.v.mean : b.v.mean - a.v.mean));
                  const winLabel = ranked[0]?.l ?? null;
                  const runnerUp = ranked[1];
                  const winnerIsNoise =
                    winLabel == null ||
                    runnerUp == null ||
                    Math.abs(ranked[0].v.mean - runnerUp.v.mean) <=
                      ranked[0].v.ci_half_width + runnerUp.v.ci_half_width;

                  return (
                    <tr key={key}>
                      <td className="cmp-metric" title={key}>
                        {meta.label}
                        {meta.unit ? <span className="cmp-unit"> {meta.unit}</span> : null}
                      </td>
                      <td className="cmp-dir" title={lower ? 'lower is better' : 'higher is better'}>
                        {lower ? '↓' : '↑'}
                      </td>
                      {ordered.map((l) => {
                        const v = row.values[l];
                        if (!v) {
                          return (
                            <td key={l} className={l === baseline ? 'cmp-base-col' : ''}>
                              {NO_DATA}
                            </td>
                          );
                        }
                        if (l === baseline) {
                          return (
                            <td key={l} className="cmp-base-col">
                              {fmtValue(v.mean, v.ci_half_width, meta.digits)}
                            </td>
                          );
                        }
                        const dAbs = base ? v.mean - base.mean : null;
                        const pctVal = v.improvement_pct_vs_baseline;
                        const withinCI =
                          base != null &&
                          Math.abs(v.mean - base.mean) < v.ci_half_width + base.ci_half_width;
                        const tone =
                          pctVal == null || withinCI
                            ? 'flat'
                            : pctVal > 0
                              ? 'up'
                              : pctVal < 0
                                ? 'down'
                                : 'flat';
                        return (
                          <td key={l}>
                            <span className="cmp-cell-mean">
                              {fmtValue(v.mean, v.ci_half_width, meta.digits)}
                            </span>
                            <span className={`cmp-delta ${tone}`}>
                              {dAbs == null
                                ? NO_DATA
                                : `${dAbs >= 0 ? '+' : '−'}${num(Math.abs(dAbs), meta.digits)}`}
                              {pctVal == null
                                ? ''
                                : `  ${pctVal > 0 ? '+' : pctVal < 0 ? '−' : ''}${Math.abs(pctVal).toFixed(1)}%`}
                              {withinCI ? '  within noise' : ''}
                            </span>
                          </td>
                        );
                      })}
                      <td className="cmp-winner">
                        {winLabel == null
                          ? NO_DATA
                          : winnerIsNoise
                            ? '≈ tie'
                            : shortName(winLabel, byLabel)}
                      </td>
                    </tr>
                  );
                })}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>

      <p className="cmp-foot">
        &darr; lower is better &middot; &uarr; higher is better. Each AI cell shows the metric
        mean (&plusmn; 95% CI), then the absolute change and the direction-aware % vs baseline
        &mdash; <span className="cmp-delta up">green</span> when the controller is better,{' '}
        <span className="cmp-delta down">red</span> when worse. &ldquo;within noise&rdquo; means
        the change is smaller than the combined confidence interval, so it is not a real
        difference. When the baseline value is ~0 no % is shown, only the absolute change.
        &ldquo;Winner&rdquo; reads &ldquo;&asymp; tie&rdquo; unless the best controller clears
        the runner-up by more than their combined CI.
      </p>
    </div>
  );
}
