import { useMemo } from 'react';

import { clock } from '../lib/format';
import { ALL_CATEGORIES, useEventStore, useSimStore } from '../store';
import { Empty, Panel } from './common/Primitives';

export function EventTimeline() {
  const events = useEventStore((s) => s.events);
  const filters = useEventStore((s) => s.filters);
  const toggleFilter = useEventStore((s) => s.toggleFilter);
  const clear = useEventStore((s) => s.clear);
  const lastError = useSimStore((s) => s.lastError);
  const clearError = useSimStore((s) => s.clearError);

  const visible = useMemo(() => events.filter((e) => filters.has(e.category)), [events, filters]);

  return (
    <Panel
      title="Event timeline"
      accent="var(--text-dim)"
      sub={`${visible.length}/${events.length}`}
      flex
      bodyClass="tight"
      actions={
        <button
          className="btn"
          style={{ marginLeft: 6, padding: '2px 7px', fontSize: 10.5 }}
          onClick={clear}
        >
          Clear
        </button>
      }
    >
      <div className="filter-row" style={{ padding: 0, border: 'none' }}>
        {ALL_CATEGORIES.map((c) => (
          <button
            key={c}
            className={filters.has(c) ? 'filter-chip on' : 'filter-chip'}
            onClick={() => toggleFilter(c)}
          >
            <span className={`cat-${c}`}>{c}</span>
          </button>
        ))}
      </div>

      {lastError ? (
        <div className="banner bad" onClick={clearError} role="button" title="Dismiss">
          <strong>{lastError.code}</strong>
          <span>{lastError.message}</span>
        </div>
      ) : null}

      <div className="timeline">
        {visible.length === 0 ? (
          <Empty>
            {events.length === 0
              ? 'No events yet.'
              : 'All categories filtered out.'}
          </Empty>
        ) : (
          visible.map((e) => (
            <div className={`timeline-row ${e.severity}`} key={e.id}>
              <span className="timeline-t">{clock(e.t)}</span>
              <span className={`timeline-cat cat-${e.category}`}>{e.category}</span>
              <span className="timeline-desc">{e.description}</span>
            </div>
          ))
        )}
      </div>
    </Panel>
  );
}
