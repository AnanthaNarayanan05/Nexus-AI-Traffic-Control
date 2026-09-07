/**
 * Minimal hash router. The project has no react-router dependency and only needs a
 * handful of top-level views (the live dashboard, the Training Lab, the Experiment
 * Lab), so a `location.hash` lookup with a subscription is enough.
 *
 * Routes are the bare hash without the `#`: '' (dashboard), 'training', 'experiments',
 * 'scenarios', 'replay'.
 */

import { useCallback, useSyncExternalStore } from 'react';

export type Route = '' | 'training' | 'experiments' | 'scenarios' | 'replay';

const ROUTES: Route[] = ['', 'training', 'experiments', 'scenarios', 'replay'];

function parse(hash: string): Route {
  const clean = hash.replace(/^#\/?/, '').split(/[?/]/)[0] as Route;
  return ROUTES.includes(clean) ? clean : '';
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener('hashchange', onChange);
  return () => window.removeEventListener('hashchange', onChange);
}

function snapshot(): Route {
  return parse(window.location.hash);
}

export function navigate(route: Route): void {
  const next = route ? `#/${route}` : '#/';
  if (window.location.hash !== next) window.location.hash = next;
}

export function useHashRoute(): [Route, (route: Route) => void] {
  const route = useSyncExternalStore(subscribe, snapshot, () => '' as Route);
  const go = useCallback((next: Route) => navigate(next), []);
  return [route, go];
}
