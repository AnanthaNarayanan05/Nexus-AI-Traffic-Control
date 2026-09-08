/**
 * Experiment Lab - configure and run one Fixed-Time vs AI comparison, watch it live, and
 * browse past experiments (MASTER_PROMPT §16, §35 P1; docs/experiments.md).
 *
 * This is headless: evaluation builds its own adapters and never touches the live
 * dashboard simulation. One experiment runs at a time. Every metric shown by the
 * comparison table is a measured episode aggregate - nothing here is mocked (spec §84).
 */

import { useCallback, useEffect, useState } from 'react';

import { ExportLinks } from '../components/common/ExportLinks';
import { Badge, Empty, KV, Panel, SectionLabel } from '../components/common/Primitives';
import { activateOnKey } from '../lib/a11y';
import { ApiError, api, exportUrls } from '../lib/api';
import { NO_DATA, int, num } from '../lib/format';
import type {
  ExperimentController,
  ExperimentDetail,
  ExperimentJob,
  ExperimentSnapshot,
  ExperimentSummary,
  ScenarioSummary,
} from '../lib/types';
import { useExperimentStore, useSimStore } from '../store';
import { ComparisonTable } from './ComparisonTable';

const CONTROLLER_OPTIONS: { key: ExperimentController; label: string }[] = [
  { key: 'fixed_time', label: 'Fixed-Time (baseline)' },
  { key: 'a2c', label: 'A2C — emergency-vehicle priority' },
  { key: 'dqn', label: 'DQN — efficiency / fuel / emissions / safety' },
  { key: 'ppo', label: 'PPO — adaptive congestion reduction' },
];

const MODEL_MODES = ['untrained', 'active', 'latest'] as const;

function phaseTone(phase: string): 'good' | 'warn' | 'bad' | 'info' | 'neutral' {
  if (phase === 'running') return 'info';
  if (phase === 'completed') return 'good';
  if (phase === 'failed') return 'bad';
  return 'neutral';
}

