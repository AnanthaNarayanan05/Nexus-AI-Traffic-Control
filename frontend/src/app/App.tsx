import { useEffect } from 'react';

import { A2CPanel } from '../components/A2CPanel';
import { CommandBar } from '../components/CommandBar';
import { CoordinationBar } from '../components/CoordinationBar';
import { DQNPanel } from '../components/DQNPanel';
import { EventTimeline } from '../components/EventTimeline';
import { MetricsRow } from '../components/MetricsRow';
import { ModelModeBar } from '../components/ModelModeBar';
import { SimulationStage } from '../components/SimulationStage';
import { ExperimentLab } from '../experiments/ExperimentLab';
import { api } from '../lib/api';
import { useHashRoute } from '../lib/hashRoute';
import { useSimStore } from '../store';
import { TrainingLab } from '../training/TrainingLab';

function Dashboard() {
  return (
    <main className="dashboard">
      <div className="column">
        <ModelModeBar />
        <A2CPanel />
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
  );
}

export function App() {
  const setScenarios = useSimStore((s) => s.setScenarios);
  const [route, go] = useHashRoute();

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

      <nav className="view-tabs" aria-label="View">
        <button className={route === '' ? 'active' : ''} onClick={() => go('')}>
          Live Control
        </button>
        <button className={route === 'training' ? 'active' : ''} onClick={() => go('training')}>
          Training Lab
        </button>
        <button
          className={route === 'experiments' ? 'active' : ''}
          onClick={() => go('experiments')}
        >
          Experiment Lab
        </button>
      </nav>

      {route === 'training' ? (
        <TrainingLab />
      ) : route === 'experiments' ? (
        <ExperimentLab />
      ) : (
        <Dashboard />
      )}
    </div>
  );
}
