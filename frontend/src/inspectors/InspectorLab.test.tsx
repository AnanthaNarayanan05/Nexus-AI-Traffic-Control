import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type {
  AgentInspectorPayload,
  CompactState,
  CoordinationUpdate,
  EmergencyState,
  FullSimulationState,
  SignalState,
  SimStatus,
  VehicleDetail,
} from '../lib/types';

/**
 * The Inspectors page is a read-only view over data the stores already hold plus two
 * on-demand fetches (`GET /simulation/state`, `GET /agents/dqn`). These tests stub the
 * API client and the socket, drive the stores directly, and assert each sub-tab renders
 * its real data — the coordinator → authoritative-safety pipeline, the signal state
 * machine, the emergency priority response, the vehicle list, and the DQN replay
 * transitions. No simulation runs here.
 */

const hoisted = vi.hoisted(() => ({
  simulationState: vi.fn(),
  agent: vi.fn(),
}));

vi.mock('../lib/api', () => ({
  ApiError: class ApiError extends Error {
    status: number;
    constructor(message: string, status = 0) {
      super(message);
      this.status = status;
    }
  },
  api: {
    simulationState: hoisted.simulationState,
    agent: hoisted.agent,
  },
}));

vi.mock('../lib/ws', () => ({
  socket: { onFrame: () => () => {}, onState: () => () => {}, connect: () => {}, command: () => true },
}));

import { InspectorLab } from './InspectorLab';
import { useAgentStore, useSimStore } from '../store';

const SIGNAL: SignalState = {
  current_phase: 'NS',
  served_phase: 'NS',
  phase_elapsed_s: 8,
  phase_remaining_min_s: 2,
  phase_remaining_max_s: 30,
  transition: null,
  allowed_next: ['EW', 'YELLOW'],
  last_action: 'KEEP_GREEN',
  approach_colors: { N: 'GREEN', E: 'RED', S: 'GREEN', W: 'RED' },
};

const EMG_OFF: EmergencyState = {
  active: false,
  vehicle_id: null,
  type: null,
  approach: null,
  distance_m: null,
  speed_mps: null,
  eta_s: null,
  cleared_this_episode: 2,
};

const EMG_ON: EmergencyState = {
  active: true,
  vehicle_id: 'amb-1',
  type: 'ambulance',
  approach: 'E',
  distance_m: 80,
  speed_mps: 9,
  eta_s: 8.9,
  cleared_this_episode: 1,
};

function coord(over: Partial<CoordinationUpdate['coordination']> = {}): CoordinationUpdate {
  return {
    decision_id: 'dec-abcdef123456',
    applied_phase: 'NS',
    coordination: {
      candidate_phase: 'NS',
      winner: 'a2c',
      basis: 'weighted_score',
      ladder_trace: [
        { rung: 'safety', outcome: 'pass', detail: 'no conflict' },
        { rung: 'weighted_score', outcome: 'score', detail: 'NS best' },
      ],
      scores: [
        { phase: 'NS', congestion: 0.4, efficiency: 0.5, throughput: 0.3, stability: 0.1, consensus_bonus: 0.05, total: 1.35 },
        { phase: 'EW', congestion: 0.2, efficiency: 0.3, throughput: 0.2, stability: 0.1, consensus_bonus: 0, total: 0.8 },
      ],
      recommendations: [
        {
          agent: 'a2c',
          action_index: 0,
          action_name: 'MAINTAIN',
          target_phase: 'NS',
          score: 0.8,
          confidence: 0.7,
          priority: 0.2,
          reason: 'a2c keeps NS',
          relevant_state: { queue_ns: 12 },
          action_distribution: [1, 0, 0, 0, 0],
          value_estimate: 0.3,
        },
        {
          agent: 'dqn',
          action_index: 2,
          action_name: 'SWITCH_PHASE',
          target_phase: 'EW',
          score: 0.4,
          confidence: 0.5,
          priority: 0.1,
          reason: 'dqn wants EW',
          relevant_state: {},
          action_distribution: [0, 0, 1, 0, 0],
          value_estimate: null,
        },
      ],
      ...over,
    },
    safety: {
      approved: true,
      command: {
        target_phase: 'NS',
        request_extend_s: null,
        request_reduce: false,
        force_transition: false,
        source: 'coordinator',
      },
      original: 'NS',
      action_taken: 'APPLIED',
      violated_rules: [],
      reason: '',
    },
  };
}

