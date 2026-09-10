import { useEffect, useState } from 'react';

import { ExportLinks } from '../components/common/ExportLinks';
import { api, exportUrls } from '../lib/api';
import { clock } from '../lib/format';
import type { Route } from '../lib/hashRoute';
import { navigateWith } from '../lib/hashRoute';
import type { ExperimentSummary, ReplaySummary } from '../lib/types';

/**
 * Customer-friendly run reports (R11 §26). Each captured run and each completed
 * comparison is a card with the scenario, when it ran and a one-line summary. The
 * CSV / JSON export stays available but quiet, underneath.
 */
export function ReportsView({ go }: { go: (r: Route) => void }) {
  const [replays, setReplays] = useState<ReplaySummary[] | null>(null);
  const [experiments, setExperiments] = useState<ExperimentSummary[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.replays(50), api.experiments(50)])
      .then(([r, e]) => {
        if (cancelled) return;
        setReplays(r.replays);
        setExperiments(e.history ?? []);
      })
      .catch(() => !cancelled && setError(true));
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="page reports">
      <header className="page-head">
        <h1>Reports</h1>
        <p>
          A record of every run NEXUS has captured and every comparison against a
          traditional fixed-timer signal.
        </p>
      </header>

      {error ? (
        <p className="empty-note">Reports aren&apos;t available right now. Please try again shortly.</p>
      ) : null}

      <section className="report-group">
        <h2>Captured runs</h2>
        {replays === null ? (
          <p className="empty-note">Loading…</p>
        ) : replays.length === 0 ? (
          <p className="empty-note">
            No runs captured yet. Open <button className="link-btn" onClick={() => go('live')}>Live</button> and
            let a scenario play through to capture one.
          </p>
        ) : (
          <div className="report-cards">
            {replays.map((r) => (
              <article className="report-card" key={r.id}>
                <div className="report-card-top">
                  <h3>{r.scenario_name}</h3>
                  <span className="report-when">{formatDate(r.created_at)}</span>
                </div>
                <p className="report-summary">
                  {clock(r.sim_duration_s)} of traffic · {r.decision_count} signal decisions ·{' '}
                  {r.episode_complete ? 'completed' : 'stopped early'}
                </p>
                <div className="report-card-foot">
                  <button className="link-btn" onClick={() => navigateWith('events', r.id)}>
                    Open event replay
                  </button>
                  <ExportLinks url={(f) => exportUrls.replay(r.id, f)} label="Export data" />
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="report-group">
        <h2>Comparisons</h2>
        {experiments === null ? (
          <p className="empty-note">Loading…</p>
        ) : experiments.length === 0 ? (
          <p className="empty-note">
            No comparisons yet. Run one from{' '}
            <button className="link-btn" onClick={() => go('insights')}>Insights</button>.
          </p>
        ) : (
          <div className="report-cards">
            {experiments.map((e) => (
              <article className="report-card" key={e.id}>
                <div className="report-card-top">
                  <h3>{e.name || e.scenario}</h3>
                  <span className="report-when">{formatDate(e.created_at)}</span>
                </div>
                <p className="report-summary">
                  {e.scenario} · {e.seeds.length} run{e.seeds.length === 1 ? '' : 's'} ·{' '}
                  {e.status === 'completed' ? 'complete' : e.status}
                </p>
                <div className="report-card-foot">
                  <button className="link-btn" onClick={() => go('insights')}>
                    View comparison
                  </button>
                  {e.status === 'completed' ? (
                    <ExportLinks url={(f) => exportUrls.experiment(e.id, f)} label="Export data" />
                  ) : null}
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}
