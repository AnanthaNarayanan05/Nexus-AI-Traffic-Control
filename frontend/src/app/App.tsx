import { useEffect } from 'react';

import { A2CPanel } from '../components/A2CPanel';
import { CommandBar } from '../components/CommandBar';
import { CoordinationBar } from '../components/CoordinationBar';
import { DQNPanel } from '../components/DQNPanel';
import { EventTimeline } from '../components/EventTimeline';
import { MetricsRow } from '../components/MetricsRow';
import { PPOStrip } from '../components/PPOStrip';
import { SimulationStage } from '../components/SimulationStage';
import { api } from '../lib/api';
import { useSimStore } from '../store';

export function App() {
  const setScenarios = useSimStore((s) => s.setScenarios);

  // Scenario list is static per server process; fetched once over REST rather than
  // streamed.
  useEffect(() => {
    let cancelled = false;
    api
      .scenarios()
      .then((r) => {
        if (!cancelled) setScenarios(r.scenarios);
      })
      .catch(() => {
        /* the command bar shows the socket state; a failed list just leaves it empty */
      });
    return () => {
      cancelled = true;
    };
  }, [setScenarios]);

  return (
    <div className="app">
      <CommandBar />

      <main className="dashboard">
        <div className="column">
          <A2CPanel />
          <PPOStrip />
        </div>

        <div className="centre-column">
          <SimulationStage />
          <CoordinationBar />
          <MetricsRow />
        </div>

        <div className="column">
          <DQNPanel />
          <EventTimeline />
        </div>
      </main>
    </div>
  );
}
