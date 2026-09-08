/**
 * Replay Lab — scrub through a captured run of the live decision loop (MASTER_PROMPT
 * §18-19, §54-56; docs/replay.md).
 *
 * A replay is the ordered list of real `DecisionRecord`s the backend produced for one
 * run: at every AI decision, what each agent recommended, how the coordinator resolved
 * it, what the authoritative safety layer did, the reward decomposition and the metric
 * snapshot. Playback is entirely client-side over the timeline returned by
 * `GET /replay/{id}` — nothing here is synthesised (spec §84).
 *
 * The timeline is at the decision cadence (~6 s of sim), not the physics cadence, so
 * there is no vehicle-level playback — that is called out in the UI.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { ExportLinks } from '../components/common/ExportLinks';
import { Badge, Empty, KV, Panel, SectionLabel, Stat } from '../components/common/Primitives';
import { ApiError, api, exportUrls } from '../lib/api';
import { AGENT_LABEL, NO_DATA, clock, num, pct, titleise } from '../lib/format';
import type {
  AgentKey,
  EventMessage,
  ReplayDetail,
  ReplayFrame,
  ReplaySummary,
  SafetyAction,
} from '../lib/types';

const AGENTS: AgentKey[] = ['a2c', 'dqn'];
const SPEEDS = [0.5, 1, 2, 4] as const;
const BASE_STEP_MS = 850; // at 1× the player advances one decision every ~0.85 s

const SAFETY_TONE: Record<SafetyAction, 'good' | 'warn' | 'bad'> = {
  APPLIED: 'good',
  REWRITTEN_TRANSITION: 'warn',
  BLOCKED_HOLD: 'warn',
  FORCED_CHANGE: 'bad',
  EMERGENCY_TIMEOUT: 'bad',
};

function when(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? NO_DATA
    : d.toLocaleString(undefined, { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}

/* ------------------------------------------------------------------ replay list */

