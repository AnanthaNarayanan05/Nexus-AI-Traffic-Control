import { describe, expect, it } from 'vitest';

import {
  ACTIVE_AGENTS,
  AGENT_LABEL,
  AGENT_OBJECTIVE,
  AGENT_OWNER,
  clock,
  int,
  NO_DATA,
  num,
  pct,
  signed,
  titleise,
} from './format';

/**
 * These lock the one rule that matters for the display layer: a value the backend did
 * not produce renders as `NO_DATA`, never as 0, NaN or a fabricated number
 * (MASTER_PROMPT sections 84, 98, 114).
 */

const ABSENT = [null, undefined, NaN, Infinity, -Infinity] as const;

describe('num', () => {
  it('formats finite numbers to the requested precision', () => {
    expect(num(3.14159, 2)).toBe('3.14');
    expect(num(10)).toBe('10.0');
    expect(num(-0.5, 3)).toBe('-0.500');
  });
  it('returns NO_DATA for every absent value', () => {
    for (const v of ABSENT) expect(num(v)).toBe(NO_DATA);
  });
});

describe('int', () => {
  it('rounds and adds thousands separators', () => {
    expect(int(1234.6)).toBe('1,235');
    expect(int(0)).toBe('0');
  });
  it('returns NO_DATA for every absent value', () => {
    for (const v of ABSENT) expect(int(v)).toBe(NO_DATA);
  });
});

describe('signed', () => {
  it('always shows an explicit sign', () => {
    expect(signed(2)).toBe('+2.00');
    expect(signed(-2)).toBe('-2.00');
    expect(signed(0)).toBe('+0.00');
  });
  it('returns NO_DATA for every absent value', () => {
    for (const v of ABSENT) expect(signed(v)).toBe(NO_DATA);
  });
});

describe('pct', () => {
  it('scales to a percentage', () => {
    expect(pct(0.5)).toBe('50%');
    expect(pct(0.1234, 1)).toBe('12.3%');
  });
  it('returns NO_DATA for every absent value', () => {
    for (const v of ABSENT) expect(pct(v)).toBe(NO_DATA);
  });
});

describe('clock', () => {
  it('formats mm:ss and h:mm:ss', () => {
    expect(clock(0)).toBe('00:00');
    expect(clock(65)).toBe('01:05');
    expect(clock(3661)).toBe('1:01:01');
  });
  it('floors negative time to zero', () => {
    expect(clock(-5)).toBe('00:00');
  });
  it('returns NO_DATA for every absent value', () => {
    for (const v of ABSENT) expect(clock(v)).toBe(NO_DATA);
  });
});

describe('titleise', () => {
  it('turns snake_case into Title Case', () => {
    expect(titleise('emergency_override')).toBe('Emergency Override');
    expect(titleise('max_green')).toBe('Max Green');
  });
});

describe('agent identity maps', () => {
  it('names all three algorithms', () => {
    expect(AGENT_LABEL).toEqual({ a2c: 'A2C', dqn: 'DQN', ppo: 'PPO' });
  });
  it('keeps each objective attached to its owner (PPT source of truth)', () => {
    expect(AGENT_OWNER).toEqual({
      a2c: 'Anantha Narayanan A',
      dqn: 'Shaun Joseph Sabu',
      ppo: 'Delna Liz Denny',
    });
    expect(AGENT_OBJECTIVE.a2c).toMatch(/emergency/i);
    expect(AGENT_OBJECTIVE.dqn).toMatch(/emission/i);
    expect(AGENT_OBJECTIVE.ppo).toMatch(/congestion/i);
  });
  it('runs the three active agents — A2C, DQN and PPO (R10)', () => {
    expect([...ACTIVE_AGENTS]).toEqual(['a2c', 'dqn', 'ppo']);
    expect(ACTIVE_AGENTS).toContain('ppo');
    expect(AGENT_LABEL.ppo).toBe('PPO');
  });
});
