import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ExperimentSnapshot, ScenarioSummary } from '../lib/types';

/**
 * The lab is a thin view over the experiment REST + WS surface. These tests stub the API
 * client and assert the framing (honest-comparison legend), the idle state, the controller
 * picker, and that a past experiment row renders - not that any metric is computed here.
 */

const hoisted = vi.hoisted(() => ({
  snapshot: { seq: 0, running: false, job: null, history: [] } as ExperimentSnapshot,
  experiment: vi.fn(),
}));

vi.mock('../lib/api', () => ({
  ApiError: class ApiError extends Error {},
  api: {
    experiments: () => Promise.resolve(hoisted.snapshot),
    startExperiment: vi.fn(() => Promise.resolve(hoisted.snapshot)),
    experiment: hoisted.experiment,
  },
  exportUrls: {
    experiment: (id: string, format: string) => `http://x/api/v1/export/experiments/${id}?format=${format}`,
    replay: (id: string, format: string) => `http://x/api/v1/export/replays/${id}?format=${format}`,
  },
}));

vi.mock('../lib/ws', () => ({
  socket: { onFrame: () => () => {}, onState: () => () => {}, connect: () => {}, command: () => true },
}));

import { useSimStore } from '../store';
import { ExperimentLab } from './ExperimentLab';

const SCENARIOS: ScenarioSummary[] = [
  {
    id: 'normal',
    name: 'Normal Traffic',
    description: '',
    preset: true,
    objective: 'baseline',
    ai_focus: 'both',
    difficulty: 'easy',
    arrivals_vph: 600,
    weights: {},
    emergency_probability_per_min: 0,
    violation_probability_scale: 1,
    blocked_lanes: [],
    scheduled_changes: 0,
    duration_s: 3600,
  },
];

beforeEach(() => {
  hoisted.snapshot = { seq: 0, running: false, job: null, history: [] };
  hoisted.experiment.mockReset().mockResolvedValue(null);
  useSimStore.setState({ scenarios: SCENARIOS });
});

afterEach(cleanup);

describe('ExperimentLab', () => {
  it('states the honest-comparison framing', async () => {
    render(<ExperimentLab />);
    expect(screen.getByText('HONEST COMPARISON')).toBeInTheDocument();
    expect(screen.getByText('DIRECTION MATTERS')).toBeInTheDocument();
    await screen.findByText(/No experiment this session/i);
  });

  it('offers Fixed-Time plus the two active AI controllers', async () => {
    render(<ExperimentLab />);
    expect(screen.getByText(/Fixed-Time \(baseline\)/)).toBeInTheDocument();
    expect(screen.getByText(/A2C — emergency/)).toBeInTheDocument();
    expect(screen.getByText(/DQN — efficiency/)).toBeInTheDocument();
    await screen.findByText(/No experiment this session/i);
  });

  it('offers CSV / JSON export on a completed experiment detail (R9 P4)', async () => {
    const { fireEvent } = await import('@testing-library/react');
    hoisted.snapshot = {
      seq: 1,
      running: false,
      job: null,
      history: [
        {
          id: 'exp-20260908T120000000Z',
          name: 'normal · fixed_time vs a2c',
          created_at: '2026-09-08T12:00:00Z',
          finished_at: '2026-09-08T12:00:20Z',
          wall_time_s: 20.4,
          scenario: 'normal',
          controllers: ['fixed_time', 'a2c'],
          seeds: [1, 2],
          episode_seconds: 90,
          baseline: 'fixed_time',
          status: 'completed',
          error: null,
        },
      ],
    };
    hoisted.experiment.mockResolvedValue({
      id: 'exp-20260908T120000000Z',
      name: 'normal · fixed_time vs a2c',
      created_at: '2026-09-08T12:00:00Z',
      finished_at: '2026-09-08T12:00:20Z',
      wall_time_s: 20.4,
      scenario: 'normal',
      controllers: ['fixed_time', 'a2c'],
      seeds: [1, 2],
      episode_seconds: 90,
      baseline: 'fixed_time',
      status: 'completed',
      error: null,
      reproducibility: { config_digest: 'abc' },
      comparison: {
        scenario: 'normal',
        baseline: 'fixed_time',
        seeds: [1, 2],
        n_episodes: 2,
        metrics: {},
      },
      results: [],
    });

    render(<ExperimentLab />);
    fireEvent.click(await screen.findByText('normal · fixed_time vs a2c'));

    const csv = (await screen.findByRole('link', { name: 'CSV' })) as HTMLAnchorElement;
    const json = screen.getByRole('link', { name: 'JSON' }) as HTMLAnchorElement;
    expect(csv.getAttribute('href')).toContain(
      '/export/experiments/exp-20260908T120000000Z?format=csv',
    );
    expect(json.getAttribute('href')).toContain(
      '/export/experiments/exp-20260908T120000000Z?format=json',
    );
  });

  it('renders a past experiment row from the API', async () => {
    hoisted.snapshot = {
      seq: 1,
      running: false,
      job: null,
      history: [
        {
          id: 'exp-20260908T120000000Z',
          name: 'normal · fixed_time vs a2c',
          created_at: '2026-09-08T12:00:00Z',
          finished_at: '2026-09-08T12:00:20Z',
          wall_time_s: 20.4,
          scenario: 'normal',
          controllers: ['fixed_time', 'a2c'],
          seeds: [1, 2],
          episode_seconds: 90,
          baseline: 'fixed_time',
          status: 'completed',
          error: null,
        },
      ],
    };
    render(<ExperimentLab />);
    expect(await screen.findByText('normal · fixed_time vs a2c')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('COMPLETED')).toBeInTheDocument());
  });

  it('opens a completed experiment row from the keyboard', async () => {
    const { fireEvent } = await import('@testing-library/react');
    hoisted.snapshot = {
      seq: 1,
      running: false,
      job: null,
      history: [
        {
          id: 'exp-20260908T120000000Z',
          name: 'normal · fixed_time vs a2c',
          created_at: '2026-09-08T12:00:00Z',
          finished_at: '2026-09-08T12:00:20Z',
          wall_time_s: 20.4,
          scenario: 'normal',
          controllers: ['fixed_time', 'a2c'],
          seeds: [1, 2],
          episode_seconds: 90,
          baseline: 'fixed_time',
          status: 'completed',
          error: null,
        },
      ],
    };
    hoisted.experiment.mockResolvedValue(null);
    render(<ExperimentLab />);
    const row = (await screen.findByText('normal · fixed_time vs a2c')).closest('tr') as HTMLElement;
    expect(row).toHaveAttribute('role', 'button');
    expect(row).toHaveAttribute('tabindex', '0');
    fireEvent.keyDown(row, { key: 'Enter' });
    await waitFor(() =>
      expect(hoisted.experiment).toHaveBeenCalledWith('exp-20260908T120000000Z'),
    );
  });
});
