import { describe, expect, it } from 'vitest';

import { capabilityReads } from './comparisonRead';
import type { EvalComparison, ExperimentResult } from './types';

/**
 * Insights reads (R11 §23) are built only from measured comparison aggregates
 * (MASTER_PROMPT §84): a difference smaller than the combined confidence interval is
 * "about the same", a regression is reported as worse, and capabilities that were not
 * part of the run are omitted rather than guessed.
 */

function cell(mean: number, ci: number, imp: number | null) {
  return { mean, ci_half_width: ci, improvement_pct_vs_baseline: imp };
}

function comparison(metrics: EvalComparison['metrics']): EvalComparison {
  return { scenario: 's', baseline: 'fixed_time', seeds: [1, 2, 3], n_episodes: 3, metrics };
}

function result(controller: ExperimentResult['controller'], label: string): ExperimentResult {
  return {
    label,
    controller,
    scenario: 's',
    model_version: null,
    checkpoint: null,
    registry_id: null,
    model_mode: 'latest',
    seeds: [1, 2, 3],
    aggregates: {},
    episodes: [],
  };
}

describe('capabilityReads', () => {
  it('reports a clear emergency improvement as better', () => {
    const cmp = comparison({
      'emergency.emergency_delay_s': {
        lower_is_better: true,
        values: {
          fixed_time: cell(18, 1, null),
          'a2c a2c-v1.4-dev': cell(12, 1, 33.3),
        },
      },
    });
    const reads = capabilityReads(cmp, [
      result('fixed_time', 'fixed_time'),
      result('a2c', 'a2c a2c-v1.4-dev'),
    ]);
    expect(reads).toHaveLength(1);
    expect(reads[0].agent).toBe('a2c');
    expect(reads[0].verdict).toBe('better');
    expect(reads[0].metrics[0].text).toContain('33% better');
  });

  it('calls a within-noise difference about the same', () => {
    const cmp = comparison({
      'traffic.avg_waiting_s': {
        lower_is_better: true,
        values: {
          fixed_time: cell(30, 3, null),
          'dqn dqn-v1.4-dev': cell(29, 3, 3.3),
        },
      },
    });
    const reads = capabilityReads(cmp, [
      result('fixed_time', 'fixed_time'),
      result('dqn', 'dqn dqn-v1.4-dev'),
    ]);
    expect(reads[0].verdict).toBe('similar');
    expect(reads[0].metrics[0].text).toContain('no measurable difference');
  });

  it('reports a regression honestly as worse', () => {
    const cmp = comparison({
      'traffic.avg_queue': {
        lower_is_better: true,
        values: {
          fixed_time: cell(4, 0.2, null),
          'ppo ppo-v1.4-dev': cell(6, 0.2, -50),
        },
      },
    });
    const reads = capabilityReads(cmp, [
      result('fixed_time', 'fixed_time'),
      result('ppo', 'ppo ppo-v1.4-dev'),
    ]);
    expect(reads[0].verdict).toBe('worse');
    expect(reads[0].metrics[0].text).toContain('50% worse');
  });

  it('omits capabilities that were not part of the comparison', () => {
    const cmp = comparison({
      'emergency.emergency_delay_s': {
        lower_is_better: true,
        values: { fixed_time: cell(18, 1, null), 'a2c untrained': cell(12, 1, 33.3) },
      },
    });
    const reads = capabilityReads(cmp, [
      result('fixed_time', 'fixed_time'),
      result('a2c', 'a2c untrained'),
    ]);
    expect(reads.map((r) => r.agent)).toEqual(['a2c']);
  });
});
