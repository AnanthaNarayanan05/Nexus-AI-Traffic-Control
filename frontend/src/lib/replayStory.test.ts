import { describe, expect, it } from 'vitest';

import { buildStory } from './replayStory';
import type { EventMessage, ReplayDetail, ReplayFrame } from './types';

/**
 * Event Replay's story is built only from real captured data (R11 §24, MASTER_PROMPT
 * §84): emergency incidents and signal changes from the decision timeline, safety and
 * violation beats from the event log. These lock that shape.
 */

function frame(t: number, over: Partial<ReplayFrame['state_summary']> = {}): ReplayFrame {
  return {
    id: `f${t}`,
    t,
    step: t,
    state_summary: {
      sim_time: t,
      phase: 'NS',
      served_phase: 'NS',
      phase_elapsed_s: 0,
      total_vehicles: 0,
      total_queue: 0,
      queues: {},
      emergency_active: false,
      emergency_approach: null,
      throughput_vph: 0,
      violations_total: 0,
      ...over,
    },
    recommendations: {},
    coordination: {
      candidate_phase: 'NS',
      winner: 'dqn',
      basis: 'ladder_winner',
      ladder_trace: [],
      scores: [],
      recommendations: [],
    },
    safety: { approved: true, command: {} as never, original: 'NS', action_taken: 'APPLIED', violated_rules: [], reason: '' },
    rewards: {},
    reward_breakdowns: {},
    metrics: {} as never,
    applied_phase: (over.served_phase as ReplayFrame['applied_phase']) ?? 'NS',
  };
}

function ev(t: number, category: EventMessage['category'], description: string): EventMessage {
  return { id: `e${t}`, t, wall_t: t, category, severity: 'info', description, meta: {} };
}

function replay(timeline: ReplayFrame[], events: EventMessage[]): ReplayDetail {
  return {
    id: 'r1',
    label: 'r1',
    created_at: '2026-01-01T00:00:00Z',
    scenario_id: 's',
    scenario_name: 'Test',
    seed: 0,
    mode: 'AI',
    model_modes: {},
    config_digest: 'x',
    sim_duration_s: timeline.at(-1)?.t ?? 0,
    decision_count: timeline.length,
    episode_complete: true,
    timeline,
    events,
    episode_metrics: null,
  };
}

describe('buildStory', () => {
  it('turns one emergency into detected → priority → cleared', () => {
    const tl = [
      frame(0, { served_phase: 'NS' }),
      frame(10, { emergency_active: true, emergency_approach: 'E', served_phase: 'NS' }),
      frame(20, { emergency_active: true, emergency_approach: 'E', served_phase: 'EW' }),
      frame(40, { emergency_active: false, served_phase: 'EW' }),
    ];
    const beats = buildStory(replay(tl, [ev(0, 'SYSTEM', 'Scenario loaded: Test')]));
    const headlines = beats.map((b) => b.headline);
    expect(headlines).toContain('Scenario started');
    expect(headlines).toContain('Emergency vehicle detected');
    expect(headlines).toContain('Emergency priority activated');
    expect(headlines).toContain('Path cleared');
    const detected = beats.find((b) => b.headline === 'Emergency vehicle detected');
    expect(detected?.detail).toMatch(/East/);
  });

  it('rewrites safety and violation events into plain language, drops AI chatter', () => {
    const beats = buildStory(
      replay(
        [frame(0), frame(30)],
        [
          ev(5, 'AI', 'DQN -> NS (min green hold); applied NS'),
          ev(10, 'SAFETY', 'BLOCKED_HOLD: direct flip is unsafe'),
          ev(15, 'VIOLATION', 'Red Light - W approach'),
        ],
      ),
    );
    const headlines = beats.map((b) => b.headline);
    expect(headlines).toContain('Safety held the signal');
    expect(headlines).toContain('Red-light violation');
    expect(headlines).not.toContain('DQN -> NS (min green hold); applied NS');
  });

  it('collapses a very emergency-dense run instead of emitting a beat per detection', () => {
    const tl: ReplayFrame[] = [frame(0)];
    for (let i = 0; i < 60; i++) {
      const base = 10 + i * 20;
      tl.push(frame(base, { emergency_active: true, emergency_approach: 'N', served_phase: 'NS' }));
      tl.push(frame(base + 5, { emergency_active: true, emergency_approach: 'N', served_phase: 'EW' }));
      tl.push(frame(base + 10, { emergency_active: false, served_phase: 'EW' }));
    }
    const beats = buildStory(replay(tl, []));
    expect(beats.length).toBeLessThanOrEqual(70);
  });
});
