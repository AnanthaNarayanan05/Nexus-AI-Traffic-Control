/**
 * Small presentational primitives shared by the dashboard panels.
 *
 * None of these synthesise data: `value={null}` renders NO_DATA rather than a zero,
 * and `Bar` with a null value renders an empty track (MASTER_PROMPT sections 84, 98, 114).
 */

import type { ReactNode } from 'react';

import { NO_DATA, num } from '../../lib/format';

/* ------------------------------------------------------------------ Panel */

export function Panel({
  title,
  accent,
  sub,
  actions,
  children,
  flex,
  bodyClass,
}: {
  title: string;
  accent?: string;
  sub?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  flex?: boolean;
  bodyClass?: string;
}) {
  return (
    <section className={flex ? 'panel flex' : 'panel'}>
      <header className="panel-head">
        {accent ? <span className="panel-accent" style={{ background: accent }} /> : null}
        <span className="panel-title">{title}</span>
        {sub ? <span className="panel-sub">{sub}</span> : null}
        {actions}
      </header>
      <div className={bodyClass ? `panel-body ${bodyClass}` : 'panel-body'}>{children}</div>
    </section>
  );
}

/* ------------------------------------------------------------------ Badge */

export type BadgeTone = 'neutral' | 'good' | 'warn' | 'bad' | 'info';

export function Badge({
  tone = 'neutral',
  children,
  title,
}: {
  tone?: BadgeTone;
  children: ReactNode;
  title?: string;
}) {
  return (
    <span className={`badge ${tone}`} title={title}>
      {children}
    </span>
  );
}

/* ------------------------------------------------------------------ Stat */

export function Stat({
  label,
  value,
  unit,
  note,
  tone,
  title,
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  note?: ReactNode;
  tone?: string;
  title?: string;
}) {
  const missing = value === NO_DATA || value === null || value === undefined;
  return (
    <div className="stat" title={title}>
      <span className="stat-label">{label}</span>
      <span className="stat-value" style={{ color: missing ? 'var(--text-faint)' : tone }}>
        {missing ? NO_DATA : value}
        {!missing && unit ? <span className="stat-unit">{unit}</span> : null}
      </span>
      {note ? <span className="stat-note">{note}</span> : null}
    </div>
  );
}

/* ------------------------------------------------------------------ Bar */

/**
 * Horizontal bar. `value` is plotted against [min, max]; a null value draws no fill.
 * Bars that can go negative (Q-values, critic values, advantages) pass min < 0 and get
 * a zero marker so the sign is legible.
 */
export function Bar({
  label,
  value,
  min = 0,
  max = 1,
  color = 'var(--accent)',
  selected,
  display,
  digits = 2,
}: {
  label: string;
  value: number | null | undefined;
  min?: number;
  max?: number;
  color?: string;
  selected?: boolean;
  display?: string;
  digits?: number;
}) {
  const finite = value !== null && value !== undefined && Number.isFinite(value);
  const span = max - min || 1;
  const zeroPct = ((0 - min) / span) * 100;
  let leftPct = 0;
  let widthPct = 0;
  if (finite) {
    const v = Math.min(max, Math.max(min, value as number));
    if (min < 0) {
      const vPct = ((v - min) / span) * 100;
      leftPct = Math.min(vPct, zeroPct);
      widthPct = Math.abs(vPct - zeroPct);
    } else {
      widthPct = ((v - min) / span) * 100;
    }
  }
  return (
    <div className={selected ? 'bar-row selected' : 'bar-row'}>
      <span className="bar-label" title={label}>
        {label}
      </span>
      <span className="bar-track">
        {min < 0 ? <span className="bar-zero" style={{ left: `${zeroPct}%` }} /> : null}
        {finite ? (
          <span
            className="bar-fill"
            style={{
              marginLeft: `${leftPct}%`,
              width: `${widthPct}%`,
              background: color,
            }}
          />
        ) : null}
      </span>
      <span className="bar-value">{display ?? num(value, digits)}</span>
    </div>
  );
}

/* ------------------------------------------------------------------ misc */

export function KV({ k, v, tone }: { k: string; v: ReactNode; tone?: string }) {
  return (
    <div className="kv">
      <span>{k}</span>
      <span style={{ color: tone }}>{v}</span>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="empty">{children}</p>;
}

export function SectionLabel({ children }: { children: ReactNode }) {
  return <span className="section-label">{children}</span>;
}

/**
 * Honest badge for a model that has never been trained. Rendered wherever agent output
 * is shown so no viewer mistakes an untrained forward pass for a learned policy
 * (MASTER_PROMPT section 84).
 */
export function TrainedBadge({
  isTrained,
  episodes,
}: {
  isTrained: boolean | undefined;
  episodes: number | undefined;
}) {
  if (isTrained === undefined) return <Badge tone="neutral">{NO_DATA}</Badge>;
  if (!isTrained) {
    return (
      <Badge tone="warn" title="This policy has never been trained. Outputs are from randomly initialised weights.">
        UNTRAINED
      </Badge>
    );
  }
  return <Badge tone="good">TRAINED · {episodes ?? NO_DATA} ep</Badge>;
}
