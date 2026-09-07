/**
 * Wire types mirroring the backend schemas (backend/app/schemas, backend/app/api/serialize.py).
 * Keep in sync by hand - the backend is the source of truth.
 */

export type Approach = 'N' | 'E' | 'S' | 'W';
export type Phase = 'NS' | 'EW' | 'N' | 'E' | 'S' | 'W' | 'YELLOW' | 'ALL_RED';
export type ControlMode = 'AI' | 'FIXED_TIME' | 'MANUAL';
export type AgentKey = 'a2c' | 'dqn' | 'ppo';
export type SafetyAction =
  | 'APPLIED'
  | 'REWRITTEN_TRANSITION'
  | 'BLOCKED_HOLD'
  | 'FORCED_CHANGE'
  | 'EMERGENCY_TIMEOUT';
export type EventCategory = 'TRAFFIC' | 'AI' | 'EMERGENCY' | 'SAFETY' | 'VIOLATION' | 'SYSTEM';
export type Severity = 'info' | 'notice' | 'warning' | 'critical';

export interface LaneState {
  index: number;
  vehicle_count: number;
  queue_length: number;
  blocked: boolean;
}

export interface ApproachState {
  approach: Approach;
  vehicle_count: number;
  queue_length: number;
  mean_speed_mps: number;
  mean_wait_s: number;
  max_wait_s: number;
  density_veh_per_km: number;
  arrival_rate_vph: number;
  stops_last_window: number;
  lanes: LaneState[];
}

export interface TransitionState {
  kind: Phase;
  elapsed_s: number;
  total_s: number;
  from_phase: Phase;
  to_phase: Phase;
}

export interface SignalState {
  current_phase: Phase;
  served_phase: Phase;
  phase_elapsed_s: number;
  phase_remaining_min_s: number;
  phase_remaining_max_s: number;
  transition: TransitionState | null;
  allowed_next: Phase[];
  last_action: string | null;
  /** Authoritative per-approach aspect from the SignalController. */
  approach_colors: Record<Approach, SignalColor>;
}

export type SignalColor = 'GREEN' | 'YELLOW' | 'RED';

export interface EmergencyState {
  active: boolean;
  vehicle_id: string | null;
  type: string | null;
  approach: Approach | null;
  distance_m: number | null;
  speed_mps: number | null;
  eta_s: number | null;
  cleared_this_episode: number;
}

export interface ViolationEvent {
  id: string;
  t: number;
  approach: Approach;
  type: string;
  signal_state: string;
  severity: string;
}

export interface SafetySnapshot {
  violations_last_window: number;
  violations_total: number;
  unsafe_transitions_total: number;
  recent: ViolationEvent[];
}

export interface LiveEstimates {
  throughput_vph: number;
  departures_last_interval: number;
  fuel_l_per_s: number;
  co2_kg_per_s: number;
  fuel_l_total: number;
  co2_kg_total: number;
}

/** Vehicles arrive as parallel arrays (see backend/app/api/serialize.py). */
export interface VehicleArrays {
  id: string[];
  type: string[];
  approach: Approach[];
  lane: number[];
  x: number[];
  y: number[];
  heading: number[];
  speed: number[];
  wait: number[];
  state: string[];
  emergency: boolean[];
  violator: boolean[];
}

export interface CompactState {
  sim_time: number;
  step: number;
  control_mode: ControlMode;
  signal: SignalState;
  approaches: Record<Approach, ApproachState>;
  emergency: EmergencyState;
  safety: SafetySnapshot;
  environment: { weather: string; time_of_day: string; blocked_lanes: unknown[] };
  estimates: LiveEstimates;
  totals: { vehicles: number; queue: number };
  vehicles: VehicleArrays;
}

export interface RewardComponent {
  name: string;
  raw: number;
  weight: number;
  contribution: number;
}

export interface RewardBreakdown {
  components: RewardComponent[];
  total: number;
}

export interface AgentRecommendation {
  agent: AgentKey;
  action_index: number;
  action_name: string;
  target_phase: Phase;
  score: number;
  confidence: number;
  priority: number;
  reason: string;
  relevant_state: Record<string, number>;
  action_distribution: number[];
  value_estimate: number | null;
}

export interface AgentStatus {
  agent: AgentKey;
  model_version: string;
  trained_episodes: number;
  is_trained: boolean;
  device: string;
  last_action: string | null;
  last_reward: number | null;
  inference_latency_ms: number | null;
}

export interface LabelledFeature {
  name: string;
  value: number;
  group: string;
}

