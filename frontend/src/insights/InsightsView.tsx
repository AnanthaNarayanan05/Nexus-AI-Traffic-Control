import { useCallback, useEffect, useMemo, useState } from 'react';

import { ComparisonTable } from '../experiments/ComparisonTable';
import { ExperimentLab } from '../experiments/ExperimentLab';
import { ApiError, api } from '../lib/api';
import { AGENT_PRODUCT_BLURB } from '../lib/format';
import type { CapabilityRead, Verdict } from '../lib/comparisonRead';
import { capabilityReads } from '../lib/comparisonRead';
import type { ExperimentJob, ExperimentSnapshot } from '../lib/types';
import { useExperimentStore, useSimStore } from '../store';

/**
 * Insights (R11 §23): how NEXUS compares with a traditional fixed-timer signal, in
 * plain language. The customer runs one comparison, watches its progress, and reads a
 * per-capability summary. Every number is measured — the comparison, its repeat runs
 * and its confidence ranges come from the evaluation harness, never a manufactured
 * improvement (MASTER_PROMPT §84). The full measurement table and the detailed
 * comparison tools stay one disclosure away for internal and academic use (§51).
 */

const SEEDS = [1, 2, 3];
const AI_MODELS = { a2c: 'latest', dqn: 'latest', ppo: 'latest' } as const;

const VERDICT_WORD: Record<Verdict, string> = {
  better: 'Better',
  similar: 'About the same',
  worse: 'Worse',
  'no-data': 'Not enough data',
};

