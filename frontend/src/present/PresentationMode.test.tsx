import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * Presentation mode (R9 P4, §60-63) is a reduced-chrome shell around the live loop. These
 * tests stub the socket and the heavy child panels and assert: the three flagship demos
 * are listed, launching one fires the real command sequence (AI mode → scenario at the
 * pinned seed → start), the "what to watch" brief appears, the number keys and Esc work,
 * and the launchers are disabled while the backend is offline. No simulation runs here.
 */

const hoisted = vi.hoisted(() => ({ command: vi.fn(() => true) }));

vi.mock('../lib/ws', () => ({
  socket: {
    command: hoisted.command,
    onFrame: () => () => {},
    onState: () => () => {},
    connect: () => {},
  },
}));
vi.mock('../components/SimulationStage', () => ({
  SimulationStage: () => <div data-testid="sim-stage" />,
}));
vi.mock('../components/MetricsRow', () => ({ MetricsRow: () => <div data-testid="metrics-row" /> }));
vi.mock('../components/CoordinationBar', () => ({
  CoordinationBar: () => <div data-testid="coord-bar" />,
}));

import { PRESENTATION_SEED, PresentationMode } from './PresentationMode';
import { useSimStore } from '../store';

beforeEach(() => {
  hoisted.command.mockClear();
  window.location.hash = '#/present';
  useSimStore.setState({ connection: 'open', status: null });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe('PresentationMode', () => {
  it('lists the three flagship demos', () => {
    render(<PresentationMode />);
    expect(screen.getByRole('button', { name: /Emergency Response Challenge/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Efficiency Challenge/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Mixed Crisis/ })).toBeInTheDocument();
  });

  it('launches a demo as AI mode → scenario at the pinned seed → start', () => {
    vi.useFakeTimers();
    render(<PresentationMode />);

    fireEvent.click(screen.getByRole('button', { name: /Emergency Response Challenge/ }));
    expect(hoisted.command).toHaveBeenCalledWith('set_mode', { mode: 'AI' });

    vi.advanceTimersByTime(400);
    expect(hoisted.command).toHaveBeenCalledWith('load_scenario', {
      id: 'emergency_heavy',
      seed: PRESENTATION_SEED,
    });
    expect(hoisted.command).toHaveBeenCalledWith('start');
  });

  it('shows the "what to watch" brief once a demo is active', () => {
    render(<PresentationMode />);
    fireEvent.click(screen.getByRole('button', { name: /Efficiency Challenge/ }));
    expect(screen.getByText('What to watch')).toBeInTheDocument();
    expect(screen.getByText(/Stops \/ veh trends down/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Restart this demo/ })).toBeInTheDocument();
  });

  it('launches demo 3 on the "3" key and exits on Escape', () => {
    render(<PresentationMode />);

    fireEvent.keyDown(document.body, { key: '3' });
    expect(hoisted.command).toHaveBeenCalledWith('set_mode', { mode: 'AI' });
    // active demo shown in the header
    expect(screen.getByText(/Demo 3 · Mixed Crisis/)).toBeInTheDocument();

    fireEvent.keyDown(document.body, { key: 'Escape' });
    expect(window.location.hash).toBe('#/');
  });

  it('disables the launchers when the backend is offline', () => {
    useSimStore.setState({ connection: 'closed' });
    render(<PresentationMode />);

    expect(screen.getByText('backend offline')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Mixed Crisis/ })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: /Mixed Crisis/ }));
    expect(hoisted.command).not.toHaveBeenCalled();
  });
});
