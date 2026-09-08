import { useState } from 'react';

import { NO_DATA, clock, int } from '../lib/format';
import type { ControlMode } from '../lib/types';
import { socket } from '../lib/ws';
import { useSimStore } from '../store';
import { Badge } from './common/Primitives';

const MODES: ControlMode[] = ['AI', 'FIXED_TIME', 'MANUAL'];
const SPEEDS = [0.5, 1, 2, 4, 8];

const MANUAL_ACTIONS = ['HOLD', 'SWITCH', 'EXTEND', 'REDUCE', 'SET_NS', 'SET_EW'] as const;

export function CommandBar() {
  const status = useSimStore((s) => s.status);
  const state = useSimStore((s) => s.state);
  const scenarios = useSimStore((s) => s.scenarios);
  const connection = useSimStore((s) => s.connection);
  const configDigest = useSimStore((s) => s.configDigest);
  const [busy, setBusy] = useState(false);

  const online = connection === 'open';
  const running = status?.running ?? false;
  const mode = status?.mode ?? 'AI';
  const scenarioId = status?.scenario.id ?? '';

  // Every control goes over the WebSocket command channel so the manager applies it on
  // its own loop thread and the resulting status frame comes back to every client.
  const send = (action: string, args: Record<string, unknown> = {}) => {
    setBusy(true);
    socket.command(action, args);
    window.setTimeout(() => setBusy(false), 120);
  };

  return (
    <header className="command-bar">
      <div className="brand">
        <span className="brand-name">NEXUS</span>
        <span className="brand-sub">AI TRAFFIC CONTROL</span>
      </div>

      <div className="btn-group">
        <button
          className="btn primary"
          disabled={!online || busy}
          onClick={() => send(running ? 'pause' : 'start')}
        >
          {running ? '❚❚ Pause' : '▶ Start'}
        </button>
        <button
          className="btn"
          disabled={!online || busy || running}
          onClick={() => send('step', { ticks: 12 })}
          title="Advance 12 physics ticks (one decision interval) while paused"
        >
          ⏭ Step
        </button>
        <button
          className="btn danger"
          disabled={!online || busy}
          onClick={() => send('reset')}
          title="Reset the episode with the current scenario and seed"
        >
          ↺ Reset
        </button>
      </div>

      <div className="seg" role="group" aria-label="Control mode">
        {MODES.map((m) => (
          <button
            key={m}
            className={m === mode ? 'active' : ''}
            aria-pressed={m === mode}
            disabled={!online || busy}
            onClick={() => send('set_mode', { mode: m })}
          >
            {m === 'FIXED_TIME' ? 'FIXED' : m}
          </button>
        ))}
      </div>

      {mode === 'MANUAL' ? (
        <div className="btn-group">
          {MANUAL_ACTIONS.map((a) => (
            <button
              key={a}
              className="btn"
              disabled={!online || busy}
              onClick={() => send('manual', { action: a })}
            >
              {a}
            </button>
          ))}
        </div>
      ) : null}

      <select
        value={scenarioId}
        disabled={!online || busy || scenarios.length === 0}
        onChange={(e) => send('load_scenario', { id: e.target.value })}
        aria-label="Scenario"
      >
        {scenarios.length === 0 ? <option value="">{NO_DATA}</option> : null}
        {scenarios.map((s) => (
          <option key={s.id} value={s.id}>
            {s.name}
          </option>
        ))}
      </select>

      <select
        value={status?.speed ?? 1}
        disabled={!online || busy}
        onChange={(e) => send('set_speed', { speed: Number(e.target.value) })}
        aria-label="Simulation speed"
      >
        {SPEEDS.map((s) => (
          <option key={s} value={s}>
            {s}×
          </option>
        ))}
      </select>

      <button
        className="btn"
        disabled={!online || busy}
        onClick={() =>
          send('inject', {
            event: 'spawn_emergency',
            args: { approach: ['N', 'E', 'S', 'W'][Math.floor(Math.random() * 4)] },
          })
        }
        title="Spawn an emergency vehicle on a random approach"
      >
        🚑 Inject
      </button>

      <span className="spacer" />

      <Badge tone={running ? 'good' : 'neutral'}>{running ? 'LIVE' : 'PAUSED'}</Badge>
      <span className="clock" title="Simulation clock">
        {clock(state?.sim_time ?? status?.sim_time)}
      </span>
      <span className="panel-sub" title="Scenario duration">
        / {clock(status?.scenario.duration_s)}
      </span>
      <Badge tone="neutral" title="Random seed for this episode">
        seed {int(status?.scenario.seed)}
      </Badge>
      <Badge
        tone="neutral"
        title={`Config digest ${configDigest ?? status?.config_digest ?? NO_DATA}`}
      >
        cfg {(configDigest ?? status?.config_digest ?? NO_DATA).slice(0, 8)}
      </Badge>
      {status?.episode_done ? <Badge tone="warn">EPISODE COMPLETE</Badge> : null}
    </header>
  );
}
