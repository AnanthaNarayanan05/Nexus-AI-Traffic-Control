import type {
  AgentInspectorPayload,
  AgentKey,
  AgentStatus,
  ExperimentController,
  ExperimentDetail,
  ExperimentSnapshot,
  FullSimulationState,
  MetricSnapshot,
  ModelRecord,
  ReplayDetail,
  ReplaySeek,
  ReplaySummary,
  ScenarioConfig,
  ScenarioSummary,
  SimStatus,
  TrainingRunDetail,
  TrainingRunSummary,
  TrainingSnapshot,
} from './types';

const BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}/api/v1${path}`, {
    // API responses are live state, never a static asset — don't let the browser
    // serve a stale disk-cached copy (e.g. after the backend restarts).
    cache: 'no-store',
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      /* body was not JSON */
    }
    throw new ApiError(detail, res.status);
  }
  return (await res.json()) as T;
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', body: JSON.stringify(body ?? {}) });

export const api = {
  health: () => request<{ status: string; adapter: string }>('/health'),
  config: () => request<Record<string, unknown>>('/config'),

  status: () => request<SimStatus>('/simulation/status'),
  /** Full state dump incl. per-vehicle detail — used by the Vehicle inspector on demand. */
  simulationState: () => request<FullSimulationState>('/simulation/state'),
  start: () => post<SimStatus>('/simulation/start'),
  pause: () => post<SimStatus>('/simulation/pause'),
  reset: (scenario_id?: string, seed?: number) =>
    post<SimStatus>('/simulation/reset', { scenario_id, seed }),
  step: (ticks = 1) => post<SimStatus>('/simulation/step', { ticks }),
  setMode: (mode: string) => post<SimStatus>('/simulation/mode', { mode }),
  setModel: (agent: AgentKey, mode: 'untrained' | 'trained', version?: string) =>
    post<SimStatus>('/simulation/model', { agent, mode, version: version ?? null }),
  setSpeed: (speed: number) => post<SimStatus>('/simulation/speed', { speed }),
  manual: (action: string) => post<Record<string, unknown>>('/simulation/manual', { action }),
  inject: (event: string, args: Record<string, unknown> = {}) =>
    post<{ injected: string; ids: string[] }>('/simulation/inject', { event, args }),

  scenarios: () => request<{ scenarios: ScenarioSummary[] }>('/scenarios'),
  scenario: (id: string) => request<ScenarioConfig>(`/scenarios/${id}`),
  loadScenario: (id: string, seed?: number) => post<SimStatus>('/scenarios/load', { id, seed }),
  createScenario: (config: ScenarioConfig) => post<ScenarioConfig>('/scenarios', config),
  duplicateScenario: (id: string, newId: string, name?: string) =>
    post<ScenarioConfig>(`/scenarios/${id}/duplicate`, { new_id: newId, name: name ?? null }),
  deleteScenario: (id: string) =>
    request<{ deleted: string }>(`/scenarios/${id}`, { method: 'DELETE' }),

  agents: () =>
    request<{
      agents: Record<AgentKey, AgentStatus>;
      ownership: Record<AgentKey, { objective: string; owner: string }>;
    }>('/agents'),
  agent: (name: AgentKey) => request<AgentInspectorPayload>(`/agents/${name}`),

  metrics: (dev = false, history = 0) =>
    request<{ current: MetricSnapshot; dev?: MetricSnapshot['dev']; history?: unknown[] }>(
      `/metrics?dev=${dev ? 1 : 0}&history=${history}`,
    ),
  safetyOverrides: (limit = 50) =>
    request<{
      overrides: Record<string, unknown>[];
      overrides_total: number;
      checks_total: number;
    }>(`/safety/overrides?limit=${limit}`),

  // ---- training + model registry (Slice 2) ----
  training: (history = 20) =>
    request<TrainingSnapshot>(`/training?history=${history}`),
  startTraining: (body: {
    agent: AgentKey;
    episodes: number;
    scenario?: string | null;
    seed?: number | null;
    checkpoint_every?: number;
  }) => post<TrainingSnapshot>('/training/runs', body),
  trainingRuns: (limit = 50) =>
    request<{ runs: TrainingRunSummary[] }>(`/training/runs?limit=${limit}`),
  trainingRun: (runId: string) => request<TrainingRunDetail>(`/training/runs/${runId}`),
  models: (agent?: AgentKey, status?: string) => {
    const q = new URLSearchParams();
    if (agent) q.set('agent', agent);
    if (status) q.set('status', status);
    const qs = q.toString();
    return request<{ models: ModelRecord[] }>(`/models${qs ? `?${qs}` : ''}`);
  },
  model: (modelId: string) => request<ModelRecord>(`/models/${modelId}`),

  // ---- replay: captured runs of the live decision loop (R9 P3) ----
  replays: (limit = 50) => request<{ replays: ReplaySummary[] }>(`/replay?limit=${limit}`),
  replay: (id: string) => request<ReplayDetail>(`/replay/${id}`),
  replayAt: (id: string, t: number) =>
    request<ReplaySeek>(`/replay/${id}/at?t=${encodeURIComponent(t)}`),
  captureReplay: () => post<ReplaySummary>('/replay/capture'),
  deleteReplay: (id: string) =>
    request<{ deleted: string }>(`/replay/${id}`, { method: 'DELETE' }),

  // ---- experiments: Fixed-Time vs AI comparison (R9 P1) ----
  experiments: (history = 20) =>
    request<ExperimentSnapshot>(`/experiments?history=${history}`),
  startExperiment: (body: {
    name?: string | null;
    scenario: string;
    controllers: ExperimentController[];
    seeds: number[];
    models?: Record<string, string>;
    episode_seconds?: number | null;
  }) => post<ExperimentSnapshot>('/experiments', body),
  experiment: (id: string) => request<ExperimentDetail>(`/experiments/${id}`),
};

export const API_BASE = BASE;

export type ExportFormat = 'csv' | 'json';

/**
 * Direct-download URLs for the export surface (R9 P4). These are plain `<a href>`
 * targets, not `fetch` calls — the backend sends `Content-Disposition: attachment`, so
 * the browser downloads the file and the SPA never navigates. `id`s are server-minted
 * (`exp-…` / `replay-…`), never user text, but encode defensively anyway.
 */
export const exportUrls = {
  experiment: (id: string, format: ExportFormat) =>
    `${BASE}/api/v1/export/experiments/${encodeURIComponent(id)}?format=${format}`,
  replay: (id: string, format: ExportFormat) =>
    `${BASE}/api/v1/export/replays/${encodeURIComponent(id)}?format=${format}`,
};
