import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import type { Frame } from '../lib/types';

/**
 * The socket is replaced with a stub that just captures the handlers `wireSocket`
 * registers, so we can push synthetic frames through the exact dispatch path the app
 * uses and assert how each frame lands in the stores.
 */
const hoisted = vi.hoisted(() => ({
  frameHandlers: [] as ((f: Frame) => void)[],
  stateHandlers: [] as ((s: string, d?: string) => void)[],
}));

vi.mock('../lib/ws', () => ({
  socket: {
    onFrame: (fn: (f: Frame) => void) => {
      hoisted.frameHandlers.push(fn);
      return () => {};
    },
    onState: (fn: (s: string, d?: string) => void) => {
      hoisted.stateHandlers.push(fn);
      return () => {};
    },
    connect: () => {},
    command: () => true,
  },
}));

import {
  ALL_CATEGORIES,
  onSimulationState,
  useAgentStore,
  useEventStore,
  useSimStore,
  useTrainingStore,
  wireSocket,
} from './index';

// Frames here are deliberately partial: each test sends only the fields the reducer
// under test reads. The real wire frames are fully typed in lib/types.ts.
function dispatch(frame: { type: string; payload: unknown }): void {
  hoisted.frameHandlers.forEach((fn) => fn(frame as unknown as Frame));
}

function setConnection(state: string, detail?: string): void {
  hoisted.stateHandlers.forEach((fn) => fn(state, detail));
}

const compactState = (over: Record<string, unknown> = {}) =>
  ({
    sim_time: 12,
    step: 24,
    signal: { current_phase: 'NS', served_phase: 'NS', approach_colors: {} },
    approaches: {},
    vehicles: { id: [] },
    ...over,
  }) as unknown;

beforeAll(() => {
  wireSocket();
  expect(hoisted.frameHandlers).toHaveLength(1);
});

beforeEach(() => {
  useSimStore.setState({
    connection: 'connecting',
    connectionDetail: null,
    state: null,
    status: null,
    metrics: null,
    configDigest: null,
    lastError: null,
  });
  useAgentStore.setState({ agents: {}, coordination: null });
  useEventStore.setState({ events: [], filters: new Set(ALL_CATEGORIES) });
  useTrainingStore.setState({ snapshot: null });
});

describe('connection state', () => {
  it('mirrors the socket connection state and detail', () => {
    setConnection('open');
    expect(useSimStore.getState().connection).toBe('open');
    setConnection('closed', 'backend restarted');
    expect(useSimStore.getState().connection).toBe('closed');
    expect(useSimStore.getState().connectionDetail).toBe('backend restarted');
  });
});

describe('frame dispatch', () => {
  it('hello populates status and config digest', () => {
    dispatch({
      type: 'hello',
      payload: { status: { running: false, mode: 'AI' }, config_digest: 'abc123' },
    });
    expect(useSimStore.getState().configDigest).toBe('abc123');
    expect(useSimStore.getState().status).toMatchObject({ mode: 'AI' });
  });

  it('simulation_state updates the store and notifies render-path listeners', () => {
    const seen: unknown[] = [];
    const off = onSimulationState((s) => seen.push(s));

    dispatch({ type: 'simulation_state', payload: compactState() });

    expect(useSimStore.getState().state).toMatchObject({ step: 24 });
    expect(seen).toHaveLength(1);
    off();

    dispatch({ type: 'simulation_state', payload: compactState({ step: 99 }) });
    expect(seen).toHaveLength(1); // unsubscribed
    expect(useSimStore.getState().state).toMatchObject({ step: 99 });
  });

  it('signal_update merges into the existing state only', () => {
    dispatch({ type: 'signal_update', payload: { current_phase: 'EW' } });
    expect(useSimStore.getState().state).toBeNull(); // no base state yet -> ignored

    dispatch({ type: 'simulation_state', payload: compactState() });
    dispatch({ type: 'signal_update', payload: { current_phase: 'EW', served_phase: 'EW' } });
    expect(useSimStore.getState().state?.signal).toMatchObject({ current_phase: 'EW' });
    expect(useSimStore.getState().state?.step).toBe(24); // rest of the state untouched
  });

  it('status and metric_update land in their slots', () => {
    dispatch({ type: 'status', payload: { running: true, mode: 'FIXED_TIME' } });
    expect(useSimStore.getState().status).toMatchObject({ running: true });

    dispatch({ type: 'metric_update', payload: { sim_time: 30, traffic: {} } });
    expect(useSimStore.getState().metrics).toMatchObject({ sim_time: 30 });
  });

  it('agent_update and coordination_update land in the agent store', () => {
    dispatch({ type: 'agent_update', payload: { a2c: { reward_total: 1.2 } } });
    expect(useAgentStore.getState().agents.a2c).toMatchObject({ reward_total: 1.2 });

    dispatch({ type: 'coordination_update', payload: { applied_phase: 'NS', decision_id: 'd1' } });
    expect(useAgentStore.getState().coordination).toMatchObject({ decision_id: 'd1' });
  });

  it('events are prepended newest-first and capped', () => {
    for (let i = 0; i < 5; i += 1) {
      dispatch({ type: 'event', payload: { id: `e${i}`, description: `event ${i}` } });
    }
    const ids = useEventStore.getState().events.map((e) => e.id);
    expect(ids[0]).toBe('e4');
    expect(ids).toHaveLength(5);
  });

  it('error frames are surfaced verbatim with a timestamp, and clearable', () => {
    dispatch({ type: 'error', payload: { code: 'command_failed', message: 'unknown command' } });
    const err = useSimStore.getState().lastError;
    expect(err).toMatchObject({ code: 'command_failed', message: 'unknown command' });
    expect(typeof err?.at).toBe('number');

    useSimStore.getState().clearError();
    expect(useSimStore.getState().lastError).toBeNull();
  });

  it('training_update lands in the training store verbatim', () => {
    expect(useTrainingStore.getState().snapshot).toBeNull();
    dispatch({
      type: 'training_update',
      payload: { seq: 4, running: true, job: { run_id: 'a2c-x', phase: 'running', episode: 3 } },
    });
    const snap = useTrainingStore.getState().snapshot;
    expect(snap).toMatchObject({ seq: 4, running: true });
    expect(snap?.job).toMatchObject({ run_id: 'a2c-x', episode: 3 });
  });

  it('ignores unknown frame types without throwing', () => {
    expect(() => dispatch({ type: 'not_a_real_frame', payload: {} })).not.toThrow();
  });
});

describe('event filters', () => {
  it('start with every category enabled', () => {
    expect(useEventStore.getState().filters.size).toBe(ALL_CATEGORIES.length);
  });
  it('toggleFilter flips a single category', () => {
    useEventStore.getState().toggleFilter('SAFETY');
    expect(useEventStore.getState().filters.has('SAFETY')).toBe(false);
    useEventStore.getState().toggleFilter('SAFETY');
    expect(useEventStore.getState().filters.has('SAFETY')).toBe(true);
  });
});
