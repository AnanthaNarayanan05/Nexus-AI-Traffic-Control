import { useEffect } from 'react';

import { ExperimentLab } from '../experiments/ExperimentLab';
import { HelpView } from '../help/HelpView';
import { Home } from '../home/Home';
import { InsightsView } from '../insights/InsightsView';
import { InspectorLab } from '../inspectors/InspectorLab';
import { api } from '../lib/api';
import type { Route } from '../lib/hashRoute';
import { useHashRoute } from '../lib/hashRoute';
import { LiveView } from '../live/LiveView';
import { PresentationMode } from '../present/PresentationMode';
import { ReplayLab } from '../replay/ReplayLab';
import { ReportsView } from '../reports/ReportsView';
import { ScenariosView } from '../scenarios/ScenariosView';
import { useSimStore } from '../store';
import { TrainingLab } from '../training/TrainingLab';
import { AppFooter } from './AppFooter';
import { AppHeader } from './AppHeader';

// The visible wordmark lives in the header; each view still needs a real <h1> for
// assistive-tech landmark/heading navigation. Most views render their own <h1>; the
// engineering surfaces below get an sr-only one here.
const ADVANCED_TITLE: Partial<Record<Route, string>> = {
  training: 'NEXUS — AI training',
  experiments: 'NEXUS — experiment lab',
  replay: 'NEXUS — replay lab',
  inspect: 'NEXUS — inspectors',
};

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
        /* the header shows the connection state; a failed list just leaves it empty */
      });
    return () => {
      cancelled = true;
    };
  }, [setScenarios]);

  // Presentation mode is a full-screen takeover: no header, no footer (R11 §27).
  if (route === 'present') {
    return <PresentationMode />;
  }

  return (
    <div className="app-shell">
      <AppHeader route={route} go={go} />
      {ADVANCED_TITLE[route] ? <h1 className="sr-only">{ADVANCED_TITLE[route]}</h1> : null}

      <div className="app-body">
        {route === '' ? (
          <Home go={go} />
        ) : route === 'live' ? (
          <LiveView />
        ) : route === 'scenarios' ? (
          <ScenariosView go={go} />
        ) : route === 'insights' ? (
          <InsightsView />
        ) : route === 'reports' ? (
          <ReportsView go={go} />
        ) : route === 'help' ? (
          <HelpView go={go} />
        ) : route === 'training' ? (
          <TrainingLab />
        ) : route === 'experiments' ? (
          <ExperimentLab />
        ) : route === 'replay' ? (
          <ReplayLab />
        ) : route === 'inspect' ? (
          <InspectorLab />
        ) : (
          <Home go={go} />
        )}
      </div>

      <AppFooter go={go} />
    </div>
  );
}