function shortTime(iso: string | null): string {
  if (!iso) return NO_DATA;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return NO_DATA;
  return d.toLocaleString(undefined, {
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function parseSeeds(raw: string): number[] {
  const out: number[] = [];
  for (const tok of raw.split(/[\s,]+/)) {
    if (!tok.trim()) continue;
    const n = Number(tok);
    if (Number.isInteger(n) && !out.includes(n)) out.push(n);
  }
  return out;
}

/* ------------------------------------------------------------------ start form */

function StartExperimentForm({
  scenarios,
  disabled,
  onStarted,
}: {
  scenarios: ScenarioSummary[];
  disabled: boolean;
  onStarted: () => void;
}) {
  const [scenario, setScenario] = useState('');
  const [controllers, setControllers] = useState<Set<ExperimentController>>(
    new Set<ExperimentController>(['fixed_time', 'a2c']),
  );
  const [models, setModels] = useState<Record<string, string>>({ a2c: 'untrained', dqn: 'untrained' });
  const [seeds, setSeeds] = useState('1, 2, 3');
  const [episodeSeconds, setEpisodeSeconds] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!scenario && scenarios.length) setScenario(scenarios[0].id);
  }, [scenarios, scenario]);

  const toggle = (k: ExperimentController) =>
    setControllers((prev) => {
      const next = new Set(prev);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      return next;
    });

  const chosen = CONTROLLER_OPTIONS.map((c) => c.key).filter((k) => controllers.has(k));
  const selectedScenario = scenarios.find((s) => s.id === scenario) ?? null;
  const parsedSeeds = parseSeeds(seeds);
  const usesTrained = chosen.some((c) => c !== 'fixed_time' && (models[c] ?? 'untrained') !== 'untrained');
  const valid = scenario !== '' && chosen.length >= 1 && parsedSeeds.length >= 1;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.startExperiment({
        scenario,
        controllers: chosen,
        seeds: parsedSeeds,
        models: Object.fromEntries(
          chosen.filter((c) => c !== 'fixed_time').map((c) => [c, models[c] ?? 'untrained']),
        ),
        episode_seconds: episodeSeconds.trim() === '' ? null : Number(episodeSeconds),
      });
      onStarted();
    } catch (err) {
      setError(err instanceof ApiError ? `${err.status} · ${err.message}` : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel title="RUN A COMPARISON" accent="var(--accent)">
      <form className="train-form" onSubmit={submit}>
        <label>
          <span>Scenario</span>
          <select value={scenario} onChange={(e) => setScenario(e.target.value)}>
            {scenarios.length === 0 ? <option value="">loading…</option> : null}
            {scenarios.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name} · {s.difficulty}
                {s.preset ? '' : ' (custom)'}
              </option>
            ))}
          </select>
        </label>
        {selectedScenario ? (
          <p className="train-form-owner">
            {selectedScenario.objective || selectedScenario.description}
            {selectedScenario.ai_focus ? ` — ${selectedScenario.ai_focus}` : ''}
          </p>
        ) : null}

        <div className="cmp-controllers">
          <SectionLabel>CONTROLLERS</SectionLabel>
          {CONTROLLER_OPTIONS.map((c) => (
            <div key={c.key} className="cmp-controller-row">
              <label className="cmp-check">
                <input
                  type="checkbox"
                  checked={controllers.has(c.key)}
                  onChange={() => toggle(c.key)}
                />
                <span>{c.label}</span>
              </label>
              {c.key !== 'fixed_time' && controllers.has(c.key) ? (
                <select
                  aria-label={`${c.key} weights`}
                  value={models[c.key] ?? 'untrained'}
                  onChange={(e) => setModels((m) => ({ ...m, [c.key]: e.target.value }))}
                >
                  {MODEL_MODES.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              ) : null}
            </div>
          ))}
        </div>

        <div className="train-form-grid">
          <label>
            <span>Seeds (comma list)</span>
            <input
              type="text"
              inputMode="numeric"
              value={seeds}
              onChange={(e) => setSeeds(e.target.value)}
              placeholder="1, 2, 3"
            />
          </label>
          <label>
            <span>Episode seconds (optional)</span>
            <input
              type="text"
              inputMode="numeric"
              value={episodeSeconds}
              onChange={(e) => setEpisodeSeconds(e.target.value.replace(/[^0-9.]/g, ''))}
              placeholder="scenario length"
            />
          </label>
        </div>

        <p className="train-form-owner">
          {parsedSeeds.length} seed{parsedSeeds.length === 1 ? '' : 's'} × {chosen.length} controller
          {chosen.length === 1 ? '' : 's'} = {parsedSeeds.length * chosen.length} headless episodes.{' '}
          {usesTrained
            ? 'A trained checkpoint must already be in the registry or the run is rejected up front.'
            : 'AI controllers run from untrained weights unless you pick active / latest.'}
        </p>

        <div className="train-form-actions">
          <button className="btn primary" type="submit" disabled={disabled || busy || !valid}>
            {busy ? 'Starting…' : '▶ Run comparison'}
          </button>
          {disabled ? (
            <span className="panel-sub">an experiment is already running — one at a time</span>
          ) : null}
        </div>
        {error ? <p className="train-form-error">{error}</p> : null}
        <p className="panel-sub">
          Fixed-Time is the baseline. Every metric in the results table is a measured episode
          aggregate; the % change is only called an improvement when the metric moved the better
          way for its direction.
        </p>
      </form>
    </Panel>
  );
}

/* ------------------------------------------------------------------ live experiment */

