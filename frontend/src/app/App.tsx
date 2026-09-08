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
import { InspectorLab } from '../inspectors/InspectorLab';
import { api } from '../lib/api';
import type { Route } from '../lib/hashRoute';
import { useHashRoute } from '../lib/hashRoute';
import { PresentationMode } from '../present/PresentationMode';
import { ReplayLab } from '../replay/ReplayLab';
import { ScenarioLab } from '../scenarios/ScenarioLab';
import { useSimStore } from '../store';
import { TrainingLab } from '../training/TrainingLab';

// The one visible wordmark ("NEXUS") lives in the command bar as styled spans; each
// view still needs a real <h1> for assistive-tech landmark/heading navigation.
const VIEW_TITLE: Record<Exclude<Route, 'present'>, string> = {
  '': 'NEXUS — live traffic control',
  training: 'NEXUS — training lab',
  experiments: 'NEXUS — experiment lab',
  scenarios: 'NEXUS — scenario lab',
  replay: 'NEXUS — replay lab',
  inspect: 'NEXUS — inspectors',
};

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

  // Presentation mode is a full-screen takeover: no command bar, no view tabs (§60-63).
  if (route === 'present') {
    return <PresentationMode />;
  }

  return (
    <div className="app">
      <h1 className="sr-only">{VIEW_TITLE[route]}</h1>
      <CommandBar />

      <nav className="view-tabs" aria-label="View">
        <button
          className={route === '' ? 'active' : ''}
          aria-current={route === '' ? 'page' : undefined}
          onClick={() => go('')}
        >
          Live Control
        </button>
        <button
          className={route === 'training' ? 'active' : ''}
          aria-current={route === 'training' ? 'page' : undefined}
          onClick={() => go('training')}
        >
          Training Lab
        </button>
        <button
          className={route === 'experiments' ? 'active' : ''}
          aria-current={route === 'experiments' ? 'page' : undefined}
          onClick={() => go('experiments')}
        >
          Experiment Lab
        </button>
        <button
          className={route === 'scenarios' ? 'active' : ''}
          aria-current={route === 'scenarios' ? 'page' : undefined}
          onClick={() => go('scenarios')}
        >
          Scenario Lab
        </button>
        <button
          className={route === 'replay' ? 'active' : ''}
          aria-current={route === 'replay' ? 'page' : undefined}
          onClick={() => go('replay')}
        >
          Replay
        </button>
        <button
          className={route === 'inspect' ? 'active' : ''}
          aria-current={route === 'inspect' ? 'page' : undefined}
          onClick={() => go('inspect')}
        >
          Inspectors
        </button>
        {/* Presentation mode replaces this whole chrome, so this tab is never "active" here. */}
        <button onClick={() => go('present')}>Presentation</button>
      </nav>

      {route === 'training' ? (
        <TrainingLab />
      ) : route === 'experiments' ? (
        <ExperimentLab />
      ) : route === 'scenarios' ? (
        <ScenarioLab />
      ) : route === 'replay' ? (
        <ReplayLab />
      ) : route === 'inspect' ? (
        <InspectorLab />
      ) : (
        <Dashboard />
      )}
    </div>
  );
}
