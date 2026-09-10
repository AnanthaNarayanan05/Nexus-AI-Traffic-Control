/**
 * Turns a measured Fixed-Time vs AI comparison (`EvalComparison` plus the
 * per-controller `ExperimentResult` rows) into a plain-language read for each NEXUS
 * capability — the customer view of Insights (R11 §23).
 *
 * Every number here is a measured episode aggregate carried straight from the
 * evaluation harness. Nothing is smoothed, extrapolated or rounded into an
 * improvement (MASTER_PROMPT §84; R11 §3/§12/§37). A change smaller than the combined
 * 95% confidence interval is reported as "about the same" — never as a win or a loss.
 */

import type { AgentKey, EvalComparison, ExperimentResult } from './types';

export type Verdict = 'better' | 'similar' | 'worse' | 'no-data';

export interface MetricRead {
  label: string;
  verdict: Verdict;
  /** e.g. "12.3 s vs 18.7 s on a fixed timer — 34% better" */
  text: string;
}

export interface CapabilityRead {
  agent: AgentKey;
  title: string;
  headline: string;
  verdict: Verdict;
  metrics: MetricRead[];
}

interface MetricSpec {
  key: string;
  label: string;
  unit: string;
  digits: number;
}

/** Customer-facing name per capability (kept in step with `AGENT_PRODUCT_NAME`). */
const TITLE: Record<AgentKey, string> = {
  a2c: 'Emergency Response',
  dqn: 'Traffic Efficiency',
  ppo: 'Congestion Management',
};

/**
 * The headline metrics for each capability, primary first. Keys match the evaluation
 * harness metric names exactly.
 */
const CAPABILITY_METRICS: Record<AgentKey, MetricSpec[]> = {
  a2c: [
    { key: 'emergency.emergency_delay_s', label: 'Emergency vehicle delay', unit: 's', digits: 1 },
    { key: 'emergency.emergency_wait_s', label: 'Emergency vehicle waiting', unit: 's', digits: 1 },
  ],
  dqn: [
    { key: 'traffic.avg_waiting_s', label: 'Average driver wait', unit: 's', digits: 1 },
    { key: 'traffic.stops_per_veh', label: 'Stops per vehicle', unit: '', digits: 2 },
    { key: 'environmental.fuel_l_per_veh', label: 'Fuel use per vehicle', unit: 'L', digits: 3 },
  ],
  ppo: [
    { key: 'traffic.avg_queue', label: 'Average queue length', unit: 'veh', digits: 2 },
    { key: 'traffic.throughput_vph', label: 'Traffic cleared per hour', unit: 'veh/h', digits: 0 },
  ],
};

interface Cell {
  mean: number;
  ci_half_width: number;
  improvement_pct_vs_baseline: number | null;
}

function fmt(n: number, digits: number, unit: string): string {
  const v = digits === 0 ? Math.round(n).toLocaleString() : n.toFixed(digits);
  return unit ? `${v} ${unit}` : v;
}

function readMetric(spec: MetricSpec, base: Cell | undefined, cand: Cell | undefined): MetricRead {
  if (!base || !cand || !Number.isFinite(base.mean) || !Number.isFinite(cand.mean)) {
    return { label: spec.label, verdict: 'no-data', text: 'not measured on this scenario' };
  }
  const pair = `${fmt(cand.mean, spec.digits, spec.unit)} vs ${fmt(base.mean, spec.digits, spec.unit)} on a fixed timer`;
  const diff = Math.abs(cand.mean - base.mean);
  const noise = base.ci_half_width + cand.ci_half_width;
  if (diff < noise) return { label: spec.label, verdict: 'similar', text: `${pair} — no measurable difference` };

  const pct = cand.improvement_pct_vs_baseline;
  if (pct == null) return { label: spec.label, verdict: 'similar', text: pair };
  if (pct > 0) return { label: spec.label, verdict: 'better', text: `${pair} — ${Math.round(pct)}% better` };
  if (pct < 0) {
    return { label: spec.label, verdict: 'worse', text: `${pair} — ${Math.round(Math.abs(pct))}% worse` };
  }
  return { label: spec.label, verdict: 'similar', text: pair };
}

function headline(title: string, primary: MetricRead | undefined): string {
  if (!primary || primary.verdict === 'no-data') {
    return `Not enough data to compare ${title} on this scenario.`;
  }
  if (primary.verdict === 'better') return `${primary.label} improved versus a fixed timer.`;
  if (primary.verdict === 'worse') {
    return `${primary.label} was worse than a fixed timer on this scenario.`;
  }
  return `${primary.label} was about the same as a fixed timer.`;
}

/**
 * Build one read per AI capability present in the comparison. Capabilities not
 * included in the run are simply omitted.
 */
export function capabilityReads(
  comparison: EvalComparison,
  results: ExperimentResult[],
): CapabilityRead[] {
  const baseLabel = comparison.baseline;
  const labelOf = new Map<string, string>();
  for (const r of results) {
    if (r.controller !== 'fixed_time') labelOf.set(r.controller, r.label);
  }

  const out: CapabilityRead[] = [];
  for (const agent of ['a2c', 'dqn', 'ppo'] as AgentKey[]) {
    const candLabel = labelOf.get(agent);
    if (!candLabel) continue;

    const metrics = CAPABILITY_METRICS[agent]
      .map((spec) => {
        const row = comparison.metrics[spec.key];
        if (!row) return null;
        return readMetric(spec, row.values[baseLabel], row.values[candLabel]);
      })
      .filter((m): m is MetricRead => m != null);

    if (metrics.length === 0) continue;
    const primary = metrics[0];
    out.push({
      agent,
      title: TITLE[agent],
      headline: headline(TITLE[agent], primary),
      verdict: primary.verdict,
      metrics,
    });
  }
  return out;
}
