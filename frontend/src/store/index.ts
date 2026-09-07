import { create } from 'zustand';

import type { ConnectionState } from '../lib/ws';
import { socket } from '../lib/ws';
import type {
  AgentKey,
  AgentSlice,
  CompactState,
  CoordinationUpdate,
  EventCategory,
  EventMessage,
  Frame,
  MetricSnapshot,
  ScenarioSummary,
  SimStatus,
  TrainingSnapshot,
} from '../lib/types';

/* ------------------------------------------------------------------ simulation */

interface SimStore {
  connection: ConnectionState;
  connectionDetail: string | null;
  state: CompactState | null;
  status: SimStatus | null;
  metrics: MetricSnapshot | null;
  scenarios: ScenarioSummary[];
  configDigest: string | null;
  /** Last server-side command rejection, surfaced verbatim rather than swallowed. */
  lastError: { code: string; message: string; at: number } | null;
  setScenarios: (s: ScenarioSummary[]) => void;
  clearError: () => void;
}

export const useSimStore = create<SimStore>((set) => ({
  connection: 'connecting',
  connectionDetail: null,
  state: null,
  status: null,
  metrics: null,
  scenarios: [],
  configDigest: null,
  lastError: null,
  setScenarios: (scenarios) => set({ scenarios }),
  clearError: () => set({ lastError: null }),
}));

/* ------------------------------------------------------------------ agents */

interface AgentStore {
  agents: Partial<Record<AgentKey, AgentSlice>>;
  coordination: CoordinationUpdate | null;
}

export const useAgentStore = create<AgentStore>(() => ({
  agents: {},
  coordination: null,
}));

/* ------------------------------------------------------------------ events */

const MAX_EVENTS = 300;

interface EventStore {
  events: EventMessage[];
  filters: Set<EventCategory>;
  toggleFilter: (c: EventCategory) => void;
  clear: () => void;
}

export const ALL_CATEGORIES: EventCategory[] = [
  'TRAFFIC',
  'AI',
  'EMERGENCY',
  'SAFETY',
  'VIOLATION',
  'SYSTEM',
];

export const useEventStore = create<EventStore>((set) => ({
  events: [],
  filters: new Set(ALL_CATEGORIES),
  toggleFilter: (c) =>
    set((s) => {
      const next = new Set(s.filters);
      if (next.has(c)) next.delete(c);
      else next.add(c);
      return { filters: next };
    }),
  clear: () => set({ events: [] }),
}));

/* ------------------------------------------------------------------ training */

interface TrainingStore {
  /** Latest snapshot from the `training_update` WS channel, or null until one arrives. */
  snapshot: TrainingSnapshot | null;
}

export const useTrainingStore = create<TrainingStore>(() => ({
  snapshot: null,
}));

/* ------------------------------------------------------------------ wiring */

/**
 * Vehicle positions are consumed directly by the PixiJS stage rather than through
 * React state: at 20 Hz a store write per frame would re-render the whole tree.
 * Subscribe here for the render path.
 */
type StateListener = (state: CompactState) => void;
const stateListeners = new Set<StateListener>();

export function onSimulationState(listener: StateListener): () => void {
  stateListeners.add(listener);
  return () => stateListeners.delete(listener);
}

let wired = false;

export function wireSocket(): void {
  if (wired) return;
  wired = true;

  socket.onState((connection, detail) =>
    useSimStore.setState({ connection, connectionDetail: detail ?? null }),
  );

  socket.onFrame((frame: Frame) => {
    switch (frame.type) {
      case 'hello':
        useSimStore.setState({
          status: frame.payload.status,
          configDigest: frame.payload.config_digest,
        });
        break;
      case 'simulation_state':
        useSimStore.setState({ state: frame.payload });
        stateListeners.forEach((l) => l(frame.payload));
        break;
      case 'signal_update':
        useSimStore.setState((s) =>
          s.state ? { state: { ...s.state, signal: frame.payload } } : s,
        );
        break;
      case 'status':
        useSimStore.setState({ status: frame.payload });
        break;
      case 'metric_update':
        useSimStore.setState({ metrics: frame.payload });
        break;
      case 'agent_update':
        useAgentStore.setState({ agents: frame.payload });
        break;
      case 'coordination_update':
        useAgentStore.setState({ coordination: frame.payload });
        break;
      case 'event':
        useEventStore.setState((s) => ({
          events: [frame.payload, ...s.events].slice(0, MAX_EVENTS),
        }));
        break;
      case 'error':
        useSimStore.setState({
          lastError: { ...frame.payload, at: Date.now() },
        });
        break;
      case 'training_update':
        useTrainingStore.setState({ snapshot: frame.payload });
        break;
      default:
        break;
    }
  });

  socket.connect();
}