function LiveExperiment({ job }: { job: ExperimentJob | null }) {
  if (!job) {
    return (
      <Panel title="LIVE EXPERIMENT" accent="var(--accent)">
        <Empty>No experiment this session. Configure one on the left and run it to watch here.</Empty>
      </Panel>
    );
  }

  const pct = Math.round((job.progress || 0) * 100);

  return (
    <Panel
      title="LIVE EXPERIMENT"
      accent="var(--accent)"
      actions={<Badge tone={phaseTone(job.phase)}>{job.phase.toUpperCase()}</Badge>}
    >
      <div className="train-run-head">
        <span className="train-run-id" title={job.experiment_id}>
          {job.name}
        </span>
        <span className="panel-sub">
          {job.scenario} · {job.seeds.length} seed{job.seeds.length === 1 ? '' : 's'} · baseline{' '}
          {job.baseline}
        </span>
      </div>

      <div className="train-progress">
        <div className="train-progress-track">
          <span
            className="train-progress-fill"
            style={{ width: `${pct}%`, background: 'var(--accent)' }}
          />
        </div>
        <span className="train-progress-label">
          {job.phase === 'running' && job.current_controller
            ? `running ${job.current_controller} · `
            : ''}
          {int(job.episodes_done)} / {int(job.episodes_total)} episodes · {pct}%
        </span>
      </div>

      {job.error ? <p className="train-form-error">{job.error}</p> : null}

      {job.phase === 'completed' && job.comparison ? (
        <>
          <SectionLabel>FIXED-TIME vs AI</SectionLabel>
          <ComparisonTable comparison={job.comparison} results={job.results ?? undefined} />
        </>
      ) : job.phase === 'running' ? (
        <Empty>
          Running headless episodes… the comparison table appears once every controller has
          finished all its seeds.
        </Empty>
      ) : null}
    </Panel>
  );
}

/* ------------------------------------------------------------------ history */

