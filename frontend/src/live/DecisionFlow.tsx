import { useState } from 'react';

import { CoordinationBar } from '../components/CoordinationBar';
import {
  AGENT_PRODUCT_NAME,
  SAFETY_PRODUCT_STATUS,
  coordinationBasisText,
  signalActionText,
} from '../lib/format';
import type { AgentKey } from '../lib/types';
import { useAgentStore } from '../store';

/**
 * The coordination pipeline for a customer (R11 §13, §14, §15):
 *   AI recommendations → NEXUS decision → safety check → signal action
 * as four plain statements. "Why did NEXUS choose this?" expands a short explanation;
 * "Decision details" reveals the full engineering view (unchanged component).
 */
export function DecisionFlow() {
  const update = useAgentStore((s) => s.coordination);
  const [why, setWhy] = useState(false);
  const [details, setDetails] = useState(false);

  if (!update) {
    return (
      <section className="decision-flow" aria-label="AI decision">
        <h2 className="panel-kicker">AI decision</h2>
        <p className="decision-empty">
          Start the simulation to see how NEXUS decides which way to run the signal.
        </p>
      </section>
    );
  }

  const { coordination, safety, applied_phase } = update;
  const winner = coordination.winner;
  const winnerName =
    winner === 'a2c' || winner === 'dqn' || winner === 'ppo'
      ? AGENT_PRODUCT_NAME[winner as AgentKey]
      : 'Safe default';
  const safetyInfo = SAFETY_PRODUCT_STATUS[safety.action_taken] ?? SAFETY_PRODUCT_STATUS.APPLIED;
  const phaseText = signalActionText(applied_phase);

  const steps: { label: string; value: string }[] = [
    { label: 'AI recommendations', value: 'Emergency, Efficiency and Congestion each proposed a signal.' },
    { label: 'NEXUS decision', value: `${winnerName} recommendation selected.` },
    { label: 'Safety check', value: safetyInfo.label },
    { label: 'Signal action', value: phaseText },
  ];

  return (
    <section className="decision-flow" aria-label="AI decision">
      <h2 className="panel-kicker">AI decision</h2>
      <ol className="decision-steps">
        {steps.map((s, i) => (
          <li key={s.label}>
            <span className="decision-step-index" aria-hidden="true">{i + 1}</span>
            <span className="decision-step-label">{s.label}</span>
            <span className="decision-step-value">{s.value}</span>
          </li>
        ))}
      </ol>

      <div className="decision-actions">
        <button className="link-btn" onClick={() => setWhy((v) => !v)} aria-expanded={why}>
          {why ? 'Hide explanation' : 'Why did NEXUS choose this?'}
        </button>
        <button className="link-btn" onClick={() => setDetails((v) => !v)} aria-expanded={details}>
          {details ? 'Hide decision details' : 'Decision details'}
        </button>
      </div>

      {why ? (
        <div className="decision-why">
          <p>{coordinationBasisText(winner)}</p>
          <p>{safetyInfo.detail}</p>
        </div>
      ) : null}

      {details ? (
        <div className="decision-details">
          <CoordinationBar />
        </div>
      ) : null}
    </section>
  );
}
