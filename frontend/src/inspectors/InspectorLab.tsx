/**
 * Inspectors — pause-and-inspect views over the live decision loop (MASTER_PROMPT §19,
 * §41-47).
 *
 * Five read-only inspectors, all fed from data the backend already produces:
 *   - Coordination "brain": why the current decision won — the priority ladder, the
 *     phase scores, each agent's recommendation, and the authoritative safety verdict.
 *   - Signal: the phase state machine — timers, transition, allowed next phases, and the
 *     authoritative per-approach aspect.
 *   - Emergency vehicle: the active emergency, and A2C's priority response.
 *   - Vehicle: every vehicle in the network with its full per-vehicle state (fetched on
 *     demand from `GET /simulation/state`).
 *   - DQN experience replay (§17): stored transitions — state → action → reward → next
 *     state → done — sampled from the buffer.
 *
 * Nothing here is synthesised (§84). Where a value has not been produced it shows as
 * unavailable. Pause the simulation to freeze the frame under inspection.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { Badge, Empty, KV, Panel, SectionLabel, Stat } from '../components/common/Primitives';
import { useAgentInspector } from '../hooks/useAgentInspector';
import { activateOnKey } from '../lib/a11y';
import { api } from '../lib/api';
import { AGENT_LABEL, NO_DATA, int, num, pct, titleise } from '../lib/format';
import type {
  AgentKey,
  AgentRecommendation,
  Approach,
  DqnReplayTransition,
  FullSimulationState,
  Phase,
  SafetyAction,
  SignalColor,
  VehicleDetail,
} from '../lib/types';
import { useAgentStore, useSimStore } from '../store';

const AGENTS: AgentKey[] = ['a2c', 'dqn'];
const APPROACHES: Approach[] = ['N', 'E', 'S', 'W'];

const SAFETY_TONE: Record<SafetyAction, 'good' | 'warn' | 'bad'> = {
  APPLIED: 'good',
  REWRITTEN_TRANSITION: 'warn',
  BLOCKED_HOLD: 'warn',
  FORCED_CHANGE: 'bad',
  EMERGENCY_TIMEOUT: 'bad',
};

const COLOR_TONE: Record<SignalColor, 'good' | 'warn' | 'bad'> = {
  GREEN: 'good',
  YELLOW: 'warn',
  RED: 'bad',
};

/** One-line gloss for each priority-ladder rung (spec §21). */
const RUNG_GLOSS: Record<string, string> = {
  safety: 'Rule check on the candidate phase before anything else is considered.',
  emergency: 'Emergency-vehicle priority (A2C) — can override the score below.',
  valid_phase: 'Filter to the phases legally reachable from the current one.',
  weighted_score: 'Deterministic phase scoring: congestion, efficiency, throughput, stability, consensus.',
  stability: 'Penalty for switching phase without a large enough gain.',
};

type InspTab = 'coordination' | 'signal' | 'emergency' | 'vehicles' | 'dqn-replay';

const TABS: { id: InspTab; label: string }[] = [
  { id: 'coordination', label: 'Coordination brain' },
  { id: 'signal', label: 'Signal' },
  { id: 'emergency', label: 'Emergency vehicle' },
  { id: 'vehicles', label: 'Vehicles' },
  { id: 'dqn-replay', label: 'DQN experience replay' },
];

/* ------------------------------------------------------------------ shared */

function LiveTag() {
  const running = useSimStore((s) => s.status?.running);
  const connection = useSimStore((s) => s.connection);
  if (connection !== 'open') return <Badge tone="bad">disconnected</Badge>;
  return running ? (
    <Badge tone="info">live</Badge>
  ) : (
    <Badge tone="good" title="The simulation is paused — this frame is frozen for inspection.">
      paused · inspecting
    </Badge>
  );
}

function phaseServes(phase: Phase | undefined, approach: Approach | null | undefined): boolean {
  if (!phase || !approach) return false;
  if (phase === approach) return true;
  if (phase === 'NS') return approach === 'N' || approach === 'S';
  if (phase === 'EW') return approach === 'E' || approach === 'W';
  return false;
}

/* ------------------------------------------------------------------ coordination brain */

