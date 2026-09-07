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
  /** Which weights each agent is running live: fresh init vs a validated checkpoint. */
  model_modes: Record<AgentKey, ModelMode>;
  /** Registry model id the trained weights came from, or null when untrained. */
  model_sources: Record<AgentKey, string | null>;
  config_digest: string;
  env: string;
}

export type ModelMode = 'untrained' | 'trained';

export type ScenarioDifficulty = 'easy' | 'moderate' | 'hard' | 'extreme';

export interface ScenarioSummary {
  id: string;
  name: string;
  description: string;
  preset: boolean;
  /** R9 §8A presentation metadata — display only, never touches the simulation. */
  objective: string;
  ai_focus: string;
  difficulty: ScenarioDifficulty;
  arrivals_vph: number;
  weights: Record<string, number>;
  emergency_probability_per_min: number;
  violation_probability_scale: number;
  blocked_lanes: { approach: string; lane: number }[];
  /** Count of mid-episode demand changes, not the changes themselves. */
  scheduled_changes: number;
  duration_s: number;
}

/** The full editable scenario blob — mirrors backend `ScenarioConfig`. */
export interface ScenarioConfig {
  id: string;
  name: string;
  description: string;
  objective: string;
  ai_focus: string;
  difficulty: ScenarioDifficulty;
  demand: {
    weights: Record<string, number>;
    arrivals_vph: number;
    turn_split: Record<string, number>;
  };
  scheduled_changes: {
    at_s: number;
    profile: { weights: Record<string, number>; arrivals_vph: number; turn_split: Record<string, number> };
  }[];
  emergency_probability_per_min: number;
  violation_probability_scale: number;
  accident_probability_per_min: number;
  blocked_lanes: { approach: string; lane: number }[];
  weather: string;
  time_of_day: string;
  duration_s: number;
  seed: number;
}

/* ------------------------------------------------------------------ training */

export type TrainingPhase = 'idle' | 'running' | 'completed' | 'failed';

export interface TrainingEpisode {
  episode: number;
  return: number;
  mean_reward: number;
  decisions: number;
  updates: number;
  safety_overrides: number;
  losses: Record<string, number>;
  wall_time_s: number;
  metrics: Record<string, number>;
}

export interface TrainingJob {
  run_id: string;
  agent: AgentKey;
  scenario: string;
  seed: number;
  episodes_requested: number;
  phase: TrainingPhase;
  episode: number;
  progress: number;
  started_at: string;
  finished_at: string | null;
  wall_time_s: number;
  error: string | null;
  returns: number[];
  last_episode: TrainingEpisode | null;
  final_checkpoint: string | null;
  final_model_version: string | null;
  registered_model_id: string | null;
}

export interface TrainingSnapshot {
  seq: number;
  running: boolean;
  job: TrainingJob | null;
  history?: TrainingRunSummary[];
}

export interface TrainingRunSummary {
  run_id: string;
  agent: AgentKey | null;
  scenario: string | null;
  seed: number | null;
  episodes: number;
  started_at: string | null;
  finished_at: string | null;
  wall_time_s: number | null;
  final_model_version: string | null;
  final_checkpoint: string | null;
  first_return: number | null;
  last_return: number | null;
  config_digest: string | null;
}

export interface TrainingRunDetail {
  run_id: string;
  agent: AgentKey;
  scenario: string;
  seed: number;
  episodes_requested: number;
  started_at: string;
  finished_at: string | null;
  wall_time_s: number;
  episode_seeds: number[];
  episode_returns: number[];
  episodes: TrainingEpisode[];
  checkpoints: string[];
  final_checkpoint: string | null;
  final_model_version: string | null;
  reproducibility: Record<string, unknown>;
}

export type ModelStatus = 'trained' | 'evaluated' | 'active' | 'archived';

export interface ModelRecord {
  id: string;
  agent: AgentKey;
  version: string;
  checkpoint_path: string;
  run_id: string;
  scenario: string;
  seed: number;
  episodes: number;
  training_config: Record<string, unknown>;
  reward_config: Record<string, unknown>;
  env_version: string;
  code_version: string | null;
  torch_version: string | null;
  created_at: string;
  evaluated_at: string | null;
  eval_scenario: string | null;
  eval_metrics: EvalComparison | null;
  status: ModelStatus;
  notes: string | null;
}

export interface EvalComparison {
  scenario: string;
  baseline: string;
  seeds: number[];
  n_episodes: number;
  metrics: Record<
    string,
    {
      lower_is_better: boolean;
      values: Record<
        string,
        { mean: number; ci_half_width: number; improvement_pct_vs_baseline: number | null }
      >;
    }
  >;
}

/* ---------------------------------------------------------------- experiments */

export type ExperimentController = 'fixed_time' | 'a2c' | 'dqn';
export type ExperimentModelMode = 'untrained' | 'active' | 'latest' | string;
export type ExperimentPhase = 'running' | 'completed' | 'failed';

/** One controller's per-metric aggregates over the experiment's seeds. */
export interface ExperimentResult {
  label: string;
  controller: ExperimentController;
  scenario: string;
  model_version: string | null;
  checkpoint: string | null;
  registry_id: string | null;
  model_mode: string;
  seeds: number[];
  aggregates: Record<string, { n: number; mean: number; median: number; std: number; min: number; max: number; ci_half_width: number }>;
  episodes: { seed: number; decisions: number; safety_overrides: number; metrics: Record<string, number> }[];
}

export interface ExperimentJob {
  experiment_id: string;
  name: string;
  scenario: string;
  controllers: ExperimentController[];
  seeds: number[];
  baseline: string;
  episode_seconds: number | null;
  phase: ExperimentPhase;
  current_controller: string | null;
  episodes_done: number;
  episodes_total: number;
  progress: number;
  started_at: string;
  finished_at: string | null;
  wall_time_s: number;
  error: string | null;
  comparison: EvalComparison | null;
  results: ExperimentResult[] | null;
  reproducibility: Record<string, unknown>;
}

export interface ExperimentSnapshot {
  seq: number;
  running: boolean;
  job: ExperimentJob | null;
  history?: ExperimentSummary[];
}

export interface ExperimentSummary {
  id: string;
  name: string;
  created_at: string;
  finished_at: string | null;
  wall_time_s: number;
  scenario: string;
  controllers: ExperimentController[];
  seeds: number[];
  episode_seconds: number | null;
  baseline: string;
  status: ExperimentPhase;
  error: string | null;
}

export interface ExperimentDetail extends ExperimentSummary {
  reproducibility: Record<string, unknown>;
  comparison: EvalComparison | null;
  results: ExperimentResult[] | null;
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
  | { type: 'training_update'; seq: number; t: number; payload: TrainingSnapshot }
  | { type: 'experiment_update'; seq: number; t: number; payload: ExperimentSnapshot }
  | { type: 'pong'; seq: number; t: number; payload: { server_time: number } };