const VEHICLES: VehicleDetail[] = [
  {
    id: 'car-1',
    type: 'car',
    approach: 'N',
    lane: 0,
    movement: 'through',
    x: 1,
    y: 2,
    heading: 0,
    speed_mps: 5,
    accel_mps2: 0.2,
    wait_s: 3,
    stops: 1,
    fuel_l: 0.01,
    co2_kg: 0.02,
    is_emergency: false,
    is_violator: false,
    state: 'driving',
  },
  {
    id: 'amb-1',
    type: 'ambulance',
    approach: 'E',
    lane: 1,
    movement: 'through',
    x: 3,
    y: 4,
    heading: 1.5,
    speed_mps: 9,
    accel_mps2: 0,
    wait_s: 0,
    stops: 0,
    fuel_l: 0.05,
    co2_kg: 0.1,
    is_emergency: true,
    is_violator: false,
    state: 'driving',
  },
];

const FULL_STATE = {
  sim_time: 30,
  step: 60,
  control_mode: 'AI',
  signal: SIGNAL,
  approaches: {},
  emergency: EMG_OFF,
  safety: { violations_last_window: 0, violations_total: 0, unsafe_transitions_total: 0, recent: [] },
  environment: { weather: 'clear', time_of_day: 'day', blocked_lanes: [] },
  estimates: {
    throughput_vph: 0,
    departures_last_interval: 0,
    fuel_l_per_s: 0,
    co2_kg_per_s: 0,
    fuel_l_total: 0,
    co2_kg_total: 0,
  },
  vehicles: VEHICLES,
} as unknown as FullSimulationState;

const DQN_INSPECT = {
  agent: 'dqn',
  extra: {
    epsilon: 0.05,
    replay_size: 128,
    q_values: { KEEP_GREEN: 0.3 },
    replay_sample: [
      {
        action: 'EXTEND_GREEN',
        reward: 0.5,
        done: false,
        state_summary: { queue_mean: 4 },
        next_state_summary: { queue_mean: 3 },
        info: {},
      },
      {
        action: 'SWITCH_PHASE',
        reward: -0.2,
        done: true,
        state_summary: { queue_mean: 6 },
        next_state_summary: { queue_mean: 6 },
        info: {},
      },
    ],
  },
} as unknown as AgentInspectorPayload;

const DQN_EMPTY = {
  agent: 'dqn',
  extra: { epsilon: 0, replay_size: 0, replay_sample: [] },
} as unknown as AgentInspectorPayload;

function setStores(opts: {
  coordination?: CoordinationUpdate | null;
  state?: Partial<CompactState> | null;
  status?: Partial<SimStatus> | null;
  a2cReason?: string;
} = {}) {
  useSimStore.setState({
    connection: 'open',
    state: (opts.state === undefined
      ? ({ signal: SIGNAL, emergency: EMG_OFF } as unknown as CompactState)
      : opts.state
        ? (opts.state as unknown as CompactState)
        : null),
    status: (opts.status === undefined
      ? ({ running: false, mode: 'AI' } as unknown as SimStatus)
      : opts.status
        ? (opts.status as unknown as SimStatus)
        : null),
  });
  useAgentStore.setState({
    coordination: opts.coordination === undefined ? coord() : opts.coordination,
    agents: opts.a2cReason
      ? {
          a2c: {
            recommendation: {
              agent: 'a2c',
              action_index: 2,
              action_name: 'SWITCH_EMERGENCY',
              target_phase: 'E',
              score: 0.9,
              confidence: 0.8,
              priority: 0.9,
              reason: opts.a2cReason,
              relevant_state: {},
              action_distribution: [0, 0, 1, 0, 0],
              value_estimate: 0.4,
            },
            reward_total: null,
            reward_breakdown: null,
          },
        }
      : {},
  });
}

