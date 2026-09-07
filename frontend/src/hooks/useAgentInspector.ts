import { useEffect, useRef, useState } from 'react';

import { api } from '../lib/api';
import type { AgentInspectorPayload, AgentKey } from '../lib/types';
import { useSimStore } from '../store';

/**
 * Poll `GET /api/v1/agents/{name}` for the deep inspector payload.
 *
 * Not streamed: the full payload costs a forward pass per agent, so pushing it at the
 * 20 Hz stream rate would triple inference load for data that changes only once per
 * decision interval. The default period matches that interval.
 */
export function useAgentInspector(
  agent: AgentKey,
  periodMs = 2000,
): { data: AgentInspectorPayload | null; error: string | null } {
  const [data, setData] = useState<AgentInspectorPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inflight = useRef(false);
  const connection = useSimStore((s) => s.connection);

  useEffect(() => {
    if (connection !== 'open') return;
    let cancelled = false;

    const poll = async () => {
      if (inflight.current) return;
      inflight.current = true;
      try {
        const payload = await api.agent(agent);
        if (!cancelled) {
          setData(payload);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      } finally {
        inflight.current = false;
      }
    };

    void poll();
    const timer = window.setInterval(poll, periodMs);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [agent, periodMs, connection]);

  return { data, error };
}