export function InsightsView() {
  const scenarios = useSimStore((s) => s.scenarios);
  const online = useSimStore((s) => s.connection === 'open');
  const wsSnap = useExperimentStore((s) => s.snapshot);

  const [scenario, setScenario] = useState('');
  const [rest, setRest] = useState<ExperimentSnapshot | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tableOpen, setTableOpen] = useState(false);
  const [advOpen, setAdvOpen] = useState(false);

  useEffect(() => {
    if (!scenario && scenarios.length) setScenario(scenarios[0].id);
  }, [scenarios, scenario]);

  const refresh = useCallback(async () => {
    try {
      setRest(await api.experiments(12));
    } catch {
      /* keep the last snapshot; the run card carries its own error state */
    }
  }, []);

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => void refresh(), 3500);
    return () => window.clearInterval(id);
  }, [refresh]);

  const job: ExperimentJob | null = wsSnap?.job ?? rest?.job ?? null;
  const running = (wsSnap?.running ?? rest?.running) ?? false;

  const run = async () => {
    if (!scenario || running || starting) return;
    setStarting(true);
    setError(null);
    try {
      await api.startExperiment({
        name: 'NEXUS vs a fixed timer',
        scenario,
        controllers: ['fixed_time', 'a2c', 'dqn', 'ppo'],
        seeds: SEEDS,
        models: { ...AI_MODELS },
      });
      setTableOpen(false);
      await refresh();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError('A comparison is already running — give it a moment to finish.');
      } else {
        setError(
          'Could not start the comparison. The traffic engine may be offline, or NEXUS has no trained model ready yet.',
        );
      }
    } finally {
      setStarting(false);
    }
  };

  const reads = useMemo<CapabilityRead[]>(
    () =>
      job && job.phase === 'completed' && job.comparison
        ? capabilityReads(job.comparison, job.results ?? [])
        : [],
    [job],
  );

  const jobScenarioName =
    scenarios.find((s) => s.id === job?.scenario)?.name ?? job?.scenario ?? '';

  return (
    <main className="page insights">
      <header className="page-head">
        <h1>Insights</h1>
        <p>
          NEXUS is measured against a traditional fixed-timer signal on the same
          scenario, with the same traffic and the same safety rules. Each comparison
          runs several times so the result reflects a real difference, not luck.
        </p>
      </header>

      <div className="insights-legend">
        <h2>How to read a comparison</h2>
        <ul>
          <li>
            <strong>Waiting time, queue length, stops</strong> — lower is better for
            drivers.
          </li>
          <li>
            <strong>Traffic cleared per hour</strong> — higher means more vehicles got
            through.
          </li>
          <li>
            <strong>Emergency vehicle delay</strong> — lower means a faster path through
            the intersection.
          </li>
          <li>
            A result is only called better or worse when the difference is larger than
            the normal run-to-run variation. Otherwise it reads{' '}
            <em>about the same</em>.
          </li>
        </ul>
      </div>

      <section className="cmp-run">
        <div className="cmp-run-head">
          <h2>Run a comparison</h2>
          <p>
            Pick a scenario and NEXUS will be scored against a fixed timer over{' '}
            {SEEDS.length} repeat runs each.
          </p>
        </div>

        <div className="cmp-run-controls">
          <label>
            <span>Scenario</span>
            <select
              value={scenario}
              onChange={(e) => setScenario(e.target.value)}
              disabled={running || starting}
            >
              {scenarios.length === 0 ? <option value="">No scenarios available</option> : null}
              {scenarios.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          <button
            className="btn-cta primary"
            type="button"
            onClick={run}
            disabled={!scenario || !online || running || starting}
          >
            {starting ? 'Starting…' : running ? 'Comparison running…' : 'Compare with a fixed timer'}
          </button>
        </div>

        {!online ? (
          <p className="cmp-run-note">The traffic engine is offline — comparisons are unavailable.</p>
        ) : null}
        {error ? <p className="cmp-run-error">{error}</p> : null}

        {job && job.phase === 'running' ? (
          <div className="cmp-progress">
            <div className="cmp-progress-track">
              <span
                className="cmp-progress-fill"
                style={{
                  width: `${Math.round((job.progress || 0) * 100)}%`,
                }}
              />
            </div>
            <p>
              Running comparison on {jobScenarioName || 'the selected scenario'} —{' '}
              {job.episodes_done} of {job.episodes_total} test runs complete.
            </p>
          </div>
        ) : null}

        {job && job.phase === 'failed' ? (
          <p className="cmp-run-error">
            The last comparison did not finish. Try running it again.
          </p>
        ) : null}
      </section>

      {job && job.phase === 'completed' && job.comparison ? (
        <section className="cmp-results">
          <h2>
            Result <span className="cmp-results-scenario">· {jobScenarioName}</span>
          </h2>

          {reads.length === 0 ? (
            <p className="empty-note">
              This comparison did not include a NEXUS capability. Open the measurement
              table below for the full detail.
            </p>
          ) : (
            <div className="cmp-read-grid">
              {reads.map((r) => (
                <article className="cmp-read" key={r.agent}>
                  <div className="cmp-read-top">
                    <h3>{r.title}</h3>
                    <span className={`cmp-read-verdict v-${r.verdict}`}>
                      {VERDICT_WORD[r.verdict]}
                    </span>
                  </div>
                  <p className="cmp-read-blurb">{AGENT_PRODUCT_BLURB[r.agent]}</p>
                  <p className="cmp-read-headline">{r.headline}</p>
                  <ul className="cmp-read-metrics">
                    {r.metrics.map((m) => (
                      <li key={m.label} className={`v-${m.verdict}`}>
                        <span className="cmp-read-metric-label">{m.label}</span>
                        <span className="cmp-read-metric-text">{m.text}</span>
                      </li>
                    ))}
                  </ul>
                </article>
              ))}
            </div>
          )}

          <details
            className="engineering"
            open={tableOpen}
            onToggle={(e) => setTableOpen((e.target as HTMLDetailsElement).open)}
          >
            <summary>Full measurement table</summary>
            <p className="engineering-note">
              Every metric, both signals side by side, with the 95% confidence range for
              each measurement.
            </p>
            {tableOpen ? (
              <ComparisonTable comparison={job.comparison} results={job.results ?? undefined} />
            ) : null}
          </details>
        </section>
      ) : null}

      <details
        className="engineering"
        open={advOpen}
        onToggle={(e) => setAdvOpen((e.target as HTMLDetailsElement).open)}
      >
        <summary>Detailed comparison tools</summary>
        <p className="engineering-note">
          Configure a comparison with a specific set of signals, repeat runs and episode
          length, and browse every comparison run so far. Intended for internal and
          academic use.
        </p>
        {advOpen ? <ExperimentLab /> : null}
      </details>
    </main>
  );
}
