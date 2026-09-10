import { create } from 'zustand';

/**
 * Customer preferences (R11 §30). These change presentation only — how much the
 * interface animates, contrast, the speed a new run starts at, and whether NEXUS
 * gives an audible / desktop cue when an emergency vehicle is detected. There is
 * deliberately no API base URL, model path, backend toggle or debug flag here.
 *
 * Persistence is a single localStorage key, written by hand: the app has one other
 * zustand store pattern and no persistence middleware, so this stays consistent with
 * it and degrades quietly when storage is unavailable.
 */

export type MotionPref = 'system' | 'full' | 'reduced';
export type ContrastPref = 'normal' | 'high';

export interface Settings {
  motion: MotionPref;
  contrast: ContrastPref;
  /** Speed a freshly connected simulation is set to (×). */
  defaultSpeed: number;
  /** Play a short tone when an emergency vehicle is first detected. */
  sound: boolean;
  /** Show a desktop notification for an emergency while the tab is in the background. */
  notifications: boolean;
}

export const SPEED_OPTIONS = [0.5, 1, 2, 4, 8] as const;

export const DEFAULT_SETTINGS: Settings = {
  motion: 'system',
  contrast: 'normal',
  defaultSpeed: 1,
  sound: false,
  notifications: false,
};

const KEY = 'nexus.settings.v1';
const MOTIONS: MotionPref[] = ['system', 'full', 'reduced'];

function load(): Settings {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return { ...DEFAULT_SETTINGS };
    const p = JSON.parse(raw) as Partial<Settings>;
    return {
      motion: MOTIONS.includes(p.motion as MotionPref) ? (p.motion as MotionPref) : DEFAULT_SETTINGS.motion,
      contrast: p.contrast === 'high' ? 'high' : 'normal',
      defaultSpeed: (SPEED_OPTIONS as readonly number[]).includes(p.defaultSpeed as number)
        ? (p.defaultSpeed as number)
        : DEFAULT_SETTINGS.defaultSpeed,
      sound: p.sound === true,
      notifications: p.notifications === true,
    };
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}

function persist(s: Settings): void {
  try {
    localStorage.setItem(
      KEY,
      JSON.stringify({
        motion: s.motion,
        contrast: s.contrast,
        defaultSpeed: s.defaultSpeed,
        sound: s.sound,
        notifications: s.notifications,
      }),
    );
  } catch {
    /* storage unavailable — the choice just won't survive a reload */
  }
}

interface SettingsStore extends Settings {
  update: <K extends keyof Settings>(key: K, value: Settings[K]) => void;
  reset: () => void;
}

export const useSettings = create<SettingsStore>((set) => ({
  ...load(),
  update: (key, value) =>
    set((s) => {
      const next = { ...s, [key]: value };
      persist(next);
      return { [key]: value } as Partial<SettingsStore>;
    }),
  reset: () => {
    try {
      localStorage.removeItem(KEY);
    } catch {
      /* ignore */
    }
    set({ ...DEFAULT_SETTINGS });
  },
}));
