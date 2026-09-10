import type { Route } from '../lib/hashRoute';
import { useSimStore } from '../store';

/**
 * The product front door (R11 §6, §44). No technical detail and no internal metrics
 * before the customer starts — just what NEXUS is, three ways in, and an honest
 * system-status line read from the live connection.
 */

const HIGHLIGHTS: { title: string; body: string }[] = [
  {
    title: 'Emergency Response',
    body: 'Detects approaching ambulances and fire trucks and clears a path through the intersection.',
  },
  {
    title: 'Traffic Efficiency',
    body: 'Keeps vehicles moving with shorter waits, fewer stops and lower fuel use.',
  },
  {
    title: 'Congestion Management',
    body: 'Rebalances the signal when demand builds unevenly on one side of the junction.',
  },
  {
    title: 'Safety Enforcement',
    body: 'An always-on safety layer validates every signal change before it is applied.',
  },
];

export function Home({ go }: { go: (r: Route) => void }) {
  const connection = useSimStore((s) => s.connection);
  const status = useSimStore((s) => s.status);
  const online = connection === 'open';

  const statusRows: { label: string; ok: boolean; value: string }[] = [
    {
      label: 'System',
      ok: online,
      value: online ? 'Ready' : connection === 'connecting' ? 'Starting…' : 'Offline',
    },
    {
      label: 'Traffic network',
      ok: online,
      value: online ? 'Online' : 'Unavailable',
    },
    {
      label: 'AI control',
      ok: online,
      value: online ? 'Available' : 'Unavailable',
    },
  ];

  return (
    <main className="page home">
      <section className="home-hero">
        <p className="home-eyebrow">Intelligent Traffic Control</p>
        <h1 className="home-title">
          NEXUS keeps the intersection moving — <span>safely</span>.
        </h1>
        <p className="home-lead">
          Safer roads. Smarter traffic. NEXUS watches the junction in real time, gives
          priority to emergency vehicles, and eases congestion — with every decision
          checked by an independent safety layer.
        </p>
        <div className="home-ctas">
          <button className="btn-cta primary" onClick={() => go('live')}>
            Start live simulation
          </button>
          <button className="btn-cta" onClick={() => go('scenarios')}>
            Explore scenarios
          </button>
          <button className="btn-cta" onClick={() => go('insights')}>
            View insights
          </button>
        </div>
      </section>

      <section className="home-status" aria-label="System status">
        {statusRows.map((r) => (
          <div className="home-status-row" key={r.label}>
            <span className={r.ok ? 'status-dot ok' : 'status-dot down'} aria-hidden="true" />
            <span className="home-status-label">{r.label}</span>
            <span className="home-status-value">{r.value}</span>
          </div>
        ))}
        {status?.scenario?.name ? (
          <div className="home-status-row">
            <span className="status-dot ok" aria-hidden="true" />
            <span className="home-status-label">Loaded scenario</span>
            <span className="home-status-value">{status.scenario.name}</span>
          </div>
        ) : null}
      </section>

      <section className="home-highlights" aria-label="What NEXUS does">
        {HIGHLIGHTS.map((h) => (
          <article className="home-highlight" key={h.title}>
            <h2>{h.title}</h2>
            <p>{h.body}</p>
          </article>
        ))}
      </section>
    </main>
  );
}
