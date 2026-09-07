import { useAgentInspector } from '../hooks/useAgentInspector';
import { AGENT_OBJECTIVE, AGENT_OWNER, NO_DATA, int, num, pct, signed } from '../lib/format';
import { useAgentStore, useSimStore } from '../store';
import { Badge, Bar, Empty, KV, Panel, SectionLabel, TrainedBadge } from './common/Primitives';
import { RewardBars } from './common/RewardBars';

const DQN_COLOR = 'var(--dqn)';

function numberOrNull(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

export function DQNPanel() {
  const slice = useAgentStore((s) => s.agents.dqn);
  const winner = useAgentStore((s) => s.coordination?.coordination.winner ?? null);
  const status = useSimStore((s) => s.status?.agents.dqn);
  const estimates = useSimStore((s) => s.state?.estimates);
  const safety = useSimStore((s) => s.state?.safety);
  const { data: inspector, error } = useAgentInspector('dqn');

  const rec = slice?.recommendation;
  const labels = inspector?.action_labels ?? [];
  // Raw Q-values, not the softmax the coordinator scores with - a DQN has no policy head.
  const qMap = (inspector?.extra?.q_values ?? null) as Record<string, number> | null;
  const qValues = qMap ? labels.map((l) => numberOrNull(qMap[l])) : [];
  const finiteQ = qValues.filter((v): v is number => v !== null);
  const qMin = finiteQ.length ? Math.min(...finiteQ) : 0;
  const qMax = finiteQ.length ? Math.max(...finiteQ) : 1;
  const pad = Math.max(0.05, (qMax - qMin) * 0.12);

  const epsilon = numberOrNull(inspector?.extra?.epsilon);
  const replaySize = numberOrNull(inspector?.extra?.replay_size);
  const training = inspector?.training as Record<string, unknown> | undefined;

  return (
    <Panel
      title="DQN · Fuel · Emissions · Safety"
      accent={DQN_COLOR}
      sub={AGENT_OWNER.dqn}
      actions={
        <span style={{ marginLeft: 6 }}>
          <TrainedBadge isTrained={status?.is_trained} episodes={status?.trained_episodes} />
        </span>
      }
    >
      <p className="stat-note" style={{ marginTop: -2 }}>
        {AGENT_OBJECTIVE.dqn}
      </p>

      <div className="stat-grid">
        <div className="stat" title="Parametric estimate, not a measured tailpipe value (docs/assumptions.md A12)">
          <span className="stat-label">
            Fuel rate <span className="estimated-tag">EST</span>
          </span>
          <span className="stat-value">
            {num(estimates?.fuel_l_per_s, 3)}
            <span className="stat-unit">L/s</span>
          </span>
        </div>
        <div className="stat" title="CO2 = fuel x 2.31 kg/L (docs/assumptions.md A13)">
          <span className="stat-label">
            CO₂ rate <span className="estimated-tag">EST</span>
          </span>
          <span className="stat-value">
            {num(estimates?.co2_kg_per_s, 4)}
            <span className="stat-unit">kg/s</span>
          </span>
        </div>
        <div className="stat">
          <span className="stat-label">Violations</span>
          <span className="stat-value" style={{ color: safety?.violations_total ? 'var(--orange)' : undefined }}>
            {int(safety?.violations_total)}
          </span>
          <span className="stat-note">{int(safety?.violations_last_window)} in window</span>
        </div>
        <div className="stat">
          <span className="stat-label">Unsafe transitions</span>
          <span className="stat-value">{int(safety?.unsafe_transitions_total)}</span>
        </div>
      </div>

      <div>
        <SectionLabel>Q(s, a)</SectionLabel>
        {qValues.length === 0 ? (
          <Empty>No Q-values yet — start the simulation.</Empty>
        ) : (
          <div style={{ marginTop: 5 }}>
            {qValues.map((q, i) => (
              <Bar
                key={labels[i] ?? i}
                label={labels[i] ?? `a${i}`}
                value={q}
                min={Math.min(0, qMin - pad)}
                max={qMax + pad}
                color={DQN_COLOR}
                selected={labels[i] === inspector?.selected_action}
                display={signed(q, 3)}
              />
            ))}
          </div>
        )}
      </div>

      <div className="stat-grid">
        <div className="stat" title="Exploration rate. Inference-only runs act greedily.">
          <span className="stat-label">Epsilon</span>
          <span className="stat-value">{num(epsilon, 3)}</span>
        </div>
        <div className="stat">
          <span className="stat-label">Replay buffer</span>
          <span className="stat-value">{int(replaySize)}</span>
          <span className="stat-note">transitions stored</span>
        </div>
      </div>

      {status?.is_trained ? (
        <div className="stat-grid">
          <div className="stat">
            <span className="stat-label">Q loss</span>
            <span className="stat-value">{num(numberOrNull(training?.q_loss), 4)}</span>
          </div>
          <div className="stat">
            <span className="stat-label">TD error</span>
            <span className="stat-value">{num(numberOrNull(training?.td_error), 4)}</span>
          </div>
        </div>
      ) : (
        <p className="stat-note">
          No gradient updates have run in this process, so loss and TD-error are not reported.
        </p>
      )}

      <div className="divider" />

      <KV k="action" v={rec?.action_name ?? NO_DATA} />
      <KV k="target phase" v={rec?.target_phase ?? NO_DATA} />
      <KV k="confidence" v={pct(rec?.confidence)} />
      <KV
        k="coordination"
        v={
          winner === null ? (
            NO_DATA
          ) : winner === 'dqn' ? (
            <Badge tone="good">WON</Badge>
          ) : (
            <Badge tone="neutral">{winner}</Badge>
          )
        }
      />

      <div className="divider" />

      <SectionLabel>Reward decomposition</SectionLabel>
      <RewardBars breakdown={slice?.reward_breakdown ?? null} color={DQN_COLOR} />

      {error ? <p className="stat-note">Inspector unavailable: {error}</p> : null}
    </Panel>
  );
}
