/**
 * Turns a captured run (`ReplayDetail`) into a short, plain-language sequence of
 * milestones — the "what happened?" story for Event Replay (R11 §24).
 *
 * The story is incident-driven, built from real captured data (MASTER_PROMPT §84):
 *   - the decision timeline (`replay.timeline`) drives the spine — an emergency
 *     becoming active, priority being applied, the path clearing, and the ordinary
 *     signal changes in between;
 *   - safety interventions and red-light violations come from `replay.events`,
 *     reworded for a customer;
 *   - the scenario start and run completion come from the SYSTEM events.
 * Nothing here is generated for effect, and the noisy per-decision "min green hold"
 * chatter never becomes a beat.
 */

import { APPROACH_NAME } from './format';
import type { EventMessage, Phase, ReplayDetail, ReplayFrame } from './types';

export type BeatTone = 'normal' | 'emergency' | 'safety' | 'violation' | 'system';

export interface StoryBeat {
  id: string;
  t: number;
  headline: string;
  detail?: string;
  tone: BeatTone;
  /** The decision frame in effect at this moment, for "decision details". */
  frame: ReplayFrame | null;
}

function servedAxis(phase: Phase | string): 'North–South' | 'East–West' | null {
  if (phase === 'NS' || phase === 'N' || phase === 'S') return 'North–South';
  if (phase === 'EW' || phase === 'E' || phase === 'W') return 'East–West';
  return null;
}

function approachName(code: string | null | undefined): string | null {
  if (!code) return null;
  return APPROACH_NAME[code.toUpperCase()] ?? code;
}

function frameAt(timeline: ReplayFrame[], t: number): ReplayFrame | null {
  if (timeline.length === 0) return null;
  let best = timeline[0];
  for (const f of timeline) {
    if (f.t <= t + 1e-6) best = f;
    else break;
  }
  return best;
}

/** Scenario-start / run-complete / safety / violation beats from the event log. */
function eventBeats(replay: ReplayDetail): StoryBeat[] {
  const out: StoryBeat[] = [];
  for (const e of replay.events) {
    const r = rewriteEvent(e);
    if (!r) continue;
    out.push({
      id: e.id,
      t: e.t,
      headline: r.headline,
      detail: r.detail,
      tone: r.tone,
      frame: frameAt(replay.timeline, e.t),
    });
  }
  return out;
}

function rewriteEvent(e: EventMessage): { headline: string; detail?: string; tone: BeatTone } | null {
  const d = e.description;

  if (e.category === 'SYSTEM') {
    if (/^scenario loaded/i.test(d))
      return { headline: 'Scenario started', detail: d.replace(/^Scenario loaded:\s*/i, ''), tone: 'system' };
    if (/^episode complete/i.test(d)) return { headline: 'Run complete', tone: 'system' };
    return null;
  }

  if (e.category === 'SAFETY') {
    if (/^EMERGENCY_TIMEOUT/i.test(d))
      return {
        headline: 'Safety ended a long phase',
        detail: 'An emergency phase reached its safe time limit, so NEXUS moved the signal on.',
        tone: 'safety',
      };
    if (/^REWRITTEN_TRANSITION/i.test(d))
      return {
        headline: 'Safety adjusted a signal change',
        detail: 'NEXUS altered the transition so the intersection cleared safely.',
        tone: 'safety',
      };
    if (/^BLOCKED_HOLD/i.test(d))
      return {
        headline: 'Safety held the signal',
        detail: 'Changing the signal at that moment would not have been safe.',
        tone: 'safety',
      };
    if (/^FORCED_CHANGE/i.test(d))
      return {
        headline: 'Safety forced a change',
        detail: 'NEXUS changed the signal to resolve an unsafe situation.',
        tone: 'safety',
      };
    return { headline: 'Safety intervention', tone: 'safety' };
  }

  if (e.category === 'VIOLATION') {
    const m = d.match(/^(.*?)\s*-\s*([NESW])\s+approach/i);
    return {
      headline: 'Red-light violation',
      detail: m
        ? `${m[1].trim()} on the ${approachName(m[2])} approach.`
        : d.replace(/\b([NESW])\b/g, (_x, c: string) => APPROACH_NAME[c] ?? c),
      tone: 'violation',
    };
  }

  return null; // AI / TRAFFIC events are not milestones on their own
}

interface Incident {
  from: string | null;
  startT: number;
  startFrame: ReplayFrame;
  goT: number | null;
  goAxis: string | null;
  goFrame: ReplayFrame | null;
  endT: number;
  endFrame: ReplayFrame;
}

