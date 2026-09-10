/**
 * Minimal hash router. The project has no react-router dependency and only needs a
 * handful of top-level views, so a `location.hash` lookup with a subscription is enough.
 *
 * Routes are the bare hash without the `#`:
 *   ''            the product home page
 *   live          the live traffic-control experience
 *   scenarios     the scenario picker (and custom-scenario builder)
 *   insights      NEXUS vs. traditional signal control
 *   reports       run reports and data export
 *   help          plain-language help
 *   present       full-screen presentation mode
 *
 * The remaining routes are the engineering surfaces. They stay reachable for the
 * project's internal / academic needs (R11 §51) but are not part of the primary
 * customer navigation:
 *   training      per-agent training + model registry
 *   experiments   the raw experiment lab
 *   replay        the raw replay lab
 *   inspect       the low-level inspectors
 */

import { useCallback, useSyncExternalStore } from 'react';

export type Route =
  | ''
  | 'live'
  | 'scenarios'
  | 'insights'
  | 'reports'
  | 'events'
  | 'settings'
  | 'help'
  | 'present'
  | 'training'
  | 'experiments'
  | 'replay'
  | 'inspect';

const ROUTES: Route[] = [
  '',
  'live',
  'scenarios',
  'insights',
  'reports',
  'events',
  'settings',
  'help',
  'present',
  'training',
  'experiments',
  'replay',
  'inspect',
];

/** Routes that make up the primary customer navigation, in order. */
export const PRIMARY_NAV: { route: Route; label: string }[] = [
  { route: '', label: 'Home' },
  { route: 'live', label: 'Live' },
  { route: 'scenarios', label: 'Scenarios' },
  { route: 'insights', label: 'Insights' },
  { route: 'reports', label: 'Reports' },
];

/** Secondary customer destinations reached from the header menu / footer. */
export const SECONDARY_NAV: { route: Route; label: string }[] = [
  { route: 'events', label: 'Event replay' },
  { route: 'settings', label: 'Settings' },
  { route: 'help', label: 'Help' },
];

/** Engineering surfaces — reachable, but kept out of the primary navigation. */
export const ADVANCED_NAV: { route: Route; label: string }[] = [
  { route: 'training', label: 'AI training' },
  { route: 'experiments', label: 'Experiment lab' },
  { route: 'replay', label: 'Replay lab' },
  { route: 'inspect', label: 'Inspectors' },
  { route: 'present', label: 'Presentation mode' },
];

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

/**
 * Navigate to a route with a single path parameter, e.g. `#/events/<replay-id>`.
 * Ids passed here are always server-minted (never user text); encode anyway.
 */
export function navigateWith(route: Route, param: string): void {
  const next = `#/${route}/${encodeURIComponent(param)}`;
  if (window.location.hash !== next) window.location.hash = next;
}

/** The path parameter after the route segment (`#/events/<id>` → `<id>`), or null. */
export function routeParam(): string | null {
  const parts = window.location.hash.replace(/^#\/?/, '').split('?')[0].split('/');
  return parts[1] ? decodeURIComponent(parts[1]) : null;
}

export function useHashRoute(): [Route, (route: Route) => void] {
  const route = useSyncExternalStore(subscribe, snapshot, () => '' as Route);
  const go = useCallback((next: Route) => navigate(next), []);
  return [route, go];
}
