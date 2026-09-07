import { AGENT_OBJECTIVE, AGENT_OWNER, NO_DATA, num, pct, signed } from '../lib/format';
import { useAgentInspector } from '../hooks/useAgentInspector';
import { useAgentStore, useSimStore } from '../store';
import { Badge, Bar, Empty, KV, Panel, SectionLabel, TrainedBadge } from './common/Primitives';
import { RewardBars } from './common/RewardBars';

const A2C_COLOR = 'var(--a2c)';

export function A2CPanel() {
  const slice = useAgentStore((s) => s.agents.a2c);
  const winner = useAgentStore((s) => s.coordination?.coordination.winner ?? null);
  const emergency = useSimStore((s) => s.state?.emergency);
  const status = useSimStore((s) => s.status?.agents.a2c);
  const { data: inspector, error } = useAgentInspector('a2c');

  const rec = slice?.recommendation;
  const labels = inspector?.action_labels ?? [];
  // Prefer the distribution attached to the live recommendation - it belongs to the
  // decision that was actually taken. The inspector fills in only when no decision has
  // streamed yet.
  const dist = rec?.action_distribution ?? inspector?.action_distribution ?? [];
  const priority = rec?.priority ?? null;

  return (
    <Panel
      title="A2C · Emergency Priority"
      accent={A2C_COLOR}
      sub={AGENT_OWNER.a2c}
      actions={
        <span style={{ marginLeft: 6 }}>
          <TrainedBadge isTrained={status?.is_trained} episodes={status?.trained_episodes} />
        </span>
      }
    >
      <p className="stat-note" style={{ marginTop: -2 }}>
        {AGENT_OBJECTIVE.a2c}
      </p>

      {emergency?.active ? (
        <div className="banner bad">
          <strong>{emergency.type ?? 'emergency'}</strong>
          <span>
            {emergency.approach ?? NO_DATA} · {num(emergency.distance_m, 0)} m ·{' '}
            {num(emergency.speed_mps)} m/s · ETA {num(emergency.eta_s)} s
          </span>
        </div>
      ) : (
        <div className="banner warn" style={{ opacity: 0.62 }}>
          No emergency vehicle in the network
        </div>
      )}

      <div className="stat-grid">
        <div className="stat">
          <span className="stat-label">Emergency priority</span>
          <span className="stat-value" style={{ color: priority === null ? undefined : A2C_COLOR }}>
            {pct(priority)}
          </span>
          <span className="stat-note">actor-head priority signal</span>
        </div>
        <div className="stat">
          <span className="stat-label">Cleared this episode</span>
          <span className="stat-value">{emergency?.cleared_this_episode ?? NO_DATA}</span>
        </div>
      </div>

      <div>
        <SectionLabel>Actor policy π(a|s)</SectionLabel>
        {dist.length === 0 ? (
          <Empty>No forward pass yet — start the simulation.</Empty>
        ) : (
          <div style={{ marginTop: 5 }}>
            {dist.map((p, i) => (
              <Bar
                key={labels[i] ?? i}
                label={labels[i] ?? `a${i}`}
                value={p}
                max={1}
                color={A2C_COLOR}
                selected={rec ? i === rec.action_index : false}
                display={pct(p, 1)}
              />
            ))}
          </div>
        )}
      </div>

      <div className="stat-grid">
        <div className="stat">
          <span className="stat-label">Critic V(s)</span>
          <span className="stat-value">{signed(inspector?.value_estimate)}</span>
        </div>
        <div className="stat">
          <span className="stat-label">Advantage</span>
          <span className="stat-value">{signed(inspector?.advantage)}</span>
        </div>
      </div>

      <div className="divider" />

      <KV k="action" v={rec?.action_name ?? NO_DATA} />
      <KV k="target phase" v={rec?.target_phase ?? NO_DATA} />
      <KV k="confidence" v={pct(rec?.confidence)} />
      <KV
        k="coordination"
        v={
          winner === null ? (
            NO_DATA
          ) : winner === 'a2c' ? (
            <Badge tone="good">WON</Badge>
          ) : (
            <Badge tone="neutral">{winner}</Badge>
          )
        }
      />
      {rec?.reason ? (
        <p className="stat-note" style={{ lineHeight: 1.4 }}>
          {rec.reason}
        </p>
      ) : null}

      <div className="divider" />

      <SectionLabel>Reward decomposition</SectionLabel>
      <RewardBars breakdown={slice?.reward_breakdown ?? null} color={A2C_COLOR} />

      {error ? <p className="stat-note">Inspector unavailable: {error}</p> : null}
    </Panel>
  );
}
