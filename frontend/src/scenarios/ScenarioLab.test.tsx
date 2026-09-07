import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ScenarioConfig, ScenarioSummary } from '../lib/types';

/**
 * The Scenario Lab is a view over the /scenarios REST surface. These tests stub the API
 * client and assert: presets are read-only, a custom scenario is editable, "+ New"
 * slugifies the name into an id, the plain-English preview reflects the draft, and Save
 * calls the create endpoint. No simulation runs here.
 */

const hoisted = vi.hoisted(() => ({
  createScenario: vi.fn(),
  duplicateScenario: vi.fn(),
  deleteScenario: vi.fn(),
  loadScenario: vi.fn(),
}));

function cfg(over: Partial<ScenarioConfig>): ScenarioConfig {
  return {
    id: 'x',
    name: 'X',
    description: '',
    objective: '',
    ai_focus: '',
    difficulty: 'moderate',
    demand: { weights: { N: 0.25, E: 0.25, S: 0.25, W: 0.25 }, arrivals_vph: 1600, turn_split: { left: 0.2, through: 0.6, right: 0.2 } },
    scheduled_changes: [],
    emergency_probability_per_min: 0,
    violation_probability_scale: 1,
    accident_probability_per_min: 0,
    blocked_lanes: [],
    weather: 'clear',
    time_of_day: 'day',
    duration_s: 3600,
    seed: 42,
    ...over,
  };
}

const CONFIGS: Record<string, ScenarioConfig> = {
  normal: cfg({ id: 'normal', name: 'Normal traffic', objective: 'baseline', difficulty: 'easy' }),
  'my-one': cfg({ id: 'my-one', name: 'My One', objective: 'watch queues', difficulty: 'hard', demand: { weights: { N: 0.5, E: 0.1, S: 0.3, W: 0.1 }, arrivals_vph: 2400, turn_split: { left: 0.2, through: 0.6, right: 0.2 } } }),
};

vi.mock('../lib/api', () => ({
  ApiError: class ApiError extends Error {},
  api: {
    scenarios: () => Promise.resolve({ scenarios: SUMMARIES }),
    scenario: (id: string) => Promise.resolve(CONFIGS[id] ?? cfg({ id, name: id })),
    createScenario: hoisted.createScenario,
    duplicateScenario: hoisted.duplicateScenario,
    deleteScenario: hoisted.deleteScenario,
    loadScenario: hoisted.loadScenario,
  },
}));

vi.mock('../lib/ws', () => ({
  socket: { onFrame: () => () => {}, onState: () => () => {}, connect: () => {}, command: () => true },
}));

import { useSimStore } from '../store';
import { ScenarioLab } from './ScenarioLab';

const SUMMARIES: ScenarioSummary[] = [
  {
    id: 'normal', name: 'Normal traffic', description: 'baseline urban demand', preset: true,
    objective: 'Establish the reference', ai_focus: 'both', difficulty: 'easy',
    arrivals_vph: 1600, weights: { N: 0.25, E: 0.25, S: 0.25, W: 0.25 },
    emergency_probability_per_min: 0.25, violation_probability_scale: 1,
    blocked_lanes: [], scheduled_changes: 0, duration_s: 3600,
  },
  {
    id: 'my-one', name: 'My One', description: '', preset: false,
    objective: 'watch queues', ai_focus: 'dqn', difficulty: 'hard',
    arrivals_vph: 2400, weights: { N: 0.5, E: 0.1, S: 0.3, W: 0.1 },
    emergency_probability_per_min: 0, violation_probability_scale: 1,
    blocked_lanes: [], scheduled_changes: 0, duration_s: 3600,
  },
];

beforeEach(() => {
  hoisted.createScenario.mockReset().mockImplementation((c: ScenarioConfig) => Promise.resolve(c));
  hoisted.duplicateScenario.mockReset();
  hoisted.deleteScenario.mockReset().mockResolvedValue({ deleted: 'x' });
  hoisted.loadScenario.mockReset().mockResolvedValue({});
  useSimStore.setState({ scenarios: SUMMARIES });
});

afterEach(cleanup);

describe('ScenarioLab', () => {
  it('lists presets and custom scenarios with difficulty', async () => {
    render(<ScenarioLab />);
    expect(await screen.findByText('PRESETS · R9 §8A')).toBeInTheDocument();
    expect(screen.getByText('Normal traffic')).toBeInTheDocument();
    expect(screen.getByText('My One')).toBeInTheDocument();
    expect(screen.getAllByText('hard').length).toBeGreaterThanOrEqual(1);
  });

  it('shows a preset as read-only — no Save, only Duplicate to edit', async () => {
    render(<ScenarioLab />);
    // first scenario (normal, a preset) auto-selects
    expect(await screen.findByText('PRESET (READ-ONLY)')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /duplicate to edit/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /save changes/i })).not.toBeInTheDocument();
    expect(screen.getByText(/authoritative safety layer always runs/i)).toBeInTheDocument();
  });

  it('opens a custom scenario as editable with Save and Delete', async () => {
    render(<ScenarioLab />);
    fireEvent.click(await screen.findByText('My One'));
    expect(await screen.findByText('EDIT SCENARIO')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /save changes/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^delete$/i })).toBeInTheDocument();
  });

  it('"+ New" slugifies the name into the id and Save posts the draft', async () => {
    render(<ScenarioLab />);
    fireEvent.click(await screen.findByRole('button', { name: /\+ New/ }));
    expect(await screen.findByText('NEW SCENARIO')).toBeInTheDocument();

    const nameInput = screen.getByRole('textbox', { name: /^name$/i }) as HTMLInputElement;
    fireEvent.change(nameInput, { target: { value: 'Friday Rush!!' } });
    const idInput = screen.getByRole('textbox', { name: /id \(slug\)/i }) as HTMLInputElement;
    expect(idInput.value).toBe('friday-rush');

    fireEvent.click(screen.getByRole('button', { name: /save scenario/i }));
    await waitFor(() => expect(hoisted.createScenario).toHaveBeenCalledTimes(1));
    expect(hoisted.createScenario.mock.calls[0][0]).toMatchObject({ id: 'friday-rush', name: 'Friday Rush!!' });
  });

  it('the preview describes the draft in plain English', async () => {
    render(<ScenarioLab />);
    fireEvent.click(await screen.findByText('My One'));
    expect(await screen.findByText('PREVIEW')).toBeInTheDocument();
    expect(screen.getByText(/2,400 veh\/h/)).toBeInTheDocument();
    expect(screen.getByText(/heaviest from N/)).toBeInTheDocument();
  });
});
