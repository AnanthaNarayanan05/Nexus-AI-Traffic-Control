import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { EventMessage } from '../lib/types';

/**
 * The timeline is a thin view over the two stores: it renders the events verbatim,
 * newest first, filters them by category, and surfaces a server-side command rejection
 * exactly as it arrived. These tests drive the real stores.
 */

vi.mock('../lib/ws', () => ({
  socket: { command: () => true, onFrame: () => () => {}, onState: () => () => {}, connect: () => {} },
}));

import { EventTimeline } from './EventTimeline';
import { ALL_CATEGORIES, useEventStore, useSimStore } from '../store';

let seq = 0;
function ev(over: Partial<EventMessage> = {}): EventMessage {
  seq += 1;
  return {
    id: `e${seq}`,
    t: 10,
    wall_t: 0,
    category: 'TRAFFIC',
    severity: 'info',
    description: 'a thing happened',
    meta: {},
    ...over,
  };
}

beforeEach(() => {
  useEventStore.setState({ events: [], filters: new Set(ALL_CATEGORIES) });
  useSimStore.setState({ lastError: null });
});

afterEach(cleanup);

describe('EventTimeline', () => {
  it('renders the events in store order (newest first)', () => {
    useEventStore.setState({
      events: [ev({ description: 'newer', t: 20 }), ev({ description: 'older', t: 10 })],
    });
    render(<EventTimeline />);
    const descs = screen.getAllByText(/newer|older/).map((el) => el.textContent);
    expect(descs).toEqual(['newer', 'older']);
  });

  it('hides a category when its filter chip is toggled off', () => {
    useEventStore.setState({
      events: [
        ev({ description: 'a safety note', category: 'SAFETY' }),
        ev({ description: 'a traffic note', category: 'TRAFFIC' }),
      ],
    });
    render(<EventTimeline />);
    fireEvent.click(screen.getByRole('button', { name: 'SAFETY' }));
    expect(screen.queryByText('a safety note')).not.toBeInTheDocument();
    expect(screen.getByText('a traffic note')).toBeInTheDocument();
  });

  it('reports the visible / total count', () => {
    useEventStore.setState({
      events: [ev({ category: 'SAFETY' }), ev({ category: 'TRAFFIC' }), ev({ category: 'TRAFFIC' })],
    });
    render(<EventTimeline />);
    expect(screen.getByText('3/3')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'SAFETY' }));
    expect(screen.getByText('2/3')).toBeInTheDocument();
  });

  it('Clear empties the timeline', () => {
    useEventStore.setState({ events: [ev(), ev()] });
    render(<EventTimeline />);
    fireEvent.click(screen.getByRole('button', { name: 'Clear' }));
    expect(screen.getByText(/no events yet/i)).toBeInTheDocument();
  });

  it('surfaces a server error verbatim and dismisses it on click', () => {
    useSimStore.setState({
      lastError: { code: 'BAD_COMMAND', message: 'unknown action "frobnicate"', at: 1 },
    });
    render(<EventTimeline />);
    expect(screen.getByText('BAD_COMMAND')).toBeInTheDocument();
    expect(screen.getByText(/frobnicate/)).toBeInTheDocument();
    fireEvent.click(screen.getByText('BAD_COMMAND'));
    expect(screen.queryByText('BAD_COMMAND')).not.toBeInTheDocument();
  });

  it('says "no events yet" before anything has happened', () => {
    render(<EventTimeline />);
    expect(screen.getByText(/no events yet/i)).toBeInTheDocument();
  });

  it('distinguishes "all filtered out" from "nothing yet"', () => {
    useEventStore.setState({ events: [ev({ category: 'TRAFFIC' })] });
    render(<EventTimeline />);
    for (const c of ALL_CATEGORIES) {
      fireEvent.click(screen.getByRole('button', { name: c }));
    }
    expect(screen.getByText(/all categories filtered out/i)).toBeInTheDocument();
  });
});
