import { A2CPanel } from '../components/A2CPanel';
import { CommandBar } from '../components/CommandBar';
import { CoordinationBar } from '../components/CoordinationBar';
import { DQNPanel } from '../components/DQNPanel';
import { EventTimeline } from '../components/EventTimeline';
import { MetricsRow } from '../components/MetricsRow';
import { ModelModeBar } from '../components/ModelModeBar';
import { PPOStrip } from '../components/PPOStrip';
import { SimulationStage } from '../components/SimulationStage';
import { useSimStore } from '../store';
import { AiCapabilities } from './AiCapabilities';
import { CustomerMetrics } from './CustomerMetrics';
import { DecisionFlow } from './DecisionFlow';
import { EmergencyBanner } from './EmergencyBanner';
import { InsightFeed } from './InsightFeed';
import { LiveControls } from './LiveControls';
import { SafetyStatus } from './SafetyStatus';
import { SituationPanel } from './SituationPanel';

/**
 * The live traffic-control experience (R11 §7–§18). The 2D intersection is the hero;
 * everything around it is plain-language. The full engineering dashboard is preserved
 * verbatim behind a single disclosure at the bottom (R11 §51).
 */
export function LiveView() {
  const lastError = useSimStore((s) => s.lastError);
  const clearError = useSimStore((s) => s.clearError);

  return (
    <main className="page live">
      <EmergencyBanner />

      {lastError ? (
        <button className="live-error" onClick={clearError}>
          We couldn&apos;t apply that action. {friendlyError(lastError.message)}
        </button>
      ) : null}

      <LiveControls />

      <div className="live-grid">
        <div className="live-col left">
          <SituationPanel />
          <AiCapabilities />
        </div>

        <div className="live-col centre">
          <SimulationStage minimalChrome />
        </div>

        <div className="live-col right">
          <SafetyStatus />
          <InsightFeed />
        </div>
      </div>

      <DecisionFlow />

      <CustomerMetrics />

      <details className="engineering">
        <summary>Engineering view</summary>
        <p className="engineering-note">
          The full research dashboard — per-agent policies, Q-values, reward
          decomposition, coordination ladder and raw measured metrics. Kept for the
          project&apos;s academic and development needs.
        </p>
        <CommandBar />
        <ModelModeBar />
        <div className="engineering-grid">
          <div className="column">
            <A2CPanel />
            <PPOStrip />
          </div>
          <div className="centre-column">
            <CoordinationBar />
            <MetricsRow />
          </div>
          <div className="column">
            <DQNPanel />
            <EventTimeline />
          </div>
        </div>
      </details>
    </main>
  );
}

function friendlyError(message: string): string {
  if (/scenario/i.test(message)) return 'Please choose a different scenario and try again.';
  if (/not running|paused/i.test(message)) return 'Start the simulation first.';
  return 'Please try again in a moment.';
}
