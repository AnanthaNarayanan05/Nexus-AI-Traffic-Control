import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const hoisted = vi.hoisted(() => ({ command: vi.fn(() => true) }));
const { command } = hoisted;
vi.mock('../lib/ws', () => ({
  socket: {
    onFrame: () => () => {},
    onState: () => () => {},
    connect: () => {},
    command: hoisted.command,
  },
}));

import type { SimStatus } from '../lib/types';
import { useSimStore } from '../store';
import { ModelModeBar } from './ModelModeBar';

function setStatus(over: Partial<SimStatus>): void {
  useSimStore.setState({
    connection: 'open',
    status: {
      model_modes: { a2c: 'untrained', dqn: 'untrained', ppo: 'untrained' },
      model_sources: { a2c: null, dqn: null, ppo: null },
      ...over,
    } as unknown as SimStatus,
  });
}

afterEach(() => {
  cleanup();
  command.mockClear();
});

describe('ModelModeBar', () => {
  it('reflects the honest per-agent mode from status', () => {
    setStatus({
      model_modes: { a2c: 'trained', dqn: 'untrained', ppo: 'untrained' },
      model_sources: { a2c: 'a2c-run-ep200', dqn: null, ppo: null },
    });
    render(<ModelModeBar />);
    expect(screen.getByText('a2c-run-ep200')).toBeInTheDocument();
    // two agents still untrained -> the honest badge shows twice
    expect(screen.getAllByText('UNTRAINED').length).toBeGreaterThanOrEqual(2);
  });

  it('sends a set_model command when a mode button is clicked', () => {
    setStatus({});
    render(<ModelModeBar />);
    const trainedButtons = screen.getAllByRole('button', { name: 'TRAINED' });
    fireEvent.click(trainedButtons[0]);
    expect(command).toHaveBeenCalledWith('set_model', { agent: 'a2c', mode: 'trained' });
  });
});
