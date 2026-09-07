import type {
  AgentInspectorPayload,
  AgentKey,
  AgentStatus,
  MetricSnapshot,
  ScenarioSummary,
  SimStatus,
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
  start: () => post<SimStatus>('/simulation/start'),
  pause: () => post<SimStatus>('/simulation/pause'),
  reset: (scenario_id?: string, seed?: number) =>
    post<SimStatus>('/simulation/reset', { scenario_id, seed }),
  step: (ticks = 1) => post<SimStatus>('/simulation/step', { ticks }),
  setMode: (mode: string) => post<SimStatus>('/simulation/mode', { mode }),
  setSpeed: (speed: number) => post<SimStatus>('/simulation/speed', { speed }),
  manual: (action: string) => post<Record<string, unknown>>('/simulation/manual', { action }),
  inject: (event: string, args: Record<string, unknown> = {}) =>
    post<{ injected: string; ids: string[] }>('/simulation/inject', { event, args }),

  scenarios: () => request<{ scenarios: ScenarioSummary[] }>('/scenarios'),
  loadScenario: (id: string, seed?: number) => post<SimStatus>('/scenarios/load', { id, seed }),

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
};

export const API_BASE = BASE;