function RecommendationCard({ rec, winner }: { rec: AgentRecommendation; winner: string }) {
  const won = winner === rec.agent;
  const rel = Object.entries(rec.relevant_state ?? {});
  return (
    <div className={won ? 'insp-rec won' : 'insp-rec'} style={{ borderLeftColor: `var(--${rec.agent})` }}>
      <div className="insp-rec-head">
        <span style={{ color: `var(--${rec.agent})` }}>
          {AGENT_LABEL[rec.agent]} → {rec.target_phase}
        </span>
        {won ? <Badge tone="info">winner</Badge> : null}
      </div>
      <span className="insp-rec-action">{rec.action_name}</span>
      <span className="insp-rec-nums">
        score {num(rec.score, 3)} · conf {pct(rec.confidence)} · prio {pct(rec.priority)}
        {rec.value_estimate != null ? ` · V ${num(rec.value_estimate, 3)}` : ''}
      </span>
      <span className="insp-rec-reason">{rec.reason}</span>
      {rel.length ? (
        <div className="insp-kv-grid">
          {rel.map(([k, v]) => (
            <KV key={k} k={k.replace(/_/g, ' ')} v={num(v, 3)} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function CoordinationBrain() {
  const update = useAgentStore((s) => s.coordination);
  const mode = useSimStore((s) => s.status?.mode);

  if (!update) {
    return (
      <Panel title="COORDINATION BRAIN" accent="var(--accent)" actions={<LiveTag />}>
        <Empty>
          {mode && mode !== 'AI'
            ? `Control mode is ${mode}. Coordination reasoning is produced only in AI mode.`
            : 'No decision has been produced yet. Start the simulation in AI mode.'}
        </Empty>
      </Panel>
    );
  }

  const { coordination, safety, applied_phase, decision_id } = update;
  const byAgent = new Map<AgentKey, AgentRecommendation>();
  coordination.recommendations.forEach((r) => byAgent.set(r.agent, r));
  const winnerIsAgent = AGENTS.includes(coordination.winner as AgentKey);
  const overrode = safety.action_taken !== 'APPLIED';

  return (
    <>
      <Panel
        title="COORDINATION BRAIN"
        accent="var(--accent)"
        sub={`#${decision_id.slice(0, 8)}`}
        actions={<LiveTag />}
      >
        <div className="insp-pipeline">
          <div className="insp-pipe-step">
            <SectionLabel>COORDINATOR</SectionLabel>
            <span className="insp-pipe-main">{coordination.candidate_phase}</span>
            <span className="insp-pipe-sub">
              <Badge tone={winnerIsAgent ? 'info' : 'neutral'}>
                {winnerIsAgent
                  ? AGENT_LABEL[coordination.winner as AgentKey]
                  : coordination.winner.toUpperCase()}
              </Badge>{' '}
              {titleise(coordination.basis)}
            </span>
          </div>
          <span className="insp-pipe-arrow">→</span>
          <div className="insp-pipe-step">
            <SectionLabel>SAFETY · AUTHORITATIVE</SectionLabel>
            <span className="insp-pipe-main">
              {applied_phase}{' '}
              <Badge tone={SAFETY_TONE[safety.action_taken] ?? 'neutral'}>{safety.action_taken}</Badge>
            </span>
            <span className="insp-pipe-sub">{safety.reason || 'passed through unchanged'}</span>
          </div>
        </div>
        {overrode ? (
          <div className="banner warn">
            The safety layer changed the coordinated choice
            {applied_phase !== coordination.candidate_phase
              ? ` (${coordination.candidate_phase} → ${applied_phase})`
              : ` (${titleise(safety.action_taken)})`}
            . No agent recommendation can bypass this layer.
          </div>
        ) : null}
      </Panel>

      <Panel title="PRIORITY LADDER — why this decision won" accent="var(--accent)">
        {coordination.ladder_trace.length === 0 ? (
          <Empty>No ladder trace on this decision.</Empty>
        ) : (
          <div className="insp-ladder">
            {coordination.ladder_trace.map((step, i) => (
              <div className="insp-ladder-step" key={`${step.rung}-${i}`}>
                <div className="insp-ladder-top">
                  <span className="ladder-rung">{step.rung}</span>
                  <span className={`ladder-outcome ${step.outcome}`}>{step.outcome}</span>
                  <span className="insp-ladder-detail">{step.detail}</span>
                </div>
                {RUNG_GLOSS[step.rung] ? (
                  <span className="insp-ladder-gloss">{RUNG_GLOSS[step.rung]}</span>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </Panel>

      {coordination.scores.length ? (
        <Panel title="PHASE SCORES" accent="var(--text-dim)">
          <div className="insp-score-table" role="table">
            <div className="insp-score-row insp-score-head" role="row">
              <span>phase</span>
              <span>congestion</span>
              <span>efficiency</span>
              <span>throughput</span>
              <span>stability</span>
              <span>consensus</span>
              <span>total</span>
            </div>
            {coordination.scores.map((s) => (
              <div
                className={
                  s.phase === coordination.candidate_phase
                    ? 'insp-score-row insp-score-win'
                    : 'insp-score-row'
                }
                role="row"
                key={s.phase}
              >
                <span>{s.phase}</span>
                <span>{num(s.congestion, 3)}</span>
                <span>{num(s.efficiency, 3)}</span>
                <span>{num(s.throughput, 3)}</span>
                <span>{num(s.stability, 3)}</span>
                <span>{num(s.consensus_bonus, 3)}</span>
                <span>
                  <strong>{num(s.total, 3)}</strong>
                </span>
              </div>
            ))}
          </div>
        </Panel>
      ) : null}

      <Panel title="AGENT RECOMMENDATIONS" accent="var(--a2c)">
        <div className="insp-recs">
          {AGENTS.map((a) => {
            const rec = byAgent.get(a);
            return rec ? (
              <RecommendationCard key={a} rec={rec} winner={coordination.winner} />
            ) : (
              <div className="insp-rec" key={a}>
                <span className="insp-rec-reason">
                  {AGENT_LABEL[a]} {NO_DATA} — no recommendation reached the coordinator.
                </span>
              </div>
            );
          })}
        </div>
      </Panel>

      <Panel title="SAFETY VERDICT" accent={overrode ? 'var(--yellow)' : 'var(--green)'}>
        <div className="kv-list">
          <KV k="approved" v={safety.approved ? 'yes' : 'no'} tone={safety.approved ? undefined : 'var(--red)'} />
          <KV k="action taken" v={safety.action_taken} />
          <KV k="candidate phase" v={safety.original} />
          <KV k="applied phase" v={applied_phase} />
          <KV
            k="command"
            v={[
              `target ${safety.command.target_phase}`,
              safety.command.request_extend_s != null ? `extend ${safety.command.request_extend_s}s` : null,
              safety.command.request_reduce ? 'reduce' : null,
              safety.command.force_transition ? 'force' : null,
              `src ${safety.command.source}`,
            ]
              .filter(Boolean)
              .join(' · ')}
          />
          <KV
            k="violated rules"
            v={safety.violated_rules.length ? safety.violated_rules.join(', ') : 'none'}
            tone={safety.violated_rules.length ? 'var(--yellow)' : undefined}
          />
          <KV k="reason" v={safety.reason || NO_DATA} />
        </div>
        <p className="panel-sub">
          The safety layer runs on every decision and is authoritative — the agents recommend, it
          decides what the signal actually does (§113).
        </p>
      </Panel>
    </>
  );
}

/* ------------------------------------------------------------------ signal inspector */

function SignalInspector() {
  const signal = useSimStore((s) => s.state?.signal);

  if (!signal) {
    return (
      <Panel title="SIGNAL" accent="var(--accent)" actions={<LiveTag />}>
        <Empty>No signal state yet. Start the simulation.</Empty>
      </Panel>
    );
  }

  const minSatisfied = signal.phase_remaining_min_s <= 1e-6;
  const tr = signal.transition;

  return (
    <>
      <Panel title="SIGNAL STATE MACHINE" accent="var(--accent)" actions={<LiveTag />}>
        <div className="stat-grid">
          <Stat label="current phase" value={signal.current_phase} />
          <Stat label="served phase" value={signal.served_phase} note="last non-transition green" />
          <Stat label="phase elapsed" value={num(signal.phase_elapsed_s, 1)} unit="s" />
        </div>
        <div className="insp-timers">
          <div className="insp-timer">
            <SectionLabel>MIN GREEN</SectionLabel>
            {minSatisfied ? (
              <Badge tone="good">satisfied — a phase change is allowed</Badge>
            ) : (
              <>
                <span className="insp-timer-val">{num(signal.phase_remaining_min_s, 1)} s remaining</span>
                <span className="insp-bar">
                  <span
                    className="insp-bar-fill"
                    style={{
                      width: `${Math.min(
                        100,
                        (signal.phase_elapsed_s /
                          Math.max(signal.phase_elapsed_s + signal.phase_remaining_min_s, 0.001)) *
                          100,
                      )}%`,
                      background: 'var(--yellow)',
                    }}
                  />
                </span>
              </>
            )}
          </div>
          <div className="insp-timer">
            <SectionLabel>MAX GREEN</SectionLabel>
            <span className="insp-timer-val">{num(signal.phase_remaining_max_s, 1)} s until a change is forced</span>
            <span className="insp-bar">
              <span
                className="insp-bar-fill"
                style={{
                  width: `${Math.min(
                    100,
                    (signal.phase_elapsed_s /
                      Math.max(signal.phase_elapsed_s + signal.phase_remaining_max_s, 0.001)) *
                      100,
                  )}%`,
                  background: 'var(--accent)',
                }}
              />
            </span>
          </div>
        </div>
        <div className="kv-list">
          <KV
            k="allowed next"
            v={
              signal.allowed_next.length
                ? signal.allowed_next.map((p) => (
                    <Badge key={p} tone="neutral">
                      {p}
                    </Badge>
                  ))
                : 'none'
            }
          />
          <KV k="last action" v={signal.last_action ?? NO_DATA} />
        </div>
      </Panel>

      {tr ? (
        <Panel title="TRANSITION IN PROGRESS" accent="var(--yellow)">
          <div className="kv-list">
            <KV k="kind" v={tr.kind} />
            <KV k="from → to" v={`${tr.from_phase} → ${tr.to_phase}`} />
            <KV k="elapsed" v={`${num(tr.elapsed_s, 1)} / ${num(tr.total_s, 1)} s`} />
          </div>
          <span className="insp-bar">
            <span
              className="insp-bar-fill"
              style={{
                width: `${Math.min(100, (tr.elapsed_s / Math.max(tr.total_s, 0.001)) * 100)}%`,
                background: 'var(--yellow)',
              }}
            />
          </span>
        </Panel>
      ) : null}

      <Panel title="PER-APPROACH ASPECT" accent="var(--text-dim)">
        <div className="insp-aspect-grid">
          {APPROACHES.map((a) => {
            const c = signal.approach_colors?.[a];
            return (
              <div className="insp-aspect" key={a}>
                <span className="insp-aspect-dir">{a}</span>
                {c ? <Badge tone={COLOR_TONE[c]}>{c}</Badge> : <span>{NO_DATA}</span>}
              </div>
            );
          })}
        </div>
        <p className="panel-sub">
          Authoritative aspect computed by the SignalController and sent on the wire — the renderer
          shows exactly this, it is not re-derived from the phase (§114).
        </p>
      </Panel>
    </>
  );
}

/* ------------------------------------------------------------------ emergency inspector */

function EmergencyInspector() {
  const emg = useSimStore((s) => s.state?.emergency);
  const signal = useSimStore((s) => s.state?.signal);
  const update = useAgentStore((s) => s.coordination);
  const a2cRec = useAgentStore((s) => s.agents.a2c?.recommendation);

  const priorityActive = !!update?.coordination.ladder_trace.some(
    (s) => s.rung === 'emergency' && s.outcome === 'override',
  );

  if (!emg?.active) {
    return (
      <Panel title="EMERGENCY VEHICLE" accent="var(--a2c)" actions={<LiveTag />}>
        <Empty>
          No emergency vehicle is in the network. Inject an ambulance from the command bar to see
          A2C&apos;s priority response.
        </Empty>
        <div className="stat-grid">
          <Stat label="cleared this episode" value={int(emg?.cleared_this_episode)} />
        </div>
      </Panel>
    );
  }

  const serving = phaseServes(signal?.current_phase, emg.approach);

  return (
    <>
      <Panel title="EMERGENCY VEHICLE" accent="var(--a2c)" actions={<LiveTag />}>
        <div className="stat-grid">
          <Stat label="vehicle" value={emg.vehicle_id ?? NO_DATA} />
          <Stat label="type" value={emg.type ? emg.type.replace(/_/g, ' ') : NO_DATA} />
          <Stat label="approach" value={emg.approach ?? NO_DATA} />
          <Stat label="distance" value={num(emg.distance_m, 1)} unit="m" />
          <Stat label="speed" value={num(emg.speed_mps, 1)} unit="m/s" />
          <Stat label="ETA to stop line" value={num(emg.eta_s, 1)} unit="s" />
          <Stat label="cleared this episode" value={int(emg.cleared_this_episode)} />
        </div>
      </Panel>

      <Panel title="A2C PRIORITY RESPONSE" accent="var(--a2c)">
        <div className="kv-list">
          <KV
            k="priority override"
            v={priorityActive ? <Badge tone="good">ACTIVE — coordinator override</Badge> : <Badge tone="warn">not overriding</Badge>}
          />
          <KV k="A2C action" v={a2cRec?.action_name ?? NO_DATA} />
          <KV k="A2C target phase" v={a2cRec?.target_phase ?? NO_DATA} />
          <KV k="A2C reason" v={a2cRec?.reason ?? NO_DATA} />
        </div>
      </Panel>

      <Panel title="SIGNAL RESPONSE" accent={serving ? 'var(--green)' : 'var(--yellow)'}>
        <div className="kv-list">
          <KV k="current phase" v={signal?.current_phase ?? NO_DATA} />
          <KV
            k="serving the emergency approach?"
            v={serving ? <Badge tone="good">yes — {emg.approach} has green</Badge> : <Badge tone="warn">not yet — {emg.approach} is held</Badge>}
          />
        </div>
        <p className="panel-sub">
          The safety layer still bounds the emergency response — minimum green and safe transitions
          are enforced even under priority (§113).
        </p>
      </Panel>
    </>
  );
}

/* ------------------------------------------------------------------ vehicle inspector */

const VEH_POLL_MS = 2000;

function VehicleInspector() {
  const [snap, setSnap] = useState<FullSimulationState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [approach, setApproach] = useState<'ALL' | Approach>('ALL');
  const [emergencyOnly, setEmergencyOnly] = useState(false);
  const [violatorOnly, setViolatorOnly] = useState(false);
  const inflight = useRef(false);

  const poll = useCallback(async () => {
    if (inflight.current) return;
    inflight.current = true;
    try {
      const s = await api.simulationState();
      setSnap(s);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      inflight.current = false;
    }
  }, []);

  useEffect(() => {
    void poll();
    const timer = window.setInterval(() => void poll(), VEH_POLL_MS);
    return () => window.clearInterval(timer);
  }, [poll]);

  const vehicles = useMemo(() => snap?.vehicles ?? [], [snap]);
  const filtered = useMemo(
    () =>
      vehicles.filter(
        (v) =>
          (approach === 'ALL' || v.approach === approach) &&
          (!emergencyOnly || v.is_emergency) &&
          (!violatorOnly || v.is_violator),
      ),
    [vehicles, approach, emergencyOnly, violatorOnly],
  );
  const selected = selectedId ? vehicles.find((v) => v.id === selectedId) ?? null : null;

  return (
    <>
      <Panel
        title="VEHICLES IN THE NETWORK"
        accent="var(--accent)"
        sub={`${vehicles.length}`}
        actions={<LiveTag />}
      >
        <div className="insp-veh-filters">
          <label>
            approach
            <select value={approach} onChange={(e) => setApproach(e.target.value as 'ALL' | Approach)}>
              <option value="ALL">all</option>
              {APPROACHES.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
          </label>
          <label>
            <input type="checkbox" checked={emergencyOnly} onChange={(e) => setEmergencyOnly(e.target.checked)} />
            emergency only
          </label>
          <label>
            <input type="checkbox" checked={violatorOnly} onChange={(e) => setViolatorOnly(e.target.checked)} />
            violators only
          </label>
        </div>

        {error ? <p className="train-form-error">Snapshot unavailable: {error}</p> : null}

        {filtered.length === 0 ? (
          <Empty>No vehicles match the filter.</Empty>
        ) : (
          <div className="insp-veh-list" role="listbox" aria-label="Vehicles in the network">
            <div className="insp-veh-row insp-veh-head" aria-hidden="true">
              <span>id</span>
              <span>type</span>
              <span>approach·lane</span>
              <span>speed</span>
              <span>wait</span>
              <span>state</span>
            </div>
            {filtered.slice(0, 120).map((v) => (
              <div
                className={v.id === selectedId ? 'insp-veh-row insp-veh-sel' : 'insp-veh-row'}
                role="option"
                aria-selected={v.id === selectedId}
                tabIndex={0}
                key={v.id}
                onClick={() => setSelectedId(v.id)}
                onKeyDown={activateOnKey(() => setSelectedId(v.id))}
              >
                <span>
                  {v.is_emergency ? '🚨 ' : ''}
                  {v.is_violator ? '⚠ ' : ''}
                  {v.id}
                </span>
                <span>{v.type.replace(/_/g, ' ')}</span>
                <span>
                  {v.approach}·{v.lane}
                </span>
                <span>{num(v.speed_mps, 1)} m/s</span>
                <span>{num(v.wait_s, 1)} s</span>
                <span>{v.state}</span>
              </div>
            ))}
            {filtered.length > 120 ? (
              <p className="panel-sub">Showing the first 120 of {filtered.length}. Narrow the filter to see more.</p>
            ) : null}
          </div>
        )}
        <p className="panel-sub">
          Snapshot polled every {VEH_POLL_MS / 1000}s from <code>GET /simulation/state</code>. Pause
          the simulation to inspect a frozen frame.
        </p>
      </Panel>

      {selectedId ? (
        <Panel title={`VEHICLE ${selectedId}`} accent="var(--text-dim)">
          {selected ? (
            <VehicleDetailBlock v={selected} />
          ) : (
            <Empty>Vehicle {selectedId} has left the network.</Empty>
          )}
        </Panel>
      ) : null}
    </>
  );
}

function VehicleDetailBlock({ v }: { v: VehicleDetail }) {
  return (
    <>
      <div className="insp-badges">
        {v.is_emergency ? <Badge tone="bad">emergency</Badge> : null}
        {v.is_violator ? <Badge tone="warn">violator</Badge> : null}
        <Badge tone="neutral">{v.state}</Badge>
      </div>
      <div className="stat-grid">
        <Stat label="type" value={v.type.replace(/_/g, ' ')} />
        <Stat label="approach" value={v.approach} />
        <Stat label="lane" value={int(v.lane)} />
        <Stat label="movement" value={v.movement} />
        <Stat label="speed" value={num(v.speed_mps, 2)} unit="m/s" />
        <Stat label="accel" value={num(v.accel_mps2, 2)} unit="m/s²" />
        <Stat label="waiting" value={num(v.wait_s, 1)} unit="s" />
        <Stat label="stops" value={int(v.stops)} />
        <Stat label="fuel used" value={num(v.fuel_l, 3)} unit="L" note="ESTIMATED" />
        <Stat label="CO₂" value={num(v.co2_kg, 3)} unit="kg" note="ESTIMATED" />
        <Stat label="position" value={`${num(v.x, 1)}, ${num(v.y, 1)}`} />
        <Stat label="heading" value={num(v.heading, 2)} unit="rad" />
      </div>
    </>
  );
}

/* ------------------------------------------------------------------ dqn replay inspector */

function transitionRows(sample: unknown): DqnReplayTransition[] {
  return Array.isArray(sample) ? (sample as DqnReplayTransition[]) : [];
}

function DqnReplayInspector() {
  const { data, error } = useAgentInspector('dqn', 2000);
  const extra = (data?.extra ?? {}) as Record<string, unknown>;
  const replaySize = typeof extra.replay_size === 'number' ? extra.replay_size : null;
  const epsilon = typeof extra.epsilon === 'number' ? extra.epsilon : null;
  const rows = transitionRows(extra.replay_sample);

  return (
    <>
      <Panel title="DQN EXPERIENCE REPLAY" accent="var(--dqn)" actions={<LiveTag />}>
        <div className="stat-grid">
          <Stat label="buffer size" value={replaySize == null ? NO_DATA : int(replaySize)} note="transitions stored" />
          <Stat label="epsilon" value={num(epsilon, 3)} note="0 in inference — acts greedily" />
        </div>
        <p className="panel-sub">
          §17: each row below is one stored transition — <strong>state → action → reward → next
          state → done</strong> — sampled uniformly from the buffer, not in time order. The buffer
          fills as the live loop runs; <code>learn()</code> only runs during a training session.
        </p>
        {error ? <p className="train-form-error">Inspector unavailable: {error}</p> : null}
      </Panel>

      <Panel title="SAMPLED TRANSITIONS" accent="var(--dqn)">
        {rows.length === 0 ? (
          <Empty>
            The replay buffer is empty. Start the simulation in AI mode and let a few decisions run —
            transitions are recorded as the loop steps.
          </Empty>
        ) : (
          <div className="insp-tr-list">
            {rows.map((t, i) => (
              <div className="insp-tr" key={i}>
                <div className="insp-tr-state">
                  <SectionLabel>state</SectionLabel>
                  {Object.entries(t.state_summary ?? {}).map(([k, v]) => (
                    <KV key={k} k={k.replace(/_/g, ' ')} v={num(v, 3)} />
                  ))}
                </div>
                <div className="insp-tr-mid">
                  <Badge tone="info">{t.action}</Badge>
                  <span className={t.reward < 0 ? 'insp-neg' : 'insp-pos'}>reward {num(t.reward, 3)}</span>
                  <Badge tone={t.done ? 'bad' : 'neutral'}>{t.done ? 'done' : 'not done'}</Badge>
                </div>
                <div className="insp-tr-state">
                  <SectionLabel>next state</SectionLabel>
                  {Object.entries(t.next_state_summary ?? {}).map(([k, v]) => (
                    <KV key={k} k={k.replace(/_/g, ' ')} v={num(v, 3)} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </>
  );
}

/* ------------------------------------------------------------------ page */

export function InspectorLab() {
  const [tab, setTab] = useState<InspTab>('coordination');

  return (
    <main className="training-lab">
      <div className="lab-legend">
        <div className="lab-legend-item">
          <SectionLabel>PAUSE &amp; INSPECT</SectionLabel>
          <p>
            Read-only views of the live decision loop. Pause the simulation from the command bar to
            freeze the current frame, then step through it here.
          </p>
        </div>
        <div className="lab-legend-item">
          <SectionLabel>REAL STATE ONLY</SectionLabel>
          <p>
            Every value comes straight from the backend — the coordinator&apos;s trace, the signal
            state machine, per-vehicle physics, the DQN replay buffer. Nothing is reconstructed.
          </p>
        </div>
        <div className="lab-legend-item">
          <SectionLabel>SAFETY IS AUTHORITATIVE</SectionLabel>
          <p>
            The coordination brain shows the agents&apos; recommendations and then what the safety
            layer actually applied. The agents recommend; the safety layer decides.
          </p>
        </div>
      </div>

      <div className="insp-tabs" role="group" aria-label="Inspector view">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={tab === t.id ? 'active' : ''}
            aria-pressed={tab === t.id}
            type="button"
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="lab-col">
        {tab === 'coordination' ? <CoordinationBrain /> : null}
        {tab === 'signal' ? <SignalInspector /> : null}
        {tab === 'emergency' ? <EmergencyInspector /> : null}
        {tab === 'vehicles' ? <VehicleInspector /> : null}
        {tab === 'dqn-replay' ? <DqnReplayInspector /> : null}
      </div>
    </main>
  );
}
