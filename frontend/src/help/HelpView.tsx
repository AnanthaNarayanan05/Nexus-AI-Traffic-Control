import type { Route } from '../lib/hashRoute';

/** Plain-language help (R11 §46). Short, no jargon, no setup required. */
export function HelpView({ go }: { go: (r: Route) => void }) {
  return (
    <main className="page help">
      <header className="page-head">
        <h1>Help</h1>
        <p>NEXUS in a couple of minutes.</p>
      </header>

      <section className="help-section">
        <h2>What NEXUS does</h2>
        <p>
          NEXUS runs a busy four-way intersection in real time. It watches every
          approach, decides which way to run the traffic signal, gives way to
          emergency vehicles, and eases congestion when one direction gets busy. An
          independent safety layer checks every signal change before it happens.
        </p>
      </section>

      <section className="help-section">
        <h2>Getting started</h2>
        <ol>
          <li>
            Open <button className="link-btn" onClick={() => go('scenarios')}>Scenarios</button> and
            pick a traffic situation.
          </li>
          <li>
            Watch the intersection on the <button className="link-btn" onClick={() => go('live')}>Live</button> page.
            The panels around it explain what NEXUS is doing and why.
          </li>
          <li>
            Use <button className="link-btn" onClick={() => go('insights')}>Insights</button> to
            compare NEXUS with a traditional fixed-timer signal.
          </li>
        </ol>
      </section>

      <section className="help-section">
        <h2>The three AI capabilities</h2>
        <ul>
          <li>
            <strong>Emergency Response</strong> — detects an approaching ambulance or
            fire truck and clears its path.
          </li>
          <li>
            <strong>Traffic Efficiency</strong> — shortens waits and reduces stops and
            fuel use.
          </li>
          <li>
            <strong>Congestion Management</strong> — rebalances the signal when demand
            is uneven.
          </li>
        </ul>
        <p>
          NEXUS listens to all three every few seconds, picks the most important one
          for the moment, and applies it — after the safety check.
        </p>
      </section>

      <section className="help-section">
        <h2>Safety</h2>
        <p>
          The safety layer is always on and cannot be switched off. If an AI
          recommendation would create an unsafe signal transition, NEXUS adjusts or
          holds it and tells you on the Live page.
        </p>
      </section>
    </main>
  );
}
