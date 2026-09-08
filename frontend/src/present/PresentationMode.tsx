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
import { CoordinationBar } from '../components/CoordinationBar';
import { MetricsRow } from '../components/MetricsRow';
import { SimulationStage } from '../components/SimulationStage';
import { navigate } from '../lib/hashRoute';
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
    agent: 'A2C · emergency prioritization',
    scenarioId: 'emergency_heavy',
    blurb:
      'Ambulances arrive under heavy traffic. A2C recommends holding green for the emergency approach; the safety layer still enforces minimum green and safe transitions.',
    watch: [
      'Emergency wait drops as A2C prioritises the approach',
      'Coordination basis flips to an emergency override',
      'Every forced change is still bounded by the safety layer',
    ],
  },
  {
    n: 2,
    name: 'Efficiency Challenge',
    agent: 'DQN · fuel / CO₂ / stops',
    scenarioId: 'high_stop_go',
    blurb:
      'Stop-and-go arrival bursts. DQN trades raw throughput for smoother flow — fewer stops per vehicle, so less fuel burned and less CO₂.',
    watch: [
      'Stops / veh trends down',
      'Fuel and CO₂ per vehicle (ESTIMATED) settle lower',
      'Average speed rises without the queue blowing up',
    ],
  },
  {
    n: 3,
    name: 'Congestion Reduction',
    agent: 'PPO · adaptive congestion reduction',
    scenarioId: 'uneven',
    blurb:
      'Unequal demand across the four approaches. PPO adapts the green split toward the busy approaches to cut queues and waiting time (R = −αQ − βW + γT); the safety layer still bounds every transition.',
    watch: [
      'Queue and average wait trend down as PPO reweights the split',
      'Throughput holds while the busy approaches drain',
      'Coordination basis shows the congestion term carrying the decision',
    ],
  },
  {
    n: 4,
    name: 'Mixed Crisis',
    agent: 'Full AI · coordination + safety',
    scenarioId: 'mixed_crisis',
    blurb:
      'Everything at once: an emergency, uneven demand, and a scripted violation. A2C, DQN, PPO, the coordinator and the safety layer all work the same decision.',
    watch: [
      'All three agents produce a recommendation every cycle',
      'The coordinator picks a winner; safety has the final say',
      'No unsafe transitions even under load',
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
            <span className="present-now-sub">
              Pick a flagship demo below — or press 1, 2, 3 or 4
            </span>
          )}
        </div>

        <div className="present-top-right">
          {online ? (
            <Badge tone={running ? 'good' : 'neutral'}>{running ? 'LIVE' : 'PAUSED'}</Badge>
          ) : (
            <Badge tone="bad">backend offline</Badge>
          )}
          <Badge tone="neutral" title="Every flagship demo is pinned to this seed">
            seed {PRESENTATION_SEED}
          </Badge>
          <button className="btn" onClick={exit} title="Back to the full dashboard (Esc)">
            ✕ Exit presentation
          </button>
        </div>
      </header>

      <main className="present-main">
        <div className="present-stage">
          <SimulationStage />
          <CoordinationBar />
          <MetricsRow />
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
              The four flagship demos each pin a preset scenario to seed {PRESENTATION_SEED} and run
              the live AI loop — the coordinator and the authoritative safety layer included. Nothing
              is pre-recorded.
            </p>
          )}
        </aside>
      </main>
    </div>
  );
}
