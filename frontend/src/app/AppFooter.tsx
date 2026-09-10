import type { Route } from '../lib/hashRoute';

/** Minimal footer (R11 §29): identity and a couple of quiet links. No tech stack. */
export function AppFooter({ go }: { go: (r: Route) => void }) {
  return (
    <footer className="app-footer">
      <span className="app-footer-brand">NEXUS · Intelligent Traffic Control</span>
      <span className="app-footer-links">
        <button onClick={() => go('help')}>Help</button>
        <button onClick={() => go('insights')}>Insights</button>
        <button onClick={() => go('reports')}>Reports</button>
      </span>
    </footer>
  );
}
