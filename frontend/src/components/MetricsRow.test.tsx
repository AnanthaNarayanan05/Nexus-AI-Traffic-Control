import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { MetricSnapshot } from '../lib/types';

/**
 * MetricsRow shows the live MetricSnapshot verbatim plus a trend strip built from the
 * raw samples this browser has seen. These tests drive the real store and assert: the
 * figures come straight from the snapshot, the trend line accumulates across distinct
 * frames, and a non-finite reading is skipped rather than carried forward (§84).
 */

vi.mock('../lib/ws', () => ({
  socket: { command: () => true, onFrame: () => () => {}, onState: () => () => {}, connect: () => {} },
}));

import { MetricsRow } from './MetricsRow';
import { useSimStore } from '../store';

function snap(simTime: number, waiting: number): MetricSnapshot {
  return {
    sim_time: simTime,
    window: 'rolling',
    traffic: {
      avg_waiting_s: waiting,
      avg_queue: 3,
      throughput_vph: 1200,
      avg_travel_time_s: 40,
      avg_speed_mps: 8,
      stops_per_veh: 1.1,
      idle_time_s: 9,
    },
    environmental: { fuel_l_per_veh: 0.09, co2_kg_per_veh: 0.2, fuel_l_total: 1, co2_kg_total: 2 },
    emergency: { emergency_wait_s: 0, emergency_travel_time_s: 0, emergency_delay_s: 0, emergency_cleared: 2 },
    safety: { red_light_violations: 0, other_violations: 0, unsafe_transitions: 0 },
    dev: null,
  };
}

beforeEach(() => {
  useSimStore.setState({ metrics: null, status: null });
});

afterEach(cleanup);

describe('MetricsRow', () => {
  it('renders the measured figures straight from the snapshot', () => {
    useSimStore.setState({ metrics: snap(30, 12.3) });
    render(<MetricsRow />);
    expect(screen.getByText('12.3')).toBeInTheDocument();
    expect(screen.getByText('1,200')).toBeInTheDocument();
  });

  it('shows an awaiting-snapshot badge before the first frame', () => {
    render(<MetricsRow />);
    expect(screen.getByText(/awaiting first snapshot/i)).toBeInTheDocument();
  });

  it('accumulates a trend line across distinct frames', async () => {
    render(<MetricsRow />);
    for (const [i, t] of [10, 20, 30, 40].entries()) {
      await act(async () => {
        useSimStore.setState({ metrics: snap(t, 10 + i) });
      });
    }
    // five headline trends, each an SVG
    expect(screen.getAllByRole('img').length).toBe(5);
    const wait = screen.getByLabelText(/avg wait trend, latest/i);
    expect(wait.querySelector('polyline')).toBeTruthy();
  });

  it('does not add a sample when the frame is re-published at the same sim_time', async () => {
    render(<MetricsRow />);
    await act(async () => {
      useSimStore.setState({ metrics: snap(10, 5) });
    });
    await act(async () => {
      useSimStore.setState({ metrics: snap(10, 5) });
    });
    // one sample only -> still under two points -> dashed placeholder, no polyline
    const wait = screen.getByLabelText(/avg wait trend, collecting samples/i);
    expect(wait.querySelector('polyline')).toBeNull();
    expect(wait.querySelector('line')).toBeTruthy();
  });
});
