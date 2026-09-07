/**
 * Live model-mode selector. Each agent runs either fresh ("UNTRAINED") weights or a
 * validated registry checkpoint ("TRAINED"). The badge here mirrors the backend's
 * honest `is_trained` - it only reads TRAINED once a checkpoint with real training
 * episodes has actually loaded (MASTER_PROMPT sections 84, 114). Safety stays
 * authoritative in either mode (section 113).
 */

import { ACTIVE_AGENTS, AGENT_LABEL, NO_DATA } from '../lib/format';
import type { AgentKey } from '../lib/types';
import { socket } from '../lib/ws';
import { useSimStore } from '../store';
import { Badge } from './common/Primitives';

const AGENTS = ACTIVE_AGENTS;

export function ModelModeBar() {
  const status = useSimStore((s) => s.status);
  const online = useSimStore((s) => s.connection === 'open');

  const modes = status?.model_modes;
  const sources = status?.model_sources;

  const set = (agent: AgentKey, mode: 'untrained' | 'trained') => {
    socket.command('set_model', { agent, mode });
  };

  return (
    <div className="model-bar" role="group" aria-label="Live model mode">
      <span className="model-bar-title">LIVE MODEL</span>
      {AGENTS.map((a) => {
        const mode = modes?.[a] ?? 'untrained';
        const trained = mode === 'trained';
        return (
          <div className="model-bar-item" key={a}>
            <span className="model-bar-agent">{AGENT_LABEL[a]}</span>
            <div className="seg" role="group" aria-label={`${AGENT_LABEL[a]} weights`}>
              <button
                className={!trained ? 'active' : ''}
                disabled={!online}
                onClick={() => set(a, 'untrained')}
              >
                UNTRAINED
              </button>
              <button
                className={trained ? 'active' : ''}
                disabled={!online}
                onClick={() => set(a, 'trained')}
                title="Load this agent's active (or latest) registry checkpoint"
              >
                TRAINED
              </button>
            </div>
            <Badge tone={trained ? 'good' : 'warn'}>
              {trained ? sources?.[a] ?? 'TRAINED' : 'UNTRAINED'}
            </Badge>
          </div>
        );
      })}
      {!modes ? <span className="panel-sub">{NO_DATA}</span> : null}
    </div>
  );
}
