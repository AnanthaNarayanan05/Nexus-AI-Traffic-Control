import { useState } from 'react';

import { NO_DATA } from '../lib/format';
import { socket } from '../lib/ws';
import { useSimStore } from '../store';

const SPEEDS = [0.5, 1, 2, 4, 8];

/**
 * The customer-facing control strip for the live view (R11 §7, §28). Start / pause,
 * reset, scenario, speed, and a one-click "simulate an emergency vehicle". Control
 * mode, manual signal control and step-by-step advance stay in the engineering view.
 */
export function LiveControls() {
  const status = useSimStore((s) => s.status);
  const scenarios = useSimStore((s) => s.scenarios);
  const online = useSimStore((s) => s.connection === 'open');
  const [busy, setBusy] = useState(false);

  const running = status?.running ?? false;
  const scenarioId = status?.scenario?.id ?? '';

  const send = (action: string, args: Record<string, unknown> = {}) => {
    setBusy(true);
    socket.command(action, args);
    window.setTimeout(() => setBusy(false), 140);
  };

  return (
    <div className="live-controls" role="group" aria-label="Simulation controls">
      <button
        className="btn-cta primary sm"
        disabled={!online || busy}
        onClick={() => send(running ? 'pause' : 'start')}
      >
        {running ? 'Pause' : 'Start'}
      </button>
      <button
        className="btn-cta sm"
        disabled={!online || busy}
        onClick={() => send('reset')}
        title="Restart this scenario from the beginning"
      >
        Restart
      </button>

      <label className="live-field">
        <span>Scenario</span>
        <select
          value={scenarioId}
          disabled={!online || busy || scenarios.length === 0}
          onChange={(e) => send('load_scenario', { id: e.target.value })}
        >
          {scenarios.length === 0 ? <option value="">{NO_DATA}</option> : null}
          {scenarios.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
      </label>

      <label className="live-field">
        <span>Speed</span>
        <select
          value={status?.speed ?? 1}
          disabled={!online || busy}
          onChange={(e) => send('set_speed', { speed: Number(e.target.value) })}
        >
          {SPEEDS.map((s) => (
            <option key={s} value={s}>
              {s}×
            </option>
          ))}
        </select>
      </label>

      <button
        className="btn-cta sm ghost"
        disabled={!online || busy}
        onClick={() =>
          send('inject', {
            event: 'spawn_emergency',
            args: { approach: ['N', 'E', 'S', 'W'][Math.floor(Math.random() * 4)] },
          })
        }
        title="Send an emergency vehicle toward the intersection"
      >
        Simulate emergency vehicle
      </button>
    </div>
  );
}
