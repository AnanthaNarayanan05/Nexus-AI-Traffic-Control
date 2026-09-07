import { useState } from 'react';

import { AGENT_LABEL, NO_DATA, num, pct, titleise } from '../lib/format';
import type { AgentKey, AgentRecommendation, SafetyAction } from '../lib/types';
import { useAgentStore } from '../store';
import { Badge, Empty, Panel } from './common/Primitives';

const AGENT_COLOR: Record<AgentKey, string> = {
  a2c: 'var(--a2c)',
  dqn: 'var(--dqn)',
  ppo: 'var(--ppo)',
};

const ORDER: AgentKey[] = ['a2c', 'dqn', 'ppo'];

/** APPLIED means the safety layer passed the command through unchanged. */
const SAFETY_TONE: Record<SafetyAction, 'good' | 'warn' | 'bad'> = {
  APPLIED: 'good',
  REWRITTEN_TRANSITION: 'warn',
  BLOCKED_HOLD: 'warn',
  FORCED_CHANGE: 'bad',
  EMERGENCY_TIMEOUT: 'bad',
};

function AgentCard({ rec, winner }: { rec: AgentRecommendation | undefined; winner: string | null }) {
  if (!rec) {
    return (
      <div className="coord-card">
        <span className="coord-agent">{NO_DATA}</span>
        <span className="coord-action">{NO_DATA}</span>
      </div>
    );
  }
  const isWinner = winner === rec.agent;
  return (
    <div
      className={isWinner ? 'coord-card winner' : 'coord-card'}
      style={{ borderLeftColor: AGENT_COLOR[rec.agent] }}
    >
      <span className="coord-agent" style={{ color: AGENT_COLOR[rec.agent] }}>
        {AGENT_LABEL[rec.agent]} → {rec.target_phase}
      </span>
      <span className="coord-action">{rec.action_name}</span>
      <span className="coord-reason" title={rec.reason}>
        {rec.reason}
      </span>
      <span className="stat-note">
        score {num(rec.score, 2)} · conf {pct(rec.confidence)} · prio {pct(rec.priority)}
      </span>
    </div>
  );
}

export function CoordinationBar() {
  const update = useAgentStore((s) => s.coordination);
  const [showLadder, setShowLadder] = useState(false);

  if (!update) {
    return (
      <Panel title="Coordination → Safety → Signal" accent="var(--accent)">
        <Empty>
          No decision has been produced yet. Start the simulation in AI mode to see the pipeline.
        </Empty>
      </Panel>
    );
  }

  const { coordination, safety, applied_phase, decision_id } = update;
  const byAgent = new Map<AgentKey, AgentRecommendation>();
  coordination.recommendations.forEach((r) => byAgent.set(r.agent, r));
  const winnerIsAgent = ORDER.includes(coordination.winner as AgentKey);
  const safetyTone = SAFETY_TONE[safety.action_taken] ?? 'neutral';
  const rewritten = safety.action_taken !== 'APPLIED';
  const phaseChanged = applied_phase !== coordination.candidate_phase;

  return (
    <Panel
      title="Coordination → Safety → Signal"
      accent="var(--accent)"
      sub={`#${decision_id.slice(0, 8)}`}
      actions={
        <button
          className="btn"
          style={{ marginLeft: 6, padding: '2px 7px', fontSize: 10.5 }}
          onClick={() => setShowLadder((v) => !v)}
        >
          {showLadder ? 'Hide ladder' : 'Show ladder'}
        </button>
      }
      bodyClass="tight"
    >
      <div className="coord-flow">
        {ORDER.map((a) => (
          <AgentCard key={a} rec={byAgent.get(a)} winner={coordination.winner} />
        ))}

        <span className="coord-arrow">→</span>

        <div className="coord-card winner">
          <span className="coord-agent" style={{ color: 'var(--accent)' }}>
            COORDINATION
          </span>
          <span className="coord-action">
            {coordination.candidate_phase}
            {'  '}
            <Badge tone={winnerIsAgent ? 'info' : 'neutral'}>
              {winnerIsAgent
                ? AGENT_LABEL[coordination.winner as AgentKey]
                : coordination.winner.toUpperCase()}
            </Badge>
          </span>
          <span className="coord-reason" title={coordination.basis}>
            {titleise(coordination.basis)}
          </span>
        </div>

        <span className="coord-arrow">→</span>

        <div
          className="coord-card"
          style={{ borderLeftColor: rewritten ? 'var(--yellow)' : 'var(--green)' }}
        >
          <span className="coord-agent" style={{ color: rewritten ? 'var(--yellow)' : 'var(--green)' }}>
            SAFETY · AUTHORITATIVE
          </span>
          <span className="coord-action">
            {applied_phase} <Badge tone={safetyTone}>{safety.action_taken}</Badge>
          </span>
          <span className="coord-reason" title={safety.reason}>
            {safety.reason}
          </span>
          {safety.violated_rules.length ? (
            <span className="stat-note" style={{ color: 'var(--yellow)' }}>
              rules: {safety.violated_rules.join(', ')}
            </span>
          ) : null}
        </div>
      </div>

      {rewritten ? (
        <div className="banner warn">
          {phaseChanged
            ? `Safety layer overrode the coordinated choice ${coordination.candidate_phase} → ${applied_phase}.`
            : `Safety layer intervened (${titleise(safety.action_taken)}) but the served phase ${applied_phase} is unchanged.`}{' '}
          No agent recommendation can bypass this layer.
        </div>
      ) : null}

      {showLadder ? (
        <div className="ladder">
          {coordination.ladder_trace.length === 0 ? (
            <Empty>No ladder trace on this decision.</Empty>
          ) : (
            coordination.ladder_trace.map((step, i) => (
              <div className="ladder-step" key={`${step.rung}-${i}`}>
                <span className="ladder-rung">{step.rung}</span>
                <span className={`ladder-outcome ${step.outcome}`}>{step.outcome}</span>
                <span>{step.detail}</span>
              </div>
            ))
          )}
          {coordination.scores.length ? (
            <>
              <div className="divider" />
              {coordination.scores.map((s) => (
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
      ) : null}
    </Panel>
  );
}
