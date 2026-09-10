import { ExperimentLab } from '../experiments/ExperimentLab';

/**
 * Insights (R11 §23): how NEXUS compares with a traditional fixed-timer signal.
 * The framing here is plain-language; the measured comparison, its seeds and
 * confidence intervals are produced by the comparison tools below — honest numbers,
 * never a manufactured improvement (MASTER_PROMPT §84).
 */
export function InsightsView() {
  return (
    <main className="page insights">
      <header className="page-head">
        <h1>Insights</h1>
        <p>
          NEXUS is measured against a traditional fixed-timer signal on the same
          scenario, with the same traffic and the same safety rules. Each comparison
          runs several times so the result reflects a real difference, not luck.
        </p>
      </header>

      <div className="insights-legend">
        <h2>How to read a comparison</h2>
        <ul>
          <li>
            <strong>Waiting time, queue length, stops</strong> — lower is better for
            drivers.
          </li>
          <li>
            <strong>Throughput and average speed</strong> — higher means more traffic
            cleared.
          </li>
          <li>
            <strong>Safety events</strong> — should stay at zero under both signals.
          </li>
          <li>
            A result is only meaningful when the ranges (shown as ±) for NEXUS and the
            fixed timer don&apos;t overlap.
          </li>
        </ul>
      </div>

      <ExperimentLab />
    </main>
  );
}
