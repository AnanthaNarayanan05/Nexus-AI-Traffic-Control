/**
 * Training Lab - start headless single-agent training runs, watch one live, and browse
 * finished runs + the model registry.
 *
 * This view is deliberately separate from the live dashboard. Three different things
 * get confused otherwise, so the header spells them out:
 *   TRAINING        - gradient steps against a scenario, here.
 *   EVALUATION      - scoring a checkpoint vs fixed-time over held-out seeds (CLI, see docs).
 *   LIVE INFERENCE  - the running simulation on the dashboard (still UNTRAINED until
 *                     STEP 8 wires trained checkpoints in).
 *
 * Every number shown is a real measurement streamed from the backend training service
 * (MASTER_PROMPT sections 84, 98, 114). Nothing here is mocked.
 */

import { useCallback, useEffect, useState } from 'react';

import { ApiError, api } from '../lib/api';
import {
  AGENT_LABEL,
  AGENT_OBJECTIVE,
  AGENT_OWNER,
  NO_DATA,
  int,
  num,
  signed,
} from '../lib/format';
import type {
  AgentKey,
  ModelRecord,
  TrainingJob,
  TrainingRunSummary,
  TrainingSnapshot,
} from '../lib/types';
import { useTrainingStore } from '../store';
import { Badge, Empty, KV, Panel, SectionLabel, Stat } from '../components/common/Primitives';
import { Sparkline } from './Sparkline';

const AGENTS: AgentKey[] = ['a2c', 'dqn', 'ppo'];
const AGENT_COLOR: Record<AgentKey, string> = {
  a2c: 'var(--a2c)',
  dqn: 'var(--dqn)',
  ppo: 'var(--ppo)',
};

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

/* ------------------------------------------------------------------ start form */

function StartRunForm({ disabled, onStarted }: { disabled: boolean; onStarted: () => void }) {
  const [agent, setAgent] = useState<AgentKey>('a2c');
  const [episodes, setEpisodes] = useState(50);
  const [scenario, setScenario] = useState('');
  const [seed, setSeed] = useState('');
  const [checkpointEvery, setCheckpointEvery] = useState(25);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.startTraining({
        agent,
        episodes,
        scenario: scenario.trim() || null,
        seed: seed.trim() === '' ? null : Number(seed),
        checkpoint_every: checkpointEvery,
      });
      onStarted();
    } catch (err) {
      setError(err instanceof ApiError ? `${err.status} · ${err.message}` : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel title="START A RUN" accent="var(--accent)">
      <form className="train-form" onSubmit={submit}>
        <label>
          <span>Agent</span>
          <select value={agent} onChange={(e) => setAgent(e.target.value as AgentKey)}>
            {AGENTS.map((a) => (
              <option key={a} value={a}>
                {AGENT_LABEL[a]} — {AGENT_OBJECTIVE[a]}
              </option>
            ))}
          </select>
        </label>
        <p className="train-form-owner">
          Owner: {AGENT_OWNER[agent]}. Trains against{' '}
          {scenario.trim() || 'the agent default scenario'}.
        </p>

        <div className="train-form-grid">
          <label>
            <span>Episodes (1–1000)</span>
            <input
              type="number"
              min={1}
              max={1000}
              value={episodes}
              onChange={(e) => setEpisodes(Math.max(1, Math.min(1000, Number(e.target.value) || 1)))}
            />
          </label>
          <label>
            <span>Checkpoint every</span>
            <input
              type="number"
              min={1}
              max={1000}
              value={checkpointEvery}
              onChange={(e) =>
                setCheckpointEvery(Math.max(1, Math.min(1000, Number(e.target.value) || 1)))
              }
            />
          </label>
          <label>
            <span>Scenario (optional)</span>
            <input
              type="text"
              placeholder="agent default"
              value={scenario}
              onChange={(e) => setScenario(e.target.value)}
            />
          </label>
          <label>
            <span>Base seed (optional)</span>
            <input
              type="text"
              inputMode="numeric"
              placeholder="config seed"
              value={seed}
              onChange={(e) => setSeed(e.target.value.replace(/[^0-9-]/g, ''))}
            />
          </label>
        </div>

        <div className="train-form-actions">
          <button className="btn primary" type="submit" disabled={disabled || busy}>
            {busy ? 'Starting…' : '▶ Start training'}
          </button>
          {disabled ? (
            <span className="panel-sub">a run is already active — only one at a time</span>
          ) : null}
        </div>
        {error ? <p className="train-form-error">{error}</p> : null}
        <p className="panel-sub">
          Full episodes are 3600 s sim (~600 decisions). A 50-episode run takes a few minutes of
          wall time; progress streams below.
        </p>
      </form>
    </Panel>
  );
}

