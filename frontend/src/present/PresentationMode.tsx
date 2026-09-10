/**
 * Presentation mode (MASTER_PROMPT §24, §60-63, §108) — a full-screen, reduced-chrome
 * view for live demos.
 *
 * Minimal nav (one "exit" control), enlarged panels, and four scripted flagship demos.
 * Each demo pins a preset scenario to a fixed seed so a run on stage is bit-for-bit the
 * run rehearsed beforehand:
 *   1 — Emergency Response Challenge  (A2C)      → emergency_heavy
 *   2 — Efficiency Challenge          (DQN)      → high_stop_go
 *   3 — Congestion Reduction          (PPO)      → uneven
 *   4 — Mixed Crisis                  (full AI)  → mixed_crisis
 *
 * A launch is three ordinary commands on the same WebSocket the dashboard uses — set AI
 * mode, load the scenario at the pinned seed, start. The simulation, the agents and the
 * authoritative safety layer behave exactly as they do everywhere else; nothing here is
 * staged or pre-recorded (§84, §114).
 */

import { useCallback, useEffect, useState } from 'react';

import { Badge } from '../components/common/Primitives';
import { SimulationStage } from '../components/SimulationStage';
import { navigate } from '../lib/hashRoute';
import { CustomerMetrics } from '../live/CustomerMetrics';
import { DecisionFlow } from '../live/DecisionFlow';
import { SafetyStatus } from '../live/SafetyStatus';
import { socket } from '../lib/ws';
import { useSimStore } from '../store';

/**
 * Every flagship demo runs at this seed — the value in `configs/config.yaml`
 * (`simulation.seed`). Pinning it keeps a stage run reproducible (§80-83, §108).
 */
export const PRESENTATION_SEED = 42;

type DemoNumber = 1 | 2 | 3 | 4;

interface Demo {
  n: DemoNumber;
  name: string;
  agent: string;
  scenarioId: string;
  blurb: string;
  watch: string[];
}

const DEMOS: Demo[] = [
  {
    n: 1,
    name: 'Emergency Response Challenge',
    agent: 'Emergency Response',
    scenarioId: 'emergency_heavy',
    blurb:
      'Ambulances keep arriving while traffic is already heavy. NEXUS gives the emergency approach priority while the safety layer keeps every signal change safe.',
    watch: [
      'The emergency vehicle’s wait drops as NEXUS clears its path',
      'The decision switches to emergency priority',
      'Safety still approves or adjusts every change',
    ],
  },
  {
    n: 2,
    name: 'Efficiency Challenge',
    agent: 'Traffic Efficiency',
    scenarioId: 'high_stop_go',
    blurb:
      'Traffic arrives in stop-and-go bursts. NEXUS smooths the flow so vehicles stop less often, using less fuel.',
    watch: [
      'Stops per vehicle trends down',
      'Estimated fuel and CO₂ per vehicle settle lower',
      'Average speed rises without the queue growing',
    ],
  },
  {
    n: 3,
    name: 'Congestion Reduction',
    agent: 'Congestion Management',
    scenarioId: 'uneven',
    blurb:
      'Demand is much heavier on some approaches than others. NEXUS shifts green time toward the busy sides to cut queues and waiting time.',
    watch: [
      'Queue length and waiting time trend down',
      'Throughput holds while the busy approaches drain',
      'The decision reflects congestion management',
    ],
  },
  {
    n: 4,
    name: 'Mixed Crisis',
    agent: 'Full AI control',
    scenarioId: 'mixed_crisis',
    blurb:
      'Everything at once — an emergency, uneven demand and a red-light violation. All three capabilities, the coordinator and the safety layer handle the same moment.',
    watch: [
      'Each capability contributes a recommendation',
      'NEXUS picks one; the safety layer has the final say',
      'No unsafe signal transitions, even under load',
    ],
  },
];

export function PresentationMode() {
  const connection = useSimStore((s) => s.connection);
  const running = useSimStore((s) => s.status?.running ?? false);
  const [activeN, setActiveN] = useState<DemoNumber | null>(null);
  const [launching, setLaunching] = useState(false);

  const online = connection === 'open';
  const active = DEMOS.find((d) => d.n === activeN) ?? null;

  const launch = useCallback(
    (demo: Demo) => {
      if (!online) return;
      setActiveN(demo.n);
      setLaunching(true);
      // Three plain commands on the shared socket, spaced so the manager applies each on
      // its loop thread before the next arrives — the same path as the command bar.
      socket.command('set_mode', { mode: 'AI' });
      window.setTimeout(
        () => socket.command('load_scenario', { id: demo.scenarioId, seed: PRESENTATION_SEED }),
        160,
      );
      window.setTimeout(() => socket.command('start'), 340);
      window.setTimeout(() => setLaunching(false), 600);
    },
    [online],
  );

  const exit = useCallback(() => navigate(''), []);

  // Minimal keyboard nav: Esc leaves, 1 / 2 / 3 / 4 launch a demo. Never while a control has
  // focus (§64 — shortcuts don't fire while typing / adjusting an input).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName)) return;
      if (e.key === 'Escape') {
        exit();
        return;
      }
      const demo = DEMOS.find((d) => String(d.n) === e.key);
      if (demo) launch(demo);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [exit, launch]);

  return (
    <div className="present">
      <h1 className="sr-only">
        NEXUS traffic control — presentation{active ? `: demo ${active.n}, ${active.name}` : ''}
      </h1>
      <header className="present-top">
        <div className="present-brand">
          <span className="brand-name">NEXUS</span>
          <span className="present-tag">PRESENTATION</span>
        </div>

        <div className="present-now">
          {active ? (
            <>
              <span className="present-now-name">
                Demo {active.n} · {active.name}
              </span>
              <span className="present-now-sub">{active.agent}</span>
            </>
          ) : (
            <span className="present-now-sub">Choose a demonstration to begin</span>
          )}
        </div>

        <div className="present-top-right">
          {online ? (
            <Badge tone={running ? 'good' : 'neutral'}>{running ? 'LIVE' : 'PAUSED'}</Badge>
          ) : (
            <Badge tone="bad">backend offline</Badge>
          )}
          <button className="btn" onClick={exit} title="Leave presentation mode (Esc)">
            ✕ Exit presentation
          </button>
        </div>
      </header>

      <main className="present-main">
        <div className="present-stage">
          <SimulationStage minimalChrome />
          <DecisionFlow />
          <SafetyStatus />
          <CustomerMetrics />
        </div>

        <aside className="present-rail">
          <div className="present-demos">
            {DEMOS.map((d) => (
              <button
                key={d.n}
                type="button"
                className={d.n === activeN ? 'present-demo active' : 'present-demo'}
                onClick={() => launch(d)}
                disabled={!online || launching}
              >
                <span className="present-demo-n">{d.n}</span>
                <span className="present-demo-name">{d.name}</span>
                <span className="present-demo-agent">{d.agent}</span>
              </button>
            ))}
          </div>

          {active ? (
            <div className="present-brief">
              <p className="present-blurb">{active.blurb}</p>
              <span className="section-label">What to watch</span>
              <ul className="present-watch">
                {active.watch.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
              <button
                type="button"
                className="btn"
                onClick={() => launch(active)}
                disabled={!online || launching}
                title="Reload this scenario at the pinned seed and start again"
              >
                ↺ Restart this demo
              </button>
            </div>
          ) : (
            <p className="present-idle">
              Each demonstration runs the live NEXUS control loop on a fixed scenario —
              the coordinator and the always-on safety layer included. Nothing is
              pre-recorded.
            </p>
          )}
        </aside>
      </main>
    </div>
  );
}
