import { useEffect, useRef, useState } from 'react';

import { clock } from '../lib/format';
import type { Route } from '../lib/hashRoute';
import { ADVANCED_NAV, PRIMARY_NAV, SECONDARY_NAV } from '../lib/hashRoute';
import { useSimStore } from '../store';

/**
 * The product header (R11 §5, §28). NEXUS wordmark, a small number of primary
 * destinations, and — only when a simulation is loaded — a live indicator with the
 * scenario name and clock. No seed, config digest, step counter or build state: those
 * live behind the advanced tools, never on the primary surface.
 */
export function AppHeader({ route, go }: { route: Route; go: (r: Route) => void }) {
  const status = useSimStore((s) => s.status);
  const state = useSimStore((s) => s.state);
  const connection = useSimStore((s) => s.connection);
  const running = status?.running ?? false;
  const scenarioName = status?.scenario?.name ?? null;
  const simTime = state?.sim_time ?? status?.sim_time ?? null;

  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const onDown = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setMenuOpen(false);
    window.addEventListener('mousedown', onDown);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('mousedown', onDown);
      window.removeEventListener('keydown', onKey);
    };
  }, [menuOpen]);

  return (
    <header className="app-header">
      <button className="app-brand" onClick={() => go('')} aria-label="NEXUS home">
        <span className="app-brand-mark" aria-hidden="true" />
        <span className="app-brand-name">NEXUS</span>
        <span className="app-brand-sub">Traffic Control</span>
      </button>

      <nav className="app-nav" aria-label="Primary">
        {PRIMARY_NAV.map(({ route: r, label }) => (
          <button
            key={r || 'home'}
            className={route === r ? 'app-nav-link active' : 'app-nav-link'}
            aria-current={route === r ? 'page' : undefined}
            onClick={() => go(r)}
          >
            {label}
          </button>
        ))}
      </nav>

      <div className="app-header-right">
        {(running || simTime !== null) && scenarioName ? (
          <span className="app-live" title="Live simulation">
            <span className={running ? 'app-live-dot running' : 'app-live-dot'} aria-hidden="true" />
            <span className="app-live-label">{running ? 'Live' : 'Paused'}</span>
            <span className="app-live-scenario">{scenarioName}</span>
            <span className="app-live-clock">{clock(simTime ?? 0)}</span>
          </span>
        ) : (
          <span
            className={
              connection === 'open' ? 'app-conn ok' : connection === 'connecting' ? 'app-conn wait' : 'app-conn down'
            }
          >
            {connection === 'open'
              ? 'System ready'
              : connection === 'connecting'
                ? 'Connecting…'
                : 'Offline'}
          </span>
        )}

        <div className="app-menu" ref={menuRef}>
          <button
            className="app-menu-trigger"
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((v) => !v)}
          >
            More
          </button>
          {menuOpen ? (
            <div className="app-menu-list" role="menu">
              {SECONDARY_NAV.map(({ route: r, label }) => (
                <button
                  key={r}
                  role="menuitem"
                  onClick={() => {
                    setMenuOpen(false);
                    go(r);
                  }}
                >
                  {label}
                </button>
              ))}
              <div className="app-menu-sep" />
              <span className="app-menu-heading">Advanced tools</span>
              {ADVANCED_NAV.map(({ route: r, label }) => (
                <button
                  key={r}
                  role="menuitem"
                  onClick={() => {
                    setMenuOpen(false);
                    go(r);
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </header>
  );
}
