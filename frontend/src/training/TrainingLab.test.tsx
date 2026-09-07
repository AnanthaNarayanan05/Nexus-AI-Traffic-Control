import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ModelRecord, TrainingSnapshot } from '../lib/types';

/**
 * The lab is a thin view over the training REST + WS surface. These tests stub the API
 * client and assert the three-way TRAINING / EVALUATION / LIVE INFERENCE framing is
 * present and that registry rows render - not that any numbers are computed here.
 */

const hoisted = vi.hoisted(() => ({
  snapshot: {
    seq: 0,
    running: false,
    job: null,
    history: [],
  } as TrainingSnapshot,
  models: [] as ModelRecord[],
}));

vi.mock('../lib/api', () => ({
  ApiError: class ApiError extends Error {},
  api: {
    training: () => Promise.resolve(hoisted.snapshot),
    models: () => Promise.resolve({ models: hoisted.models }),
    startTraining: vi.fn(() => Promise.resolve(hoisted.snapshot)),
  },
}));

// The store pulls in lib/ws (a live socket); stub it so importing the store is inert.
vi.mock('../lib/ws', () => ({
  socket: { onFrame: () => () => {}, onState: () => () => {}, connect: () => {}, command: () => true },
}));

import { TrainingLab } from './TrainingLab';

beforeEach(() => {
  hoisted.snapshot = { seq: 0, running: false, job: null, history: [] };
  hoisted.models = [];
});

afterEach(cleanup);

describe('TrainingLab', () => {
  it('spells out the three distinct concepts', async () => {
    render(<TrainingLab />);
    expect(screen.getByText('TRAINING')).toBeInTheDocument();
    expect(screen.getByText('EVALUATION')).toBeInTheDocument();
    expect(screen.getByText('LIVE INFERENCE')).toBeInTheDocument();
    // let the mount-time fetch settle so cleanup doesn't race an unwrapped update
    await screen.findByText(/No training run this session/i);
  });

  it('shows the idle live-run state when nothing has run', async () => {
    render(<TrainingLab />);
    expect(
      await screen.findByText(/No training run this session/i),
    ).toBeInTheDocument();
  });

  it('renders a registry row from the API', async () => {
    hoisted.models = [
      {
        id: 'a2c-run-ep050',
        agent: 'a2c',
        version: 'a2c-v1.1-dev',
        checkpoint_path: 'models/a2c/latest.pt',
        run_id: 'a2c-run',
        scenario: 'emergency_heavy',
        seed: 0,
        episodes: 50,
        training_config: {},
        reward_config: {},
        env_version: '1',
        code_version: null,
        torch_version: null,
        created_at: '2026-09-07T10:00:00Z',
        evaluated_at: null,
        eval_scenario: null,
        eval_metrics: null,
        status: 'trained',
        notes: null,
      },
    ];
    render(<TrainingLab />);
    expect(await screen.findByText('a2c-run-ep050')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('TRAINED')).toBeInTheDocument());
  });
});
