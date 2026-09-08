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