/**
 * Emergency incidents + ordinary signal changes, from the decision timeline. Below
 * `expandLimit` incidents each becomes three beats (detected → priority → cleared);
 * above it, one combined beat per incident, so a long emergency-stress run still
 * reads as a story rather than a wall.
 */
function timelineBeats(timeline: ReplayFrame[], expandLimit = 16): StoryBeat[] {
  const signals: StoryBeat[] = [];
  const incidents: Incident[] = [];
  let cur: Incident | null = null;
  let prevAxis: string | null = null;

  for (const f of timeline) {
    const s = f.state_summary;
    const active = s.emergency_active;

    if (active && !cur) {
      cur = {
        from: approachName(s.emergency_approach),
        startT: f.t,
        startFrame: f,
        goT: null,
        goAxis: null,
        goFrame: null,
        endT: f.t,
        endFrame: f,
      };
    } else if (!active && cur) {
      cur.endT = f.t;
      cur.endFrame = f;
      incidents.push(cur);
      cur = null;
    }

    const axis = servedAxis(s.served_phase ?? f.applied_phase);
    if (axis && axis !== prevAxis) {
      if (prevAxis !== null) {
        if (cur && cur.goT === null) {
          cur.goT = f.t;
          cur.goAxis = axis;
          cur.goFrame = f;
        } else if (!cur) {
          signals.push({
            id: `sig-${f.id}`,
            t: f.t,
            headline: 'Signal changed',
            detail: `${axis} traffic released.`,
            tone: 'normal',
            frame: f,
          });
        }
      }
      prevAxis = axis;
    }
  }
  if (cur) {
    cur.endT = cur.endFrame.t;
    incidents.push(cur);
  }

  const emergency: StoryBeat[] = [];
  const expand = incidents.length <= expandLimit;
  for (const inc of incidents) {
    const fromText = inc.from ? `Approaching from the ${inc.from}.` : 'Approaching the intersection.';
    if (expand) {
      emergency.push({
        id: `em-in-${inc.startFrame.id}`,
        t: inc.startT,
        headline: 'Emergency vehicle detected',
        detail: fromText,
        tone: 'emergency',
        frame: inc.startFrame,
      });
      if (inc.goT !== null && inc.goFrame) {
        emergency.push({
          id: `em-go-${inc.goFrame.id}`,
          t: inc.goT,
          headline: 'Emergency priority activated',
          detail: `${inc.goAxis} traffic released to clear the path.`,
          tone: 'emergency',
          frame: inc.goFrame,
        });
      }
      emergency.push({
        id: `em-out-${inc.endFrame.id}`,
        t: inc.endT,
        headline: 'Path cleared',
        detail: 'The emergency vehicle is through; normal traffic resumes.',
        tone: 'emergency',
        frame: inc.endFrame,
      });
    } else {
      const held = Math.max(0, Math.round(inc.endT - inc.startT));
      emergency.push({
        id: `em-${inc.startFrame.id}`,
        t: inc.startT,
        headline: inc.from ? `Emergency vehicle from the ${inc.from}` : 'Emergency vehicle',
        detail: `Detected, priority applied, path cleared${held ? ` in ${held}s` : ''}.`,
        tone: 'emergency',
        frame: inc.goFrame ?? inc.startFrame,
      });
    }
  }

  return [...signals, ...emergency];
}

/** Keep every non-routine beat; thin the plain "Signal changed" ones to fit. */
function thin(beats: StoryBeat[], maxBeats: number): StoryBeat[] {
  if (beats.length <= maxBeats) return beats;
  const important = beats.filter((b) => b.tone !== 'normal');
  const routine = beats.filter((b) => b.tone === 'normal');
  if (important.length >= maxBeats) return important;
  const keepEvery = Math.ceil(routine.length / (maxBeats - important.length));
  const kept = routine.filter((_b, i) => i % keepEvery === 0);
  return [...important, ...kept].sort((a, b) => a.t - b.t);
}

export function buildStory(replay: ReplayDetail, maxBeats = 70): StoryBeat[] {
  const merged = [...eventBeats(replay), ...timelineBeats(replay.timeline)].sort((a, b) => a.t - b.t);

  // Collapse immediate repeats of the same headline (+ detail).
  const deduped: StoryBeat[] = [];
  let lastKey = '';
  for (const b of merged) {
    const key = `${b.headline}|${b.detail ?? ''}`;
    if (key === lastKey) continue;
    lastKey = key;
    deduped.push(b);
  }

  return thin(deduped, maxBeats);
}
