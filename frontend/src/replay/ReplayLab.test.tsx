import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ReplayDetail, ReplayFrame, ReplaySummary } from '../lib/types';

/**
 * The Replay Lab is a client-side player over the /replay REST surface. These tests stub
 * the API client and assert: the list renders with the partial/full badge, the newest
 * replay auto-opens, the transport steps through decisions, the pipeline shows the
 * coordinator → authoritative-safety hop, and "Capture current run" calls the endpoint
 * (with a friendly message on 409). No simulation runs here.
 */

const hoisted = vi.hoisted(() => ({
  replays: vi.fn(),
  replay: vi.fn(),
  captureReplay: vi.fn(),
  deleteReplay: vi.fn(),
}));

function frame(i: number, over: Partial<ReplayFrame> = {}): ReplayFrame {
  const phase = i % 2 === 0 ? 'NS' : 'EW';
  return {
    id: `d${i}`,
    t: 6 * (i + 1),
    step: 12 * (i + 1),
    state_summary: {
      sim_time: 6 * (i + 1),
      phase,
      served_phase: phase,
      phase_elapsed_s: 4,
      total_vehicles: 20 + i,
      total_queue: 8 + i,
      queues: { N: 3, E: 2, S: 2, W: 1 },
      emergency_active: false,
      emergency_approach: null,
      throughput_vph: 900,
      violations_total: 0,
    },
    recommendations: {
      a2c: {
        agent: 'a2c',
        action_index: 0,
        action_name: i % 2 === 0 ? 'HOLD' : 'SWITCH_NS',
        target_phase: phase,
        score: 0.4 + i * 0.05,
        confidence: 0.6,
        priority: 0.2,
        reason: `a2c reason ${i}`,
        relevant_state: {},
        action_distribution: [0.5, 0.5],
        value_estimate: 0.1,
      },
      dqn: {
        agent: 'dqn',
        action_index: 1,
        action_name: 'SWITCH_EW',
        target_phase: 'EW',
        score: 0.3,
        confidence: 0.55,
        priority: 0.1,
        reason: `dqn reason ${i}`,
        relevant_state: {},
        action_distribution: [0.4, 0.6],
        value_estimate: null,
      },
    },
    coordination: {
      candidate_phase: phase,
      winner: i % 2 === 0 ? 'a2c' : 'dqn',
      basis: 'weighted_score',
      ladder_trace: [{ rung: 'safety', outcome: 'pass', detail: 'no conflict' }],
      scores: [],
      recommendations: [],
    },
    safety: {
      approved: true,
      command: {
        target_phase: phase,
        request_extend_s: null,
        request_reduce: false,
        force_transition: false,
        source: 'coordinator',
      },
      original: phase,
      action_taken: i === 1 ? 'BLOCKED_HOLD' : 'APPLIED',
      violated_rules: i === 1 ? ['min_green'] : [],
      reason: i === 1 ? 'min green not met' : 'ok',
    },
    rewards: { a2c: 0.2 - i * 0.01, dqn: -0.1 * i },
    reward_breakdowns: {
      a2c: { total: 0.2 - i * 0.01, components: [{ name: 'emergency_clear', raw: 1, weight: 0.2, contribution: 0.2 }] },
      dqn: { total: -0.1 * i, components: [] },
    },
    metrics: {
      sim_time: 6 * (i + 1),
      window: 'rolling',
      traffic: {
        avg_waiting_s: 10 + i,
        avg_queue: 5,
        throughput_vph: 900,
        avg_travel_time_s: 40,
        avg_speed_mps: 7,
        stops_per_veh: 1.2,
        idle_time_s: 9,
      },
      environmental: { fuel_l_per_veh: 0.05, co2_kg_per_veh: 0.11, fuel_l_total: 1, co2_kg_total: 2 },
      emergency: { emergency_wait_s: 0, emergency_travel_time_s: 0, emergency_delay_s: 0, emergency_cleared: 0 },
      safety: { red_light_violations: 0, other_violations: 0, unsafe_transitions: i === 1 ? 1 : 0 },
      dev: null,
    },
    applied_phase: phase,
    ...over,
  };
}

const DETAIL: ReplayDetail = {
  id: 'replay-2',
  label: 'Rush hour · seed 7 · AI · partial',
  created_at: '2026-09-08T09:00:00Z',
  scenario_id: 'rush_hour',
  scenario_name: 'Rush hour',
  seed: 7,
  mode: 'AI',
  model_modes: { a2c: 'untrained', dqn: 'untrained' },
  config_digest: 'cfg0001',
  sim_duration_s: 30,
  decision_count: 5,
  episode_complete: false,
  timeline: [0, 1, 2, 3, 4].map((i) => frame(i)),
  events: [
    { id: 'e0', t: 1, wall_t: 0, category: 'SYSTEM', severity: 'info', description: 'started', meta: {} },
    { id: 'e1', t: 13, wall_t: 0, category: 'SAFETY', severity: 'warning', description: 'blocked hold', meta: {} },
  ],
  episode_metrics: null,
};

