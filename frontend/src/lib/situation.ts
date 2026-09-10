/**
 * Plain-language reads of the *real* live state (R11 §12, §17, §37).
 *
 * Every string here is generated from a value the backend actually produced. Nothing
 * is invented, smoothed, or predicted — where a measurement is missing the caller gets
 * `null` and shows nothing, never a guess (MASTER_PROMPT §84, §98, §114). The only
 * judgement this file makes is banding a continuous number into a word ("Heavy" /
 * "Moderate" / "Light"), which is presentation, not simulation logic (R11 §52).
 */

import type { Approach, CompactState, CoordinationUpdate, MetricSnapshot } from './types';

const APPROACH_NAME: Record<Approach, string> = {
  N: 'North',
  E: 'East',
  S: 'South',
  W: 'West',
};

export type TrafficLevel = 'Heavy' | 'Moderate' | 'Light';

export function trafficLevel(state: CompactState | null): TrafficLevel | null {
  if (!state) return null;
  const queue = state.totals?.queue;
  if (typeof queue !== 'number' || !Number.isFinite(queue)) return null;
  if (queue >= 24) return 'Heavy';
  if (queue >= 10) return 'Moderate';
  return 'Light';
}

/** The approach carrying the most queued traffic right now, or null if it is even. */
export function busiestApproach(
  state: CompactState | null,
): { approach: Approach; name: string; queue: number } | null {
  if (!state?.approaches) return null;
  let best: { approach: Approach; name: string; queue: number } | null = null;
  for (const key of Object.keys(state.approaches) as Approach[]) {
    const q = state.approaches[key]?.queue_length ?? 0;
    if (!best || q > best.queue) best = { approach: key, name: APPROACH_NAME[key], queue: q };
  }
  // Only call a side "heavier" if it is meaningfully ahead of an even split.
  if (!best || best.queue < 4) return null;
  const total = (Object.keys(state.approaches) as Approach[]).reduce(
    (sum, k) => sum + (state.approaches[k]?.queue_length ?? 0),
    0,
  );
  if (total > 0 && best.queue / total < 0.4) return null;
  return best;
}

export interface EmergencyRead {
  type: string;
  approachName: string;
  etaSeconds: number | null;
  cleared: boolean;
}

export function emergencyRead(state: CompactState | null): EmergencyRead | null {
  const e = state?.emergency;
  if (!e?.active || !e.approach) return null;
  return {
    type: titleCaseWord(e.type ?? 'Emergency vehicle'),
    approachName: APPROACH_NAME[e.approach],
    etaSeconds:
      typeof e.eta_s === 'number' && Number.isFinite(e.eta_s) ? Math.max(0, e.eta_s) : null,
    cleared: false,
  };
}

/**
 * The ordered list of natural-language insight lines for the current moment. Each entry
 * corresponds to something the backend reported this decision cycle.
 */
export function insightLines(
  state: CompactState | null,
  coordination: CoordinationUpdate | null,
): string[] {
  const lines: string[] = [];

  const em = emergencyRead(state);
  if (em) {
    lines.push(
      em.etaSeconds !== null
        ? `${em.type} approaching from the ${em.approachName}, about ${Math.round(
            em.etaSeconds,
          )} seconds away.`
        : `${em.type} detected on the ${em.approachName} approach.`,
    );
  }

  const busy = busiestApproach(state);
  if (busy && !em) {
    lines.push(`Traffic demand is currently heavier on the ${busy.name} approach.`);
  }

  if (coordination) {
    const winner = coordination.coordination.winner;
    if (winner === 'a2c') lines.push('Coordinator selected the emergency-priority recommendation.');
    else if (winner === 'dqn')
      lines.push('Coordinator selected the traffic-efficiency recommendation.');
    else if (winner === 'ppo')
      lines.push('Coordinator selected the congestion-management recommendation.');

    const action = coordination.safety.action_taken;
    if (action === 'APPLIED') lines.push('Safety validation approved the signal change.');
    else lines.push('Safety validation adjusted the signal change to keep the transition safe.');
  }

  if (lines.length === 0 && state) {
    lines.push('Traffic is flowing normally. NEXUS is managing the intersection.');
  }
  return lines;
}

/** Short status word for a live AI capability, from real winner / emergency state. */
export function capabilityStatus(
  agent: 'a2c' | 'dqn' | 'ppo',
  state: CompactState | null,
  coordination: CoordinationUpdate | null,
): { label: string; active: boolean } {
  const winner = coordination?.coordination.winner ?? null;
  if (agent === 'a2c') {
    if (state?.emergency?.active) return { label: 'Priority active', active: true };
    return { label: winner === 'a2c' ? 'Active' : 'Ready', active: winner === 'a2c' };
  }
  if (agent === 'dqn') {
    return { label: winner === 'dqn' ? 'Optimising' : 'Ready', active: winner === 'dqn' };
  }
  return { label: winner === 'ppo' ? 'Managing' : 'Ready', active: winner === 'ppo' };
}

export function hasMeasuredMetrics(m: MetricSnapshot | null): boolean {
  return !!m && typeof m.traffic?.avg_waiting_s === 'number';
}

function titleCaseWord(text: string): string {
  return text
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}