function ExperimentHistory({
  rows,
  activeId,
  onOpen,
}: {
  rows: ExperimentSummary[];
  activeId: string | null;
  onOpen: (id: string) => void;
}) {
  return (
    <Panel title="PAST EXPERIMENTS" accent="var(--text-dim)" sub={`${rows.length}`}>
      {rows.length === 0 ? (
        <Empty>No experiments recorded yet.</Empty>
      ) : (
        <div className="table-scroll">
          <table className="train-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Scenario</th>
                <th>Controllers</th>
                <th>Seeds</th>
                <th>Status</th>
                <th>Wall</th>
                <th>When</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const openable = r.status === 'completed';
                return (
                  <tr
                    key={r.id}
                    onClick={openable ? () => onOpen(r.id) : undefined}
                    onKeyDown={openable ? activateOnKey(() => onOpen(r.id)) : undefined}
                    tabIndex={openable ? 0 : undefined}
                    role={openable ? 'button' : undefined}
                    aria-label={openable ? `Open comparison for ${r.name}` : undefined}
                    className={
                      r.id === activeId ? 'cmp-row-active' : openable ? 'cmp-row-click' : ''
                    }
                    title={openable ? 'Open comparison' : (r.error ?? r.id)}
                  >
                    <td>{r.name}</td>
                    <td>{r.scenario}</td>
                    <td>{r.controllers.join(', ')}</td>
                    <td>{r.seeds.join(', ')}</td>
                    <td>
                      <Badge tone={phaseTone(r.status)}>{r.status.toUpperCase()}</Badge>
                    </td>
                    <td>{num(r.wall_time_s, 1)}s</td>
                    <td>{shortTime(r.created_at)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

/* ------------------------------------------------------------------ selected detail */

function SelectedExperiment({
  detail,
  onClose,
}: {
  detail: ExperimentDetail;
  onClose: () => void;
}) {
  const repro = Object.entries(detail.reproducibility).filter(
    ([, v]) => v === null || typeof v !== 'object',
  );

  return (
    <Panel
      title="SELECTED EXPERIMENT"
      accent="var(--accent)"
      actions={
        <div className="exp-detail-actions">
          <ExportLinks
            url={(f) => exportUrls.experiment(detail.id, f)}
            disabled={detail.status !== 'completed' || !detail.comparison}
            title="Download this comparison — CSV is one row per metric per controller, JSON is the full record"
          />
          <button className="btn" type="button" onClick={onClose}>
            Close
          </button>
        </div>
      }
    >
      <div className="train-run-head">
        <span className="train-run-id" title={detail.id}>
          {detail.name}
        </span>
        <span className="panel-sub">{shortTime(detail.created_at)}</span>
      </div>

      {detail.status === 'completed' && detail.comparison ? (
        <ComparisonTable comparison={detail.comparison} results={detail.results ?? undefined} />
      ) : detail.status === 'failed' ? (
        <p className="train-form-error">{detail.error ?? 'experiment failed'}</p>
      ) : (
        <Empty>No comparison was recorded for this experiment.</Empty>
      )}

      {repro.length ? (
        <>
          <SectionLabel>REPRODUCIBILITY</SectionLabel>
          <div className="kv-list">
            {repro.map(([k, v]) => (
              <KV key={k} k={k} v={String(v)} />
            ))}
          </div>
        </>
      ) : null}
    </Panel>
  );
}

/* ------------------------------------------------------------------ page */

export function ExperimentLab() {
  const wsSnapshot = useExperimentStore((s) => s.snapshot);
  const scenarios = useSimStore((s) => s.scenarios);
  const [rest, setRest] = useState<ExperimentSnapshot | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selected, setSelected] = useState<ExperimentDetail | null>(null);

  const refresh = useCallback(async () => {
    try {
      const snap = await api.experiments(40);
      setRest(snap);
      setLoadError(null);
    } catch (err) {
      setLoadError(err instanceof ApiError ? `${err.status} · ${err.message}` : String(err));
    }
  }, []);

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => void refresh(), 4000);
    return () => window.clearInterval(id);
  }, [refresh]);

  const openDetail = useCallback(async (id: string) => {
    try {
      setSelected(await api.experiment(id));
    } catch (err) {
      setLoadError(err instanceof ApiError ? `${err.status} · ${err.message}` : String(err));
    }
  }, []);

  // The WS snapshot is the freshest source for the running job; REST fills in history and
  // covers the no-job-this-session case (no WS frame ever arrives then).
  const job = wsSnapshot?.job ?? rest?.job ?? null;
  const running = (wsSnapshot?.running ?? rest?.running) ?? false;
  const history = rest?.history ?? [];

  return (
    <main className="training-lab">
      <div className="lab-legend">
        <div className="lab-legend-item">
          <SectionLabel>EXPERIMENT</SectionLabel>
          <p>
            Score Fixed-Time against the AI controllers on one scenario over a fixed seed set.
            Headless — it never touches the live dashboard simulation.
          </p>
        </div>
        <div className="lab-legend-item">
          <SectionLabel>HONEST COMPARISON</SectionLabel>
          <p>
            The baseline column is always shown, so a percentage is never displayed without the
            absolute values behind it. Every number is a measured episode aggregate.
          </p>
        </div>
        <div className="lab-legend-item">
          <SectionLabel>DIRECTION MATTERS</SectionLabel>
          <p>
            A metric counts as improved only when it moves the better way for that metric — lower
            waiting, higher throughput. Changes inside the 95% CI are flagged as noise.
          </p>
        </div>
      </div>

      {loadError ? (
        <p className="train-form-error">Cannot reach the experiment API: {loadError}</p>
      ) : null}

      <div className="lab-columns">
        <div className="lab-col">
          <StartExperimentForm scenarios={scenarios} disabled={running} onStarted={refresh} />
          <LiveExperiment job={job} />
        </div>
        <div className="lab-col">
          <ExperimentHistory rows={history} activeId={selected?.id ?? null} onOpen={openDetail} />
          {selected ? (
            <SelectedExperiment detail={selected} onClose={() => setSelected(null)} />
          ) : null}
        </div>
      </div>
    </main>
  );
}
