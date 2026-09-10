import { beforeEach, describe, expect, it } from 'vitest';

import { DEFAULT_SETTINGS, useSettings } from './settings';

/**
 * Customer preferences (R11 §30): presentation-only, persisted to one localStorage
 * key, and quietly falling back to defaults when a stored value is missing or junk.
 */

beforeEach(() => {
  localStorage.clear();
  useSettings.setState({ ...DEFAULT_SETTINGS });
});

describe('useSettings', () => {
  it('persists an update and reloads it', () => {
    useSettings.getState().update('defaultSpeed', 4);
    useSettings.getState().update('motion', 'reduced');
    const raw = JSON.parse(localStorage.getItem('nexus.settings.v1') ?? '{}');
    expect(raw.defaultSpeed).toBe(4);
    expect(raw.motion).toBe('reduced');
  });

  it('reset clears storage and returns to defaults', () => {
    useSettings.getState().update('sound', true);
    useSettings.getState().reset();
    expect(localStorage.getItem('nexus.settings.v1')).toBeNull();
    expect(useSettings.getState().sound).toBe(false);
  });

  it('only stores the known preference keys', () => {
    useSettings.getState().update('contrast', 'high');
    const raw = JSON.parse(localStorage.getItem('nexus.settings.v1') ?? '{}');
    expect(Object.keys(raw).sort()).toEqual(
      ['contrast', 'defaultSpeed', 'motion', 'notifications', 'sound'].sort(),
    );
  });
});