/* ------------------------------------------------------------------ live run */

function LiveRun({ job }: { job: TrainingJob | null }) {
  if (!job) {
    return (
      <Panel title="LIVE RUN" accent="var(--accent)">
        <Empty>No training run this session. Start one above to watch it here.</Empty>
      </Panel>
    );
  }

  const ep = job.last_episode;
  const pct = Math.round((job.progress || 0) * 100);
  const color = AGENT_COLOR[job.agent];

  return (
    <Panel
      title="LIVE RUN"
      accent={color}
      actions={<Badge tone={phaseTone(job.phase)}>{job.phase.toUpperCase()}</Badge>}
    >
      <div className="train-run-head">
        <span className="train-run-id" title={job.run_id}>
          {job.run_id}
        </span>
        <span className="panel-sub">
          {AGENT_LABEL[job.agent]} · {job.scenario} · seed {job.seed}
        </span>
      </div>

      <div className="train-progress">
        <div className="train-progress-track">
          <span
            className="train-progress-fill"
            style={{ width: `${pct}%`, background: color }}
          />
        </div>
        <span className="train-progress-label">
          episode {int(job.episode)} / {int(job.episodes_requested)} · {pct}%
        </span>
      </div>

      {job.error ? <p className="train-form-error">{job.error}</p> : null}

      <SectionLabel>EPISODE RETURNS</SectionLabel>
      <Sparkline values={job.returns} color={color} />

      {ep ? (
        <>
          <SectionLabel>LAST EPISODE ({int(ep.episode)})</SectionLabel>
          <div className="stat-grid">
            <Stat label="Return" value={num(ep.return, 2)} />
            <Stat label="Mean reward" value={num(ep.mean_reward, 3)} />
            <Stat label="Decisions" value={int(ep.decisions)} />
            <Stat label="Updates" value={int(ep.updates)} />
            <Stat
              label="Safety overrides"
              value={int(ep.safety_overrides)}
              title="Times the safety layer overrode the agent this episode (always authoritative, spec §113)"
            />
            <Stat label="Wall time" value={`${num(ep.wall_time_s, 1)}s`} />
          </div>

          {Object.keys(ep.losses).length > 0 ? (
            <>
              <SectionLabel>OPTIMISER</SectionLabel>
              <div className="kv-list">
                {Object.entries(ep.losses).map(([k, v]) => (
                  <KV key={k} k={k} v={num(v, 4)} />
                ))}
              </div>
            </>
          ) : null}
        </>
      ) : (
        <Empty>Waiting for the first episode to finish…</Empty>
      )}

      {job.phase === 'completed' ? (
        <div className="train-done">
          <KV k="Final model version" v={job.final_model_version ?? NO_DATA} />
          <KV k="Registered model id" v={job.registered_model_id ?? NO_DATA} />
          <KV k="Checkpoint" v={job.final_checkpoint ?? NO_DATA} />
          <p className="panel-sub">
            The checkpoint is saved and registered as <code>trained</code>. It is not in live
            inference yet — promote it to <code>active</code> (STEP 8) first.
          </p>
        </div>
      ) : null}
    </Panel>
  );
}

/* ------------------------------------------------------------------ runs table */

