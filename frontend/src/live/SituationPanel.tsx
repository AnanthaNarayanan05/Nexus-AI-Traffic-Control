import { int } from '../lib/format';
import { busiestApproach, emergencyRead, trafficLevel } from '../lib/situation';
import { useAgentStore, useSimStore } from '../store';

/**
 * "Current situation" (R11 §9) — a compact, plain-language read of the live state.
 * Every row is derived from a value the backend produced; when the value is missing
 * the row is omitted rather than guessed.
 */
export function SituationPanel() {
  const state = useSimStore((s) => s.state);
  const coordination = useAgentStore((s) => s.coordination);

  const level = trafficLevel(state);
  const em = emergencyRead(state);
  const busy = busiestApproach(state);
  const vehicles = state?.totals?.vehicles ?? null;
  const priorityActive = state?.emergency?.active || coordination?.coordination.winner === 'a2c';

  const rows: { label: string; value: string; tone?: 'alert' | 'ok' }[] = [];
  if (level) rows.push({ label: 'Traffic', value: level, tone: level === 'Heavy' ? 'alert' : undefined });
  if (em) {
    rows.push({
      label: 'Emergency',
      value:
        em.etaSeconds !== null
          ? `${em.type} · ${em.approachName} · ${Math.round(em.etaSeconds)}s`
          : `${em.type} · ${em.approachName}`,
      tone: 'alert',
    });
  }
  rows.push({
    label: 'Response priority',
    value: priorityActive ? 'Active' : 'Standby',
    tone: priorityActive ? 'alert' : undefined,
  });
  if (busy && !em) rows.push({ label: 'Heaviest side', value: `${busy.name} approach` });
  if (vehicles !== null) rows.push({ label: 'Vehicles', value: int(vehicles) });
  rows.push({
    label: 'Status',
    value: state ? 'Intersection managed' : 'Waiting to start',
    tone: state ? 'ok' : undefined,
  });

  return (
    <section className="situation-panel" aria-label="Current situation">
      <h2 className="panel-kicker">Current situation</h2>
      <dl className="situation-list">
        {rows.map((r) => (
          <div className={r.tone ? `situation-row ${r.tone}` : 'situation-row'} key={r.label}>
            <dt>{r.label}</dt>
            <dd>{r.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
