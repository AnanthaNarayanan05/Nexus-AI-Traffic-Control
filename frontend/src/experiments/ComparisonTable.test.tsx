import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import type { EvalComparison, ExperimentResult } from '../lib/types';
import { ComparisonTable } from './ComparisonTable';

/**
 * These tests pin the honesty rules of the comparison table (MASTER_PROMPT §16):
 *  - the baseline column is always rendered;
 *  - a metric is only flagged green when it moved the *better* way for its direction;
 *  - a delta inside the combined CI is called "within noise", not an improvement;
 *  - a null % (baseline ~0) degrades to the absolute delta with no fabricated ratio.
 */

const comparison: EvalComparison = {
  scenario: 'normal',
  baseline: 'fixed_time',
  seeds: [1, 2],
  n_episodes: 2,
  metrics: {
    'traffic.avg_waiting_s': {
      lower_is_better: true,
      values: {
        fixed_time: { mean: 40, ci_half_width: 2, improvement_pct_vs_baseline: null },
        'a2c untrained': { mean: 25, ci_half_width: 2, improvement_pct_vs_baseline: 37.5 },
      },
    },
    'traffic.throughput_vph': {
      lower_is_better: false,
      values: {
        fixed_time: { mean: 500, ci_half_width: 50, improvement_pct_vs_baseline: null },
        'a2c untrained': { mean: 505, ci_half_width: 50, improvement_pct_vs_baseline: 1 },
      },
    },
    'safety.red_light_violations': {
      lower_is_better: true,
      values: {
        fixed_time: { mean: 0, ci_half_width: 0, improvement_pct_vs_baseline: null },
        'a2c untrained': { mean: 1, ci_half_width: 0.5, improvement_pct_vs_baseline: null },
      },
    },
  },
};

const results: ExperimentResult[] = [
  {
    label: 'fixed_time',
    controller: 'fixed_time',
    scenario: 'normal',
    model_version: null,
    checkpoint: null,
    registry_id: null,
    model_mode: 'fixed_time',
    seeds: [1, 2],
    aggregates: {},
    episodes: [],
  },
  {
    label: 'a2c untrained',
    controller: 'a2c',
    scenario: 'normal',
    model_version: 'untrained',
    checkpoint: null,
    registry_id: null,
    model_mode: 'untrained',
    seeds: [1, 2],
    aggregates: {},
    episodes: [],
  },
];

afterEach(cleanup);

describe('ComparisonTable', () => {
  it('always shows the baseline column with its absolute values', () => {
    render(<ComparisonTable comparison={comparison} results={results} />);
    expect(screen.getAllByText('Fixed-Time').length).toBeGreaterThan(0);
    expect(screen.getByText('40.0 ± 2.0')).toBeInTheDocument();
    expect(screen.getByText(/A2C.*untrained/)).toBeInTheDocument();
  });

  it('marks a genuine directional improvement green with its %', () => {
    render(<ComparisonTable comparison={comparison} results={results} />);
    const delta = screen.getByText(/\+37\.5%/);
    expect(delta.className).toContain('cmp-delta');
    expect(delta.className).toContain('up');
    expect(delta.textContent).toContain('−15.0'); // absolute change shown too
  });

  it('flags a change inside the combined CI as noise, not a win', () => {
    render(<ComparisonTable comparison={comparison} results={results} />);
    const deltaSpan = screen
      .getAllByText(/within noise/)
      .find((el) => el.classList.contains('cmp-delta'));
    expect(deltaSpan).toBeDefined();
    expect(deltaSpan?.className).toContain('flat');
    expect(deltaSpan?.className).not.toContain('up');
    // throughput is a coin-flip here, so the winner column says tie
    expect(screen.getByText('≈ tie')).toBeInTheDocument();
  });

  it('degrades to the absolute delta when the baseline is ~0 (no fake ratio)', () => {
    render(<ComparisonTable comparison={comparison} results={results} />);
    const cell = screen.getByText('+1.00');
    expect(cell.textContent).not.toContain('%');
    expect(cell.textContent).not.toContain('NaN');
  });

  it('shows a per-metric direction indicator', () => {
    render(<ComparisonTable comparison={comparison} results={results} />);
    expect(screen.getAllByText('↓', { exact: true }).length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText('↑', { exact: true }).length).toBeGreaterThanOrEqual(1);
  });

  it('renders the scenario and seed provenance', () => {
    render(<ComparisonTable comparison={comparison} results={results} />);
    expect(screen.getByText(/seeds \[1, 2\]/)).toBeInTheDocument();
  });
});
