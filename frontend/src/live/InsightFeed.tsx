import { useEffect, useRef, useState } from 'react';

import { clock } from '../lib/format';
import { insightLines } from '../lib/situation';
import { useAgentStore, useSimStore } from '../store';

interface Entry {
  id: number;
  at: number;
  text: string;
}

/**
 * A short rolling feed of natural-language insights (R11 §12). Lines are generated
 * from the real live state and coordinator decision — never invented — and appended
 * only when the wording actually changes, so the feed reads like commentary rather
 * than a log.
 */
export function InsightFeed() {
  const state = useSimStore((s) => s.state);
  const simTime = state?.sim_time ?? 0;
  const coordination = useAgentStore((s) => s.coordination);
  const [entries, setEntries] = useState<Entry[]>([]);
  const lastKey = useRef<string>('');
  const seq = useRef(0);

  useEffect(() => {
    const lines = insightLines(state, coordination);
    const key = lines.join(' | ');
    if (!key || key === lastKey.current) return;
    lastKey.current = key;
    const at = simTime;
    setEntries((prev) => {
      const next = [
        ...lines.map((text) => ({ id: (seq.current += 1), at, text })),
        ...prev,
      ];
      return next.slice(0, 6);
    });
  }, [state, coordination, simTime]);

  return (
    <section className="insight-feed" aria-label="AI insights" aria-live="polite">
      <h2 className="panel-kicker">AI insights</h2>
      {entries.length === 0 ? (
        <p className="insight-empty">NEXUS will explain each decision here as traffic develops.</p>
      ) : (
        <ul className="insight-list">
          {entries.map((e) => (
            <li key={e.id}>
              <span className="insight-time">{clock(e.at)}</span>
              <span className="insight-text">{e.text}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
