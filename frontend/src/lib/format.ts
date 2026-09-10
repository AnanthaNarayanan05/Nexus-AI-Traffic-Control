/**
 * Display helpers.
 *
 * `NO_DATA` is rendered wherever the backend has not produced a value yet. Nothing in
 * this file ever invents, extrapolates or rounds a value into existence - an absent
 * measurement stays visibly absent (MASTER_PROMPT sections 84, 98, 114).
 */

import type { AgentKey } from './types';

export const NO_DATA = '—';

/**
 * The three active RL agents, each with its own objective (R10 §6):
 * A2C — emergency-vehicle prioritization, DQN — efficiency / fuel / emissions /
 * safety, PPO — adaptive congestion reduction under unbalanced demand. All three
 * are wired into the live loop, the training workflow, coordination and the UI.
 */
export const ACTIVE_AGENTS: readonly AgentKey[] = ['a2c', 'dqn', 'ppo'] as const;

export function num(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return NO_DATA;
  return value.toFixed(digits);
}

export function int(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return NO_DATA;
  return Math.round(value).toLocaleString();
}

export function signed(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return NO_DATA;
  return `${value >= 0 ? '+' : ''}${value.toFixed(digits)}`;
}

export function pct(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return NO_DATA;
  return `${(value * 100).toFixed(digits)}%`;
}

export function clock(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return NO_DATA;
  const total = Math.max(0, Math.floor(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const mm = String(m).padStart(2, '0');
  const ss = String(s).padStart(2, '0');
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

export function titleise(text: string): string {
  return text
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export const AGENT_LABEL = {
  a2c: 'A2C',
  dqn: 'DQN',
  ppo: 'PPO',
} as const;

export const AGENT_OBJECTIVE = {
  a2c: 'Emergency vehicle prioritization',
  dqn: 'Efficiency · fuel · emissions · safety',
  ppo: 'Adaptive congestion reduction',
} as const;

export const AGENT_OWNER = {
  a2c: 'Anantha Narayanan A',
  dqn: 'Shaun Joseph Sabu',
  ppo: 'Delna Liz Denny',
} as const;

/**
 * Customer-facing names for the three AI capabilities (R11 §10, §41). The algorithm
 * name (A2C / DQN / PPO) may still appear as a secondary detail, but the product
 * surface leads with what each one does for the road, not how it is built.
 */
export const AGENT_PRODUCT_NAME = {
  a2c: 'Emergency Response',
  dqn: 'Traffic Efficiency',
  ppo: 'Congestion Management',
} as const;

/** One plain sentence describing what each capability does (R11 §10). */
export const AGENT_PRODUCT_BLURB = {
  a2c: 'Clears a path for approaching emergency vehicles.',
  dqn: 'Keeps traffic moving with less fuel use and fewer stops.',
  ppo: 'Balances the signal when demand is heavier on one side.',
} as const;

/**
 * Plain-language wording for a safety outcome (R11 §15, §37). The raw enum
 * (`REWRITTEN_TRANSITION`, …) is only ever shown in an expanded "decision details"
 * view — never on the primary surface.
 */
export const SAFETY_PRODUCT_STATUS: Record<
  string,
  { label: string; tone: 'good' | 'warn' | 'bad'; detail: string }
> = {
  APPLIED: {
    label: 'Approved',
    tone: 'good',
    detail: 'Safety validation approved the signal change.',
  },
  REWRITTEN_TRANSITION: {
    label: 'Adjusted for safety',
    tone: 'warn',
    detail: 'NEXUS adjusted the AI recommendation to keep the signal transition safe.',
  },
  BLOCKED_HOLD: {
    label: 'Held for safety',
    tone: 'warn',
    detail: 'NEXUS held the current signal because changing it now would be unsafe.',
  },
  FORCED_CHANGE: {
    label: 'Safety change',
    tone: 'bad',
    detail: 'NEXUS forced a signal change to resolve an unsafe situation.',
  },
  EMERGENCY_TIMEOUT: {
    label: 'Safety timeout',
    tone: 'bad',
    detail: 'NEXUS ended an over-long phase to protect the intersection.',
  },
};

/** Product wording for the signal that ends up being served. */
export function signalActionText(phase: string): string {
  switch (phase) {
    case 'NS':
    case 'N':
    case 'S':
      return 'North–South traffic released.';
    case 'EW':
    case 'E':
    case 'W':
      return 'East–West traffic released.';
    case 'YELLOW':
      return 'Signal changing — clearing the intersection.';
    case 'ALL_RED':
      return 'All directions held briefly for a safe changeover.';
    default:
      return 'Signal updated.';
  }
}

/** The compass name of an approach letter, for customer copy. */
export const APPROACH_NAME: Record<string, string> = {
  N: 'North',
  E: 'East',
  S: 'South',
  W: 'West',
};

/** Product wording for the coordinator's choice of which recommendation to act on. */
export function coordinationBasisText(winner: string): string {
  switch (winner) {
    case 'a2c':
      return 'NEXUS selected the emergency-priority recommendation.';
    case 'dqn':
      return 'NEXUS selected the traffic-efficiency recommendation.';
    case 'ppo':
      return 'NEXUS selected the congestion-management recommendation.';
    default:
      return 'NEXUS selected the safest valid signal for current traffic.';
  }
}
