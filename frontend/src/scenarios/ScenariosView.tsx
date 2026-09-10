import { useState } from 'react';

import type { Route } from '../lib/hashRoute';
import type { ScenarioDifficulty } from '../lib/types';
import { socket } from '../lib/ws';
import { useSimStore } from '../store';
import { ScenarioLab } from './ScenarioLab';

/**
 * The scenario picker a customer meets (R11 §19–§21): a card per scenario with a
 * plain title, one-line description, difficulty and purpose — no internal ids, no
 * arrival-rate numbers. "Create a custom scenario" reveals the full builder unchanged.
 */

const DIFFICULTY_LABEL: Record<ScenarioDifficulty, string> = {
  easy: 'Gentle',
  moderate: 'Moderate',
  hard: 'Demanding',
  extreme: 'Extreme',
};

/**
 * Present the backend's scenario copy in customer language (R11 §19): drop internal
 * slide references and swap algorithm names for what they do. Display only — the
 * stored scenario text is untouched.
 */
function customerCopy(text: string): string {
  return text
    .replace(/\s*\(PPT slide[^)]*\)/gi, '')
    .replace(/\bthe A2C stress case\b/gi, 'the emergency-response stress case')
    .replace(/\bthe DQN stress case\b/gi, 'the efficiency stress case')
    .replace(/\bthe PPO stress case\b/gi, 'the congestion stress case')
    .replace(/\bA2C\b/g, 'emergency response')
    .replace(/\bDQN\b/g, 'traffic efficiency')
    .replace(/\bPPO\b/g, 'congestion management')
    .trim();
}

export function ScenariosView({ go }: { go: (r: Route) => void }) {
  const scenarios = useSimStore((s) => s.scenarios);
  const online = useSimStore((s) => s.connection === 'open');
  const [custom, setCustom] = useState(false);
  const [starting, setStarting] = useState<string | null>(null);

  const start = (id: string) => {
    if (!online) return;
    setStarting(id);
    socket.command('set_mode', { mode: 'AI' });
    window.setTimeout(() => socket.command('load_scenario', { id }), 120);
    window.setTimeout(() => socket.command('start'), 300);
    window.setTimeout(() => go('live'), 360);
  };

  return (
    <main className="page scenarios">
      <header className="page-head">
        <h1>Scenarios</h1>
        <p>
          Pick a traffic situation to watch NEXUS handle. Each one runs on the same
          intersection with the same safety rules — only the demand changes.
        </p>
        <button className="btn-cta sm" onClick={() => setCustom((v) => !v)}>
          {custom ? 'Back to scenarios' : 'Create a custom scenario'}
        </button>
      </header>

      {custom ? (
        <ScenarioLab />
      ) : scenarios.length === 0 ? (
        <p className="empty-note">
          No scenarios are available yet. Once the traffic network is online they will
          appear here.
        </p>
      ) : (
        <div className="scenario-cards">
          {scenarios.map((s) => (
            <article className="scenario-card" key={s.id}>
              <div className="scenario-card-top">
                <h2>{s.name}</h2>
                <span className={`difficulty ${s.difficulty}`}>
                  {DIFFICULTY_LABEL[s.difficulty] ?? s.difficulty}
                </span>
              </div>
              <p className="scenario-card-desc">{customerCopy(s.description)}</p>
              {s.objective ? (
                <p className="scenario-card-purpose">
                  <span>Purpose</span> {customerCopy(s.objective)}
                </p>
              ) : null}
              <button
                className="btn-cta sm primary"
                disabled={!online || starting === s.id}
                onClick={() => start(s.id)}
              >
                {starting === s.id ? 'Starting…' : 'Start this scenario'}
              </button>
            </article>
          ))}
        </div>
      )}
    </main>
  );
}