const SUMMARIES: ReplaySummary[] = [
  {
    id: 'replay-2',
    label: 'Rush hour · seed 7 · AI · partial',
    created_at: '2026-09-08T09:00:00Z',
    scenario_id: 'rush_hour',
    scenario_name: 'Rush hour',
    seed: 7,
    mode: 'AI',
    model_modes: { a2c: 'untrained', dqn: 'untrained' },
    config_digest: 'cfg0001',
    sim_duration_s: 30,
    decision_count: 5,
    episode_complete: false,
  },
  {
    id: 'replay-1',
    label: 'Normal traffic · seed 42 · AI · episode',
    created_at: '2026-09-08T08:00:00Z',
    scenario_id: 'normal',
    scenario_name: 'Normal traffic',
    seed: 42,
    mode: 'AI',
    model_modes: { a2c: 'untrained', dqn: 'untrained' },
    config_digest: 'cfg0001',
    sim_duration_s: 3600,
    decision_count: 600,
    episode_complete: true,
  },
];

vi.mock('../lib/api', () => ({
  ApiError: class ApiError extends Error {
    status: number;
    constructor(message: string, status = 0) {
      super(message);
      this.status = status;
    }
  },
  api: {
    replays: hoisted.replays,
    replay: hoisted.replay,
    captureReplay: hoisted.captureReplay,
    deleteReplay: hoisted.deleteReplay,
  },
  exportUrls: {
    experiment: (id: string, format: string) => `http://x/api/v1/export/experiments/${id}?format=${format}`,
    replay: (id: string, format: string) => `http://x/api/v1/export/replays/${id}?format=${format}`,
  },
}));

vi.mock('../lib/ws', () => ({
  socket: { onFrame: () => () => {}, onState: () => () => {}, connect: () => {}, command: () => true },
}));

import { ReplayLab } from './ReplayLab';

beforeEach(() => {
  hoisted.replays.mockReset().mockResolvedValue({ replays: SUMMARIES });
  hoisted.replay.mockReset().mockResolvedValue(DETAIL);
  hoisted.captureReplay.mockReset();
  hoisted.deleteReplay.mockReset().mockResolvedValue({ deleted: 'replay-2' });
});

afterEach(cleanup);

describe('ReplayLab', () => {
  it('lists captured replays with the partial / full-episode badge', async () => {
    render(<ReplayLab />);
    expect(await screen.findByText('Rush hour')).toBeInTheDocument();
    expect(screen.getByText('Normal traffic')).toBeInTheDocument();
    expect(screen.getByText('FULL EPISODE')).toBeInTheDocument();
    expect(screen.getAllByText('PARTIAL').length).toBeGreaterThanOrEqual(1);
  });

  it('auto-opens the newest replay and shows the coordinator → safety pipeline', async () => {
    render(<ReplayLab />);
    await waitFor(() => expect(hoisted.replay).toHaveBeenCalledWith('replay-2'));
    expect(await screen.findByText('AGENT RECOMMENDATIONS')).toBeInTheDocument();
    expect(screen.getByText('COORDINATOR')).toBeInTheDocument();
    expect(screen.getByText('SAFETY · AUTHORITATIVE')).toBeInTheDocument();
    // decision 1 of 5
    expect(screen.getByTestId('rpl-readout').textContent).toMatch(/1\s*\/\s*5/);
    expect(screen.getByText('a2c reason 0')).toBeInTheDocument();
    expect(screen.getByText(/vehicle-level playback is not captured/i)).toBeInTheDocument();
  });

  it('steps forward through decisions with the ▶ control', async () => {
    render(<ReplayLab />);
    await screen.findByText('AGENT RECOMMENDATIONS');

    fireEvent.click(screen.getByRole('button', { name: /next decision/i }));
    await waitFor(() => expect(screen.getByTestId('rpl-readout').textContent).toMatch(/2\s*\/\s*5/));
    // frame 1 has the safety override in the fixture
    expect(screen.getByText('BLOCKED_HOLD')).toBeInTheDocument();
    expect(screen.getByText('dqn reason 1')).toBeInTheDocument();
  });

  it('captures the current run and surfaces the result', async () => {
    hoisted.captureReplay.mockResolvedValue({
      ...SUMMARIES[0],
      id: 'replay-3',
      label: 'Normal traffic · seed 1 · AI · partial',
      decision_count: 7,
    });
    render(<ReplayLab />);
    await screen.findByText('Rush hour');

    fireEvent.click(screen.getByRole('button', { name: /capture current run/i }));
    await waitFor(() => expect(hoisted.captureReplay).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/captured .* 7 decisions/i)).toBeInTheDocument();
  });

  it('offers CSV / JSON download links for the open replay (R9 P4)', async () => {
    render(<ReplayLab />);
    await screen.findByText('AGENT RECOMMENDATIONS');
    const csv = screen.getByRole('link', { name: 'CSV' }) as HTMLAnchorElement;
    const json = screen.getByRole('link', { name: 'JSON' }) as HTMLAnchorElement;
    expect(csv.getAttribute('href')).toContain('/export/replays/replay-2?format=csv');
    expect(json.getAttribute('href')).toContain('/export/replays/replay-2?format=json');
  });

  it('shows a friendly message when there is nothing to capture (409)', async () => {
    const { ApiError } = await import('../lib/api');
    hoisted.captureReplay.mockRejectedValue(new (ApiError as new (m: string, s?: number) => Error)('conflict', 409));
    render(<ReplayLab />);
    await screen.findByText('Rush hour');

    fireEvent.click(screen.getByRole('button', { name: /capture current run/i }));
    expect(await screen.findByText(/run the simulation on the dashboard for a few decisions/i)).toBeInTheDocument();
  });
});