export interface AgentInspectorPayload {
  agent: AgentKey;
  status: AgentStatus;
  features: LabelledFeature[];
  action_distribution: number[];
  action_labels: string[];
  selected_action: string;
  value_estimate: number | null;
  advantage: number | null;
  reward: RewardBreakdown;
  reward_history: number[];
  decision_history: Record<string, unknown>[];
  training: Record<string, unknown>;
  extra: Record<string, unknown>;
}

export interface AgentSlice {
  recommendation: AgentRecommendation;
  reward_total: number | null;
  reward_breakdown: RewardBreakdown | null;
}

export type AgentUpdate = Partial<Record<AgentKey, AgentSlice>>;

export interface LadderStep {
  rung: string;
  outcome: string;
  detail: string;
}

export interface PhaseScore {
  phase: Phase;
  congestion: number;
  efficiency: number;
  throughput: number;
  stability: number;
  consensus_bonus: number;
  total: number;
}

export interface CoordinationDecision {
  candidate_phase: Phase;
  winner: string;
  basis: string;
  ladder_trace: LadderStep[];
  scores: PhaseScore[];
  recommendations: AgentRecommendation[];
}

export interface PhaseCommand {
  target_phase: Phase;
  request_extend_s: number | null;
  request_reduce: boolean;
  force_transition: boolean;
  source: string;
}

export interface SafetyResult {
  approved: boolean;
  command: PhaseCommand;
  original: Phase;
  action_taken: SafetyAction;
  violated_rules: string[];
  reason: string;
}

export interface CoordinationUpdate {
  coordination: CoordinationDecision;
  safety: SafetyResult;
  applied_phase: Phase;
  decision_id: string;
}

export interface MetricSnapshot {
  sim_time: number;
  window: string;
  traffic: {
    avg_waiting_s: number;
    avg_queue: number;
    throughput_vph: number;
    avg_travel_time_s: number;
    avg_speed_mps: number;
    stops_per_veh: number;
    idle_time_s: number;
  };
  environmental: {
    fuel_l_per_veh: number;
    co2_kg_per_veh: number;
    fuel_l_total: number;
    co2_kg_total: number;
  };
  emergency: {
    emergency_wait_s: number;
    emergency_travel_time_s: number;
    emergency_delay_s: number;
    emergency_cleared: number;
  };
  safety: {
    red_light_violations: number;
    other_violations: number;
    unsafe_transitions: number;
  };
  dev: {
    fps: number;
    frame_time_ms: number;
    ai_latency_ms: number;
    sim_step_ms: number;
    ws_latency_ms: number;
    memory_mb: number;
  } | null;
}

export interface EventMessage {
  id: string;
  t: number;
  wall_t: number;
  category: EventCategory;
  severity: Severity;
  description: string;
  meta: Record<string, unknown>;
}

export interface SimStatus {
  running: boolean;
  mode: ControlMode;
  speed: number;
  adapter: string;
  scenario: { id: string; name: string; duration_s: number; seed: number };
  sim_time: number;
  step: number;
  episode_done: boolean;
  seq: number;
  agents: Record<AgentKey, AgentStatus>;
  safety: { overrides_total: number; checks_total: number };
  config_digest: string;
  env: string;
}

export interface ScenarioSummary {
  id: string;
  name: string;
  description: string;
  preset: boolean;
  arrivals_vph: number;
  weights: Record<string, number>;
  emergency_probability_per_min: number;
  duration_s: number;
}

export interface HelloPayload {
  protocol_version: string;
  config_digest: string;
  adapter: string;
  status: SimStatus;
  channels: string[];
  stream_hz: number;
  server_time: number;
}

export type Frame =
  | { type: 'hello'; seq: number; t: number; payload: HelloPayload }
  | { type: 'simulation_state'; seq: number; t: number; payload: CompactState }
  | { type: 'signal_update'; seq: number; t: number; payload: SignalState }
  | { type: 'agent_update'; seq: number; t: number; payload: AgentUpdate }
  | { type: 'coordination_update'; seq: number; t: number; payload: CoordinationUpdate }
  | { type: 'metric_update'; seq: number; t: number; payload: MetricSnapshot }
  | { type: 'event'; seq: number; t: number; payload: EventMessage }
  | { type: 'status'; seq: number; t: number; payload: SimStatus }
  | {
      type: 'command_result';
      seq: number;
      t: number;
      payload: { action: string; result: Record<string, unknown> };
    }
  | {
      type: 'error';
      seq: number;
      t: number;
      payload: { code: string; message: string; detail?: Record<string, unknown> };
    }
  | { type: 'pong'; seq: number; t: number; payload: { server_time: number } };
