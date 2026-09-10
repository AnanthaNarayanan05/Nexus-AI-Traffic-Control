import type { Route } from '../lib/hashRoute';

/** Minimal footer (R11 §29): identity and a few quiet links. No tech stack. */
export function AppFooter({ go }: { go: (r: Route) => void }) {
  return (
    <footer className="app-footer">
      <span className="app-footer-brand">NEXUS · Intelligent Traffic Control</span>
      <span className="app-footer-links">
        <button onClick={() => go('events')}>Event replay</button>
        <button onClick={() => go('reports')}>Reports</button>
        <button onClick={() => go('settings')}>Settings</button>
        <button onClick={() => go('help')}>Help</button>
      </span>
    </footer>
  );
}