function ReplayList({
  rows,
  selectedId,
  onSelect,
  onDelete,
  busyId,
}: {
  rows: ReplaySummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  busyId: string | null;
}) {
  if (rows.length === 0) {
    return (
      <Empty>
        No replays captured yet. Run the simulation on the dashboard, then use “Capture current
        run”, or let an episode finish — a replay is saved automatically.
      </Empty>
    );
  }
  return (
    <div className="rpl-list">
      {rows.map((r) => (
        <div
          key={r.id}
          className={r.id === selectedId ? 'rpl-item active' : 'rpl-item'}
          onClick={() => onSelect(r.id)}
        >
          <div className="rpl-item-head">
            <span className="rpl-item-name">{r.scenario_name}</span>
            <Badge tone={r.episode_complete ? 'good' : 'neutral'}>
              {r.episode_complete ? 'FULL EPISODE' : 'PARTIAL'}
            </Badge>
          </div>
          <span className="rpl-item-meta">
            seed {r.seed} · {r.mode} · {r.decision_count} decisions · {clock(r.sim_duration_s)}
          </span>
          <span className="rpl-item-meta rpl-item-when">
            {when(r.created_at)}
            <button
              className="btn danger rpl-del"
              type="button"
              disabled={busyId === r.id}
              onClick={(e) => {
                e.stopPropagation();
                onDelete(r.id);
              }}
            >
              {busyId === r.id ? '…' : 'Delete'}
            </button>
          </span>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ transport */

function Transport({
  idx,
  total,
  playing,
  speed,
  frameT,
  durationS,
  onSeek,
  onPlayToggle,
  onSpeed,
}: {
  idx: number;
  total: number;
  playing: boolean;
  speed: number;
  frameT: number;
  durationS: number;
  onSeek: (i: number) => void;
  onPlayToggle: () => void;
  onSpeed: (s: number) => void;
}) {
  return (
    <div className="rpl-transport">
      <div className="rpl-buttons">
        <button className="btn" type="button" aria-label="First decision" onClick={() => onSeek(0)}>
          ⏮
        </button>
        <button
          className="btn"
          type="button"
          aria-label="Previous decision"
          onClick={() => onSeek(idx - 1)}
          disabled={idx <= 0}
        >
          ◀
        </button>
        <button className="btn primary" type="button" onClick={onPlayToggle}>
          {playing ? '⏸ Pause' : '▶ Play'}
        </button>
        <button
          className="btn"
          type="button"
          aria-label="Next decision"
          onClick={() => onSeek(idx + 1)}
          disabled={idx >= total - 1}
        >
          ▶
        </button>
        <button
          className="btn"
          type="button"
          aria-label="Last decision"
          onClick={() => onSeek(total - 1)}
        >
          ⏭
        </button>
        <label className="rpl-speed">
          <span>speed</span>
          <select value={speed} onChange={(e) => onSpeed(Number(e.target.value))}>
            {SPEEDS.map((s) => (
              <option key={s} value={s}>
                {s}×
              </option>
            ))}
          </select>
        </label>
      </div>

      <input
        className="rpl-scrub"
        type="range"
        min={0}
        max={Math.max(0, total - 1)}
        value={idx}
        aria-label="Timeline position"
        onChange={(e) => onSeek(Number(e.target.value))}
      />

      <div className="rpl-readout" data-testid="rpl-readout">
        decision <strong>{idx + 1}</strong> / {total} · t <strong>{clock(frameT)}</strong> of{' '}
        {clock(durationS)}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ frame panels */

function PipelineRow({ frame }: { frame: ReplayFrame }) {
  const { coordination, safety, applied_phase } = frame;
  const overrode = safety.action_taken !== 'APPLIED';
  const winnerIsAgent = AGENTS.includes(coordination.winner as AgentKey);
  return (
    <div className="rpl-pipeline">
      <div className="rpl-pipe-step">
        <SectionLabel>COORDINATOR</SectionLabel>
        <span className="rpl-pipe-main">{coordination.candidate_phase}</span>
        <span className="rpl-pipe-sub">
          <Badge tone={winnerIsAgent ? 'info' : 'neutral'}>
            {winnerIsAgent
              ? AGENT_LABEL[coordination.winner as AgentKey]
              : coordination.winner.toUpperCase()}
          </Badge>{' '}
          {titleise(coordination.basis)}
        </span>
      </div>
      <span className="rpl-pipe-arrow">→</span>
      <div className="rpl-pipe-step">
        <SectionLabel>SAFETY · AUTHORITATIVE</SectionLabel>
        <span className="rpl-pipe-main">
          {applied_phase} <Badge tone={SAFETY_TONE[safety.action_taken] ?? 'neutral'}>{safety.action_taken}</Badge>
        </span>
        <span className="rpl-pipe-sub" title={safety.reason}>
          {safety.reason || (overrode ? 'overridden' : 'passed through unchanged')}
        </span>
      </div>
    </div>
  );
}

function Recommendations({ frame }: { frame: ReplayFrame }) {
  return (
    <div className="rpl-recs">
      {AGENTS.map((a) => {
        const rec = frame.recommendations[a];
        if (!rec) {
          return (
            <div className="rpl-rec" key={a}>
              <span className="rpl-rec-agent">{AGENT_LABEL[a]}</span>
              <span className="rpl-rec-none">{NO_DATA} — no recommendation on this decision</span>
            </div>
          );
        }
        const won = frame.coordination.winner === a;
        return (
          <div className={won ? 'rpl-rec won' : 'rpl-rec'} key={a} style={{ borderLeftColor: `var(--${a})` }}>
            <span className="rpl-rec-agent" style={{ color: `var(--${a})` }}>
              {AGENT_LABEL[a]} → {rec.target_phase} {won ? <Badge tone="info">winner</Badge> : null}
            </span>
            <span className="rpl-rec-action">{rec.action_name}</span>
            <span className="rpl-rec-nums">
              score {num(rec.score, 2)} · conf {pct(rec.confidence)} · prio {pct(rec.priority)}
              {rec.value_estimate != null ? ` · V ${num(rec.value_estimate, 2)}` : ''}
            </span>
            <span className="rpl-rec-reason" title={rec.reason}>
              {rec.reason}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function Ladder({ frame }: { frame: ReplayFrame }) {
  const { ladder_trace, scores } = frame.coordination;
  if (!ladder_trace.length && !scores.length) return <Empty>No ladder trace on this decision.</Empty>;
  return (
    <div className="ladder">
      {ladder_trace.map((step, i) => (
        <div className="ladder-step" key={`${step.rung}-${i}`}>
          <span className="ladder-rung">{step.rung}</span>
          <span className={`ladder-outcome ${step.outcome}`}>{step.outcome}</span>
          <span>{step.detail}</span>
        </div>
      ))}
      {scores.length ? (
        <>
          <div className="divider" />
          {scores.map((s) => (
            <div className="ladder-step" key={s.phase} style={{ gridTemplateColumns: '92px 1fr' }}>
              <span className="ladder-rung">{s.phase}</span>
              <span>
                total {num(s.total, 3)} = congestion {num(s.congestion, 3)} + efficiency{' '}
                {num(s.efficiency, 3)} + throughput {num(s.throughput, 3)} + stability{' '}
                {num(s.stability, 3)} + consensus {num(s.consensus_bonus, 3)}
              </span>
            </div>
          ))}
        </>
      ) : null}
    </div>
  );
}

function RewardBreakdownBlock({ frame }: { frame: ReplayFrame }) {
  return (
    <div className="rpl-rewards">
      {AGENTS.map((a) => {
        const total = frame.rewards[a];
        const bd = frame.reward_breakdowns[a];
        return (
          <div className="rpl-reward" key={a}>
            <div className="rpl-reward-head">
              <span style={{ color: `var(--${a})` }}>{AGENT_LABEL[a]}</span>
              <span className={total != null && total < 0 ? 'rpl-neg' : 'rpl-pos'}>
                {total != null ? num(total, 3) : NO_DATA}
              </span>
            </div>
            {bd && bd.components.length ? (
              <div className="rpl-reward-parts">
                {bd.components.map((c) => (
                  <KV
                    key={c.name}
                    k={c.name.replace(/_/g, ' ')}
                    v={num(c.contribution, 3)}
                    tone={c.contribution < 0 ? 'var(--red)' : 'var(--green)'}
                  />
                ))}
              </div>
            ) : (
              <span className="rpl-rec-none">breakdown not recorded for this step</span>
            )}
          </div>
        );
      })}
    </div>
  );
}

function MetricsBlock({ frame }: { frame: ReplayFrame }) {
  const m = frame.metrics;
  return (
    <>
      <SectionLabel>TRAFFIC</SectionLabel>
      <div className="rpl-metric-grid">
        <Stat label="avg wait" value={num(m.traffic.avg_waiting_s, 1)} unit="s" />
        <Stat label="avg queue" value={num(m.traffic.avg_queue, 1)} />
        <Stat label="throughput" value={num(m.traffic.throughput_vph, 0)} unit="vph" />
        <Stat label="avg speed" value={num(m.traffic.avg_speed_mps, 1)} unit="m/s" />
        <Stat label="stops / veh" value={num(m.traffic.stops_per_veh, 2)} />
        <Stat label="idle time" value={num(m.traffic.idle_time_s, 1)} unit="s" />
      </div>
      <SectionLabel>ENVIRONMENTAL · ESTIMATED</SectionLabel>
      <div className="rpl-metric-grid">
        <Stat label="fuel / veh" value={num(m.environmental.fuel_l_per_veh, 3)} unit="L" />
        <Stat label="CO₂ / veh" value={num(m.environmental.co2_kg_per_veh, 3)} unit="kg" />
      </div>
      <SectionLabel>EMERGENCY</SectionLabel>
      <div className="rpl-metric-grid">
        <Stat label="emg wait" value={num(m.emergency.emergency_wait_s, 1)} unit="s" />
        <Stat label="emg delay" value={num(m.emergency.emergency_delay_s, 1)} unit="s" />
        <Stat label="emg cleared" value={num(m.emergency.emergency_cleared, 0)} />
      </div>
      <SectionLabel>SAFETY</SectionLabel>
      <div className="rpl-metric-grid">
        <Stat label="red-light" value={num(m.safety.red_light_violations, 0)} />
        <Stat label="other viol." value={num(m.safety.other_violations, 0)} />
        <Stat label="unsafe trans." value={num(m.safety.unsafe_transitions, 0)} />
      </div>
    </>
  );
}

function TrafficState({ frame }: { frame: ReplayFrame }) {
  const s = frame.state_summary;
  return (
    <div className="kv-list">
      <KV k="phase" v={`${s.phase} (served ${s.served_phase}, ${num(s.phase_elapsed_s, 0)}s)`} />
      <KV
        k="queues N/E/S/W"
        v={['N', 'E', 'S', 'W'].map((d) => num(s.queues?.[d] ?? 0, 0)).join(' / ')}
      />
      <KV k="vehicles / queued" v={`${num(s.total_vehicles, 0)} / ${num(s.total_queue, 0)}`} />
      <KV
        k="emergency"
        v={s.emergency_active ? `active on ${s.emergency_approach ?? '?'}` : 'none'}
        tone={s.emergency_active ? 'var(--a2c)' : undefined}
      />
      <KV k="violations (run total)" v={num(s.violations_total, 0)} />
    </div>
  );
}

function EventsUpTo({ events, t }: { events: EventMessage[]; t: number }) {
  const shown = events.filter((e) => e.t <= t + 1e-6).slice(-8).reverse();
  if (!shown.length) return <Empty>No events before this point.</Empty>;
  return (
    <div className="rpl-events">
      {shown.map((e) => (
        <div className="rpl-event" key={e.id}>
          <span className="rpl-event-t">{clock(e.t)}</span>
          <Badge tone={e.severity === 'critical' ? 'bad' : e.severity === 'warning' ? 'warn' : 'neutral'}>
            {e.category}
          </Badge>
          <span className="rpl-event-desc">{e.description}</span>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ player */

function ReplayPlayer({ detail }: { detail: ReplayDetail }) {
  const total = detail.timeline.length;
  const [idx, setIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const timer = useRef<number | null>(null);

  // reset the head whenever a different replay is opened
  useEffect(() => {
    setIdx(0);
    setPlaying(false);
  }, [detail.id]);

  const seek = useCallback(
    (i: number) => setIdx(Math.max(0, Math.min(total - 1, i))),
    [total],
  );

  useEffect(() => {
    if (!playing) {
      if (timer.current) window.clearInterval(timer.current);
      timer.current = null;
      return;
    }
    timer.current = window.setInterval(() => {
      setIdx((cur) => {
        if (cur >= total - 1) {
          setPlaying(false);
          return cur;
        }
        return cur + 1;
      });
    }, BASE_STEP_MS / speed);
    return () => {
      if (timer.current) window.clearInterval(timer.current);
    };
  }, [playing, speed, total]);

  const frame = detail.timeline[idx];
  if (!frame) return <Empty>This replay has no decision frames.</Empty>;

  return (
    <>
      <Panel
        title="PLAYER"
        accent="var(--accent)"
        sub={detail.label}
        actions={
          <Badge tone={detail.episode_complete ? 'good' : 'neutral'}>
            {detail.episode_complete ? 'FULL EPISODE' : 'PARTIAL RUN'}
          </Badge>
        }
      >
        <Transport
          idx={idx}
          total={total}
          playing={playing}
          speed={speed}
          frameT={frame.t}
          durationS={detail.sim_duration_s}
          onSeek={(i) => {
            setPlaying(false);
            seek(i);
          }}
          onPlayToggle={() => setPlaying((p) => !p)}
          onSpeed={setSpeed}
        />
        <p className="panel-sub rpl-note">
          Decision-cadence replay: the pipeline state at each AI decision (~
          {num(detail.timeline[1] ? detail.timeline[1].t - detail.timeline[0].t : 6, 0)} s apart).
          Vehicle-level playback is not captured.
        </p>
        <PipelineRow frame={frame} />
      </Panel>

      <Panel title="AGENT RECOMMENDATIONS" accent="var(--a2c)">
        <Recommendations frame={frame} />
      </Panel>

      <Panel title="COORDINATION LADDER" accent="var(--accent)">
        <Ladder frame={frame} />
      </Panel>

      <Panel title="REWARD DECOMPOSITION" accent="var(--dqn)">
        <RewardBreakdownBlock frame={frame} />
        <p className="panel-sub">
          The reward for a decision is realised one interval later (on-policy ordering), so the
          value shown is what this step ultimately earned.
        </p>
      </Panel>

      <Panel title="METRICS AT THIS DECISION" accent="var(--text-dim)">
        <MetricsBlock frame={frame} />
      </Panel>

      <Panel title="TRAFFIC STATE" accent="var(--text-dim)">
        <TrafficState frame={frame} />
      </Panel>

      <Panel title="EVENTS UP TO THIS POINT" accent="var(--text-dim)">
        <EventsUpTo events={detail.events} t={frame.t} />
      </Panel>
    </>
  );
}

/* ------------------------------------------------------------------ page */

export function ReplayLab() {
  const [rows, setRows] = useState<ReplaySummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ReplayDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [capturing, setCapturing] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const r = await api.replays();
      setRows(r.replays);
      setError(null);
      return r.replays;
    } catch (err) {
      setError(err instanceof ApiError ? `${err.status} · ${err.message}` : String(err));
      return [];
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // auto-open the newest replay once the list is known
  useEffect(() => {
    if (selectedId === null && rows.length) setSelectedId(rows[0].id);
  }, [rows, selectedId]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    api
      .replay(selectedId)
      .then((d) => {
        if (!cancelled) setDetail(d);
      })
      .catch((err) => {
        if (!cancelled) {
          setDetail(null);
          setError(err instanceof ApiError ? `${err.status} · ${err.message}` : String(err));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  const capture = useCallback(async () => {
    setCapturing(true);
    setError(null);
    setNotice(null);
    try {
      const saved = await api.captureReplay();
      setNotice(`Captured “${saved.label}” — ${saved.decision_count} decisions.`);
      await refresh();
      setSelectedId(saved.id);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.status === 409
            ? 'Nothing to capture yet — run the simulation on the dashboard for a few decisions first.'
            : `${err.status} · ${err.message}`
          : String(err),
      );
    } finally {
      setCapturing(false);
    }
  }, [refresh]);

  const remove = useCallback(
    async (id: string) => {
      setBusyId(id);
      setError(null);
      try {
        await api.deleteReplay(id);
        const left = await refresh();
        if (selectedId === id) setSelectedId(left[0]?.id ?? null);
      } catch (err) {
        setError(err instanceof ApiError ? `${err.status} · ${err.message}` : String(err));
      } finally {
        setBusyId(null);
      }
    },
    [refresh, selectedId],
  );

  const selectedSummary = useMemo(
    () => rows.find((r) => r.id === selectedId) ?? null,
    [rows, selectedId],
  );

  return (
    <main className="training-lab">
      <div className="lab-legend">
        <div className="lab-legend-item">
          <SectionLabel>REPLAY</SectionLabel>
          <p>
            Every captured run of the live decision loop, frame by frame. Play, pause, step or
            scrub to any decision and see exactly what the agents, the coordinator and the safety
            layer did.
          </p>
        </div>
        <div className="lab-legend-item">
          <SectionLabel>REAL FRAMES ONLY</SectionLabel>
          <p>
            A replay is saved when an episode finishes, when a run is reset, or on an explicit
            capture. Nothing is reconstructed — each frame is the record the backend wrote at that
            decision.
          </p>
        </div>
        <div className="lab-legend-item">
          <SectionLabel>SAFETY IS AUTHORITATIVE</SectionLabel>
          <p>
            Each frame shows the coordinated choice and then what the safety layer applied. Where
            they differ, the safety layer won — no agent recommendation can bypass it.
          </p>
        </div>
      </div>

      {error ? <p className="train-form-error">{error}</p> : null}
      {notice ? <p className="scn-notice">{notice}</p> : null}

      <div className="lab-columns">
        <div className="lab-col">
          <Panel
            title="CAPTURED REPLAYS"
            accent="var(--accent)"
            sub={`${rows.length}`}
            actions={
              <div className="rpl-list-actions">
                <button className="btn" type="button" onClick={() => void refresh()}>
                  Refresh
                </button>
                <button
                  className="btn primary"
                  type="button"
                  disabled={capturing}
                  onClick={() => void capture()}
                >
                  {capturing ? 'Capturing…' : 'Capture current run'}
                </button>
              </div>
            }
          >
            <ReplayList
              rows={rows}
              selectedId={selectedId}
              onSelect={setSelectedId}
              onDelete={(id) => void remove(id)}
              busyId={busyId}
            />
          </Panel>
        </div>

        <div className="lab-col">
          {selectedSummary ? (
            <Panel
              title="REPLAY"
              accent="var(--text-dim)"
              actions={
                <ExportLinks
                  url={(f) => exportUrls.replay(selectedSummary.id, f)}
                  title="Download this replay — CSV is one row per decision, JSON is the full timeline"
                />
              }
            >
              <div className="kv-list">
                <KV k="scenario" v={`${selectedSummary.scenario_name} (${selectedSummary.scenario_id})`} />
                <KV k="seed" v={selectedSummary.seed} />
                <KV k="control mode" v={selectedSummary.mode} />
                <KV
                  k="agent weights"
                  v={AGENTS.map((a) => `${AGENT_LABEL[a]} ${selectedSummary.model_modes[a] ?? '—'}`).join(' · ')}
                />
                <KV k="config digest" v={selectedSummary.config_digest || NO_DATA} />
                <KV k="captured" v={when(selectedSummary.created_at)} />
              </div>
            </Panel>
          ) : null}

          {detail ? (
            <ReplayPlayer detail={detail} />
          ) : selectedId ? (
            <Panel title="PLAYER" accent="var(--accent)">
              <Empty>Loading replay…</Empty>
            </Panel>
          ) : (
            <Panel title="PLAYER" accent="var(--accent)">
              <Empty>Select a replay on the left to play it back.</Empty>
            </Panel>
          )}
        </div>
      </div>
    </main>
  );
}