beforeEach(() => {
  hoisted.simulationState.mockReset().mockResolvedValue(FULL_STATE);
  hoisted.agent.mockReset().mockResolvedValue(DQN_INSPECT);
  setStores();
});

afterEach(cleanup);

describe('InspectorLab', () => {
  it('shows the coordinator → authoritative-safety pipeline and the priority ladder', () => {
    render(<InspectorLab />);
    expect(screen.getByText('COORDINATION BRAIN')).toBeInTheDocument();
    expect(screen.getByText('COORDINATOR')).toBeInTheDocument();
    expect(screen.getByText('SAFETY · AUTHORITATIVE')).toBeInTheDocument();
    expect(screen.getByText('PRIORITY LADDER — why this decision won')).toBeInTheDocument();
    expect(screen.getByText('PHASE SCORES')).toBeInTheDocument();
    expect(screen.getByText('a2c keeps NS')).toBeInTheDocument();
    expect(screen.getByText('dqn wants EW')).toBeInTheDocument();
    expect(screen.getByText('SAFETY VERDICT')).toBeInTheDocument();
    expect(
      screen.getByText(/the agents recommend, it\s+decides what the signal actually does/i),
    ).toBeInTheDocument();
  });

  it('warns when the safety layer rewrote the coordinated choice', () => {
    setStores({
      coordination: {
        ...coord(),
        applied_phase: 'YELLOW',
        safety: {
          approved: false,
          command: {
            target_phase: 'EW',
            request_extend_s: null,
            request_reduce: false,
            force_transition: true,
            source: 'safety',
          },
          original: 'NS',
          action_taken: 'REWRITTEN_TRANSITION',
          violated_rules: ['unsafe_switch'],
          reason: 'inserted yellow',
        },
      },
    });
    render(<InspectorLab />);
    expect(screen.getByText(/the safety layer changed the coordinated choice/i)).toBeInTheDocument();
    expect(screen.getAllByText('REWRITTEN_TRANSITION').length).toBeGreaterThanOrEqual(1);
  });

  it('falls back to an empty state when there is no coordination decision', () => {
    setStores({ coordination: null, status: { running: false, mode: 'FIXED_TIME' } });
    render(<InspectorLab />);
    expect(screen.getByText(/coordination reasoning is produced only in AI mode/i)).toBeInTheDocument();
  });

  it('marks the current inspector view on its tab button (aria-pressed) and titles panels as headings', () => {
    render(<InspectorLab />);
    const coordTab = screen.getByRole('button', { name: 'Coordination brain' });
    const signalTab = screen.getByRole('button', { name: 'Signal' });
    expect(coordTab).toHaveAttribute('aria-pressed', 'true');
    expect(signalTab).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(signalTab);
    expect(coordTab).toHaveAttribute('aria-pressed', 'false');
    expect(signalTab).toHaveAttribute('aria-pressed', 'true');
    expect(
      screen.getByRole('heading', { name: 'SIGNAL STATE MACHINE' }),
    ).toBeInTheDocument();
  });

  it('renders the signal state machine and the authoritative per-approach aspect', () => {
    render(<InspectorLab />);
    fireEvent.click(screen.getByRole('button', { name: 'Signal' }));
    expect(screen.getByText('SIGNAL STATE MACHINE')).toBeInTheDocument();
    expect(screen.getByText('MIN GREEN')).toBeInTheDocument();
    expect(screen.getByText('MAX GREEN')).toBeInTheDocument();
    expect(screen.getByText('PER-APPROACH ASPECT')).toBeInTheDocument();
    expect(screen.getAllByText('GREEN').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/computed by the SignalController/i)).toBeInTheDocument();
  });

  it('shows the emergency vehicle and A2C priority response when one is active', () => {
    setStores({
      coordination: coord({
        ladder_trace: [
          { rung: 'safety', outcome: 'pass', detail: 'ok' },
          { rung: 'emergency', outcome: 'override', detail: 'ambulance on E' },
        ],
      }),
      state: { signal: SIGNAL, emergency: EMG_ON },
      a2cReason: 'clear the E approach',
    });
    render(<InspectorLab />);
    fireEvent.click(screen.getByRole('button', { name: 'Emergency vehicle' }));
    expect(screen.getByText('EMERGENCY VEHICLE')).toBeInTheDocument();
    expect(screen.getByText('amb-1')).toBeInTheDocument();
    expect(screen.getByText('A2C PRIORITY RESPONSE')).toBeInTheDocument();
    expect(screen.getByText(/ACTIVE — coordinator override/i)).toBeInTheDocument();
    expect(screen.getByText('clear the E approach')).toBeInTheDocument();
  });

  it('has an empty emergency state with the cleared count when none is active', () => {
    render(<InspectorLab />);
    fireEvent.click(screen.getByRole('button', { name: 'Emergency vehicle' }));
    expect(screen.getByText(/No emergency vehicle is in the network/i)).toBeInTheDocument();
  });

  it('polls the full state dump and lets a vehicle be selected for detail', async () => {
    render(<InspectorLab />);
    fireEvent.click(screen.getByRole('button', { name: 'Vehicles' }));
    await waitFor(() => expect(hoisted.simulationState).toHaveBeenCalled());
    expect(await screen.findByText('VEHICLES IN THE NETWORK')).toBeInTheDocument();
    expect(screen.getByText('car-1')).toBeInTheDocument();
    fireEvent.click(screen.getByText('car-1'));
    expect(await screen.findByText('VEHICLE car-1')).toBeInTheDocument();
    expect(screen.getByText(/Snapshot polled every 2s/i)).toBeInTheDocument();
  });

  it('selects a vehicle from the keyboard (Space on the option row)', async () => {
    render(<InspectorLab />);
    fireEvent.click(screen.getByRole('button', { name: 'Vehicles' }));
    const row = await screen.findByRole('option', { name: /car-1/ });
    expect(row).toHaveAttribute('tabindex', '0');
    fireEvent.keyDown(row, { key: ' ' });
    expect(await screen.findByText('VEHICLE car-1')).toBeInTheDocument();
  });

  it('filters the vehicle list to emergencies only', async () => {
    render(<InspectorLab />);
    fireEvent.click(screen.getByRole('button', { name: 'Vehicles' }));
    expect(await screen.findByText('car-1')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/emergency only/i));
    await waitFor(() => expect(screen.queryByText('car-1')).not.toBeInTheDocument());
    expect(screen.getByText(/amb-1/)).toBeInTheDocument();
  });

  it('renders sampled DQN replay transitions from the inspector payload', async () => {
    render(<InspectorLab />);
    fireEvent.click(screen.getByRole('button', { name: 'DQN experience replay' }));
    await waitFor(() => expect(hoisted.agent).toHaveBeenCalledWith('dqn'));
    expect(await screen.findByText('DQN EXPERIENCE REPLAY')).toBeInTheDocument();
    expect(screen.getByText('SAMPLED TRANSITIONS')).toBeInTheDocument();
    expect(screen.getAllByText('EXTEND_GREEN').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('reward 0.500')).toBeInTheDocument();
    expect(screen.getByText(/each row below is one stored transition/i)).toBeInTheDocument();
  });

  it('shows an empty DQN replay state when the buffer has not filled', async () => {
    hoisted.agent.mockResolvedValue(DQN_EMPTY);
    render(<InspectorLab />);
    fireEvent.click(screen.getByRole('button', { name: 'DQN experience replay' }));
    expect(await screen.findByText(/The replay buffer is empty/i)).toBeInTheDocument();
  });
});
