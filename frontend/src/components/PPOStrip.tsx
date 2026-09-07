import { useAgentInspector } from '../hooks/useAgentInspector';
import { AGENT_OBJECTIVE, AGENT_OWNER, NO_DATA, int, num, pct } from '../lib/format';
import type { Approach } from '../lib/types';
import { useAgentStore, useSimStore } from '../store';
import { Badge, Bar, Empty, KV, Panel, SectionLabel, TrainedBadge } from './common/Primitives';
import { RewardBars } from './common/RewardBars';

const PPO_COLOR = 'var(--ppo)';
const APPROACHES: Approach[] = ['N', 'E', 'S', 'W'];

function pressureColor(p: number | null): string {
  if (p === null) return 'var(--text-faint)';
  if (p >= 0.66) return 'var(--red)';
  if (p >= 0.33) return 'var(--yellow)';
  return 'var(--green)';
}

export function PPOStrip() {
  const slice = useAgentStore((s) => s.agents.ppo);
  const winner = useAgentStore((s) => s.coordination?.coordination.winner ?? null);
  const status = useSimStore((s) => s.status?.agents.ppo);
  const approaches = useSimStore((s) => s.state?.approaches);
  const { data: inspector, error } = useAgentInspector('ppo');

  const rec = slice?.recommendation;
  const labels = inspector?.action_labels ?? [];
  const dist = rec?.action_distribution ?? inspector?.action_distribution ?? [];
  const pressure = (inspector?.extra?.queue_pressure ?? null) as Record<string, number> | null;
  const advice = (inspector?.extra?.recommendation ?? null) as string | null;

  return (
    <Panel
      title="PPO · Congestion"
      accent={PPO_COLOR}
      sub={AGENT_OWNER.ppo}
      actions={
        <span style={{ marginLeft: 6 }}>
          <TrainedBadge isTrained={status?.is_trained} episodes={status?.trained_episodes} />
        </span>
      }
      bodyClass="tight"
    >
      <p className="stat-note" style={{ marginTop: -2 }}>
        {AGENT_OBJECTIVE.ppo}
      </p>

      <SectionLabel>Queue pressure per approach</SectionLabel>
      <div className="pressure-strip">
        {APPROACHES.map((a) => {
          const p = pressure && Number.isFinite(pressure[a]) ? pressure[a] : null;
          const ap = approaches?.[a];
          return (
            <div className="pressure-cell" key={a}>
              <div className="pressure-head">
                <span className="pressure-approach">{a}</span>
                <span style={{ color: pressureColor(p) }}>{pct(p)}</span>
              </div>
              <span className="bar-track">
                {p === null ? null : (
                  <span
                    className="bar-fill"
                    style={{ width: `${Math.min(100, p * 100)}%`, background: pressureColor(p) }}
                  />
                )}
              </span>
              <span className="stat-note">
                q {int(ap?.queue_length)} · w {num(ap?.mean_wait_s)}s
              </span>
            </div>
          );
        })}
      </div>

      {advice ? (
        <div className="banner warn" style={{ borderColor: 'rgba(245,197,66,0.28)' }}>
          <strong>{advice}</strong>
        </div>
      ) : null}

      <SectionLabel>Policy π(a|s)</SectionLabel>
      {dist.length === 0 ? (
        <Empty>No forward pass yet.</Empty>
      ) : (
        <div>
          {dist.map((p, i) => (
            <Bar
              key={labels[i] ?? i}
              label={labels[i] ?? `a${i}`}
              value={p}
              max={1}
              color={PPO_COLOR}
              selected={rec ? i === rec.action_index : false}
              display={pct(p, 1)}
            />
          ))}
        </div>
      )}

      <div className="divider" />
      <KV k="target phase" v={rec?.target_phase ?? NO_DATA} />
      <KV k="confidence" v={pct(rec?.confidence)} />
      <KV
        k="coordination"
        v={
          winner === null ? (
            NO_DATA
          ) : winner === 'ppo' ? (
            <Badge tone="good">WON</Badge>
          ) : (
            <Badge tone="neutral">{winner}</Badge>
          )
        }
      />

      <div className="divider" />
      <SectionLabel>Reward decomposition</SectionLabel>
      <RewardBars breakdown={slice?.reward_breakdown ?? null} color={PPO_COLOR} />

      {error ? <p className="stat-note">Inspector unavailable: {error}</p> : null}
    </Panel>
  );
}