function RunsTable({ runs }: { runs: TrainingRunSummary[] }) {
  return (
    <Panel title="FINISHED RUNS" accent="var(--text-dim)" sub={`${runs.length}`}>
      {runs.length === 0 ? (
        <Empty>No run records on disk yet.</Empty>
      ) : (
        <div className="table-scroll">
          <table className="train-table">
            <thead>
              <tr>
                <th>Run</th>
                <th>Agent</th>
                <th>Scenario</th>
                <th>Seed</th>
                <th>Eps</th>
                <th>Return Δ</th>
                <th>Wall</th>
                <th>Version</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => {
                const delta =
                  r.first_return !== null && r.last_return !== null
                    ? r.last_return - r.first_return
                    : null;
                return (
                  <tr key={r.run_id}>
                    <td title={r.run_id}>{r.run_id}</td>
                    <td>{r.agent ? AGENT_LABEL[r.agent] : NO_DATA}</td>
                    <td>{r.scenario ?? NO_DATA}</td>
                    <td>{r.seed ?? NO_DATA}</td>
                    <td>{int(r.episodes)}</td>
                    <td
                      style={{
                        color:
                          delta === null
                            ? 'var(--text-faint)'
                            : delta >= 0
                              ? 'var(--green)'
                              : 'var(--red)',
                      }}
                    >
                      {delta === null ? NO_DATA : signed(delta, 1)}
                    </td>
                    <td>{r.wall_time_s !== null ? `${int(r.wall_time_s)}s` : NO_DATA}</td>
                    <td>{r.final_model_version ?? NO_DATA}</td>
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

/* ------------------------------------------------------------------ models table */

const MODEL_TONE: Record<string, 'good' | 'info' | 'neutral' | 'warn'> = {
  active: 'good',
  evaluated: 'info',
  trained: 'neutral',
  archived: 'warn',
};

function ModelsTable({ models }: { models: ModelRecord[] }) {
  return (
    <Panel title="MODEL REGISTRY" accent="var(--text-dim)" sub={`${models.length}`}>
      {models.length === 0 ? (
        <Empty>No models registered yet.</Empty>
      ) : (
        <div className="table-scroll">
          <table className="train-table">
            <thead>
              <tr>
                <th>Model id</th>
                <th>Agent</th>
                <th>Version</th>
                <th>Status</th>
                <th>Eps</th>
                <th>Eval scenario</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {models.map((m) => (
                <tr key={m.id}>
                  <td title={m.id}>{m.id}</td>
                  <td>{AGENT_LABEL[m.agent]}</td>
                  <td>{m.version}</td>
                  <td>
                    <Badge tone={MODEL_TONE[m.status] ?? 'neutral'}>{m.status.toUpperCase()}</Badge>
                  </td>
                  <td>{int(m.episodes)}</td>
                  <td>{m.eval_scenario ?? NO_DATA}</td>
                  <td>{shortTime(m.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

/* ------------------------------------------------------------------ page */

export function TrainingLab() {
  const wsSnapshot = useTrainingStore((s) => s.snapshot);
  const [rest, setRest] = useState<TrainingSnapshot | null>(null);
  const [models, setModels] = useState<ModelRecord[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [snap, ms] = await Promise.all([api.training(40), api.models()]);
      setRest(snap);
      setModels(ms.models);
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

  // The WS snapshot is the freshest source for the live job; REST fills in history +
  // the registry, and covers the case where no job has run this session (no WS frame).
  const job = wsSnapshot?.job ?? rest?.job ?? null;
  const running = (wsSnapshot?.running ?? rest?.running) ?? false;
  const history = rest?.history ?? [];

  return (
    <main className="training-lab">
      <div className="lab-legend">
        <div className="lab-legend-item">
          <SectionLabel>TRAINING</SectionLabel>
          <p>Gradient steps against a scenario. Runs here, one agent at a time.</p>
        </div>
        <div className="lab-legend-item">
          <SectionLabel>EVALUATION</SectionLabel>
          <p>
            Scoring a checkpoint vs fixed-time over held-out seeds. Run from the CLI
            (<code>scripts.training.evaluate</code>); results attach to the registry row.
          </p>
        </div>
        <div className="lab-legend-item">
          <SectionLabel>LIVE INFERENCE</SectionLabel>
          <p>
            The running simulation on the dashboard. Still <strong>UNTRAINED</strong> until trained
            checkpoints are promoted into it (STEP 8).
          </p>
        </div>
      </div>

      {loadError ? <p className="train-form-error">Cannot reach training API: {loadError}</p> : null}

      <div className="lab-columns">
        <div className="lab-col">
          <StartRunForm disabled={running} onStarted={refresh} />
          <LiveRun job={job} />
        </div>
        <div className="lab-col">
          <RunsTable runs={history} />
          <ModelsTable models={models} />
        </div>
      </div>
    </main>
  );
}
