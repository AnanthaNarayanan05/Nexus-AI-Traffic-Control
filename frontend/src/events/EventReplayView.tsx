import { useEffect, useMemo, useRef, useState } from 'react';

import { api } from '../lib/api';
import {
  AGENT_LABEL,
  AGENT_PRODUCT_NAME,
  APPROACH_NAME,
  SAFETY_PRODUCT_STATUS,
  clock,
  coordinationBasisText,
  signalActionText,
} from '../lib/format';
import { navigate, navigateWith, routeParam, useHashRoute } from '../lib/hashRoute';
import { buildStory, type StoryBeat } from '../lib/replayStory';
import type { AgentKey, ReplayDetail, ReplayFrame, ReplaySummary } from '../lib/types';

/**
 * Event Replay (R11 §24): a cinematic "what happened?" walk-through of a captured
 * run. The timeline is a short list of plain-language milestones — an emergency
 * detected, priority activated, the signal moved, the path cleared — that plays
 * back one beat at a time. The full engineering decision frame for any moment sits
 * behind "Decision details", and the raw winner / safety / recommendation data
 * behind a further "technical details" toggle. Every beat is real captured data
 * (MASTER_PROMPT §84); nothing here is generated for effect.
 */

const STEP_MS = 1700;

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function axisWord(phase: string): string {
  if (phase === 'NS' || phase === 'N' || phase === 'S') return 'North–South';
  if (phase === 'EW' || phase === 'E' || phase === 'W') return 'East–West';
  if (phase === 'YELLOW') return 'changing';
  if (phase === 'ALL_RED') return 'all held';
  return phase;
}

export function EventReplayView() {
  const [route] = useHashRoute();
  const [runs, setRuns] = useState<ReplaySummary[] | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ReplayDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [showTech, setShowTech] = useState(false);

  const listRef = useRef<HTMLOListElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .replays(50)
      .then((r) => {
        if (cancelled) return;
        setRuns(r.replays);
        const fromUrl = routeParam();
        const initial =
          (fromUrl && r.replays.some((x) => x.id === fromUrl) ? fromUrl : r.replays[0]?.id) ?? null;
        setSelectedId(initial);
      })
      .catch(() => !cancelled && setError('Captured runs aren’t available right now.'));
    return () => {
      cancelled = true;
    };
  }, []);

  // Navigating in from a Reports card while this view is already mounted.
  useEffect(() => {
    if (route !== 'events') return;
    const p = routeParam();
    if (p) setSelectedId(p);
  }, [route]);

  useEffect(() => {
    if (!selectedId) return;
    let cancelled = false;
    setLoadingDetail(true);
    setDetail(null);
    setPlaying(false);
    setActive(0);
    setShowTech(false);
    setError(null);
    api
      .replay(selectedId)
      .then((d) => {
        if (cancelled) return;
        setDetail(d);
        setLoadingDetail(false);
      })
      .catch(() => {
        if (cancelled) return;
        setError('That run could not be opened.');
        setLoadingDetail(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  const beats = useMemo<StoryBeat[]>(() => (detail ? buildStory(detail) : []), [detail]);

  useEffect(() => {
    if (!playing || beats.length === 0) return;
    const id = window.setInterval(() => {
      setActive((i) => {
        if (i >= beats.length - 1) {
          setPlaying(false);
          return i;
        }
        return i + 1;
      });
    }, STEP_MS);
    return () => window.clearInterval(id);
  }, [playing, beats.length]);

  useEffect(() => {
    const el = listRef.current?.querySelector<HTMLElement>(`[data-beat="${active}"]`);
    el?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [active]);

  const activeBeat = beats.length ? beats[Math.min(active, beats.length - 1)] : null;

  function selectRun(id: string) {
    navigateWith('events', id);
    setSelectedId(id);
  }

  return (
    <main className="page events">
      <header className="page-head">
        <h1>Event replay</h1>
        <p>
          Step through what happened during a captured run — every emergency, signal
          change and safety check, in the order it occurred.
        </p>
      </header>

      {error ? <p className="empty-note">{error}</p> : null}

      {runs !== null && runs.length === 0 ? (
        <p className="empty-note">
          No runs have been captured yet. Open{' '}
          <button className="link-btn" onClick={() => navigate('live')}>
            Live
          </button>{' '}
          and let a scenario play through to capture one.
        </p>
      ) : null}

      {runs && runs.length > 0 ? (
        <div className="events-pick">
          <label htmlFor="events-run">Run</label>
          <select
            id="events-run"
            value={selectedId ?? ''}
            onChange={(e) => selectRun(e.target.value)}
          >
            {runs.map((r) => (
              <option key={r.id} value={r.id}>
                {r.scenario_name} — {formatDate(r.created_at)}
              </option>
            ))}
          </select>
        </div>
      ) : null}

      {loadingDetail ? <p className="empty-note">Loading run…</p> : null}

      {detail && !loadingDetail ? (
        <div className="events-body">
          <section className="events-timeline-wrap" aria-label="Timeline">
            <div className="events-transport">
              <button
                className="btn-cta sm primary"
                onClick={() => {
                  if (active >= beats.length - 1) setActive(0);
                  setPlaying((p) => !p);
                }}
                disabled={beats.length === 0}
              >
                {playing ? 'Pause' : active >= beats.length - 1 ? 'Replay' : 'Play'}
              </button>
              <button
                className="btn-cta sm ghost"
                onClick={() => {
                  setPlaying(false);
                  setActive(0);
                }}
                disabled={beats.length === 0}
              >
                Restart
              </button>
              <input
                className="events-scrub"
                type="range"
                min={0}
                max={Math.max(0, beats.length - 1)}
                value={Math.min(active, Math.max(0, beats.length - 1))}
                onChange={(e) => {
                  setPlaying(false);
                  setActive(Number(e.target.value));
                }}
                aria-label="Scrub timeline"
                disabled={beats.length === 0}
              />
              <span className="events-count">
                {beats.length === 0 ? '—' : `${Math.min(active + 1, beats.length)} / ${beats.length}`}
              </span>
            </div>

            {beats.length === 0 ? (
              <p className="empty-note">This run is too short to build a timeline.</p>
            ) : (
              <ol className="events-timeline" ref={listRef}>
                {beats.map((b, i) => (
                  <li
                    key={b.id}
                    data-beat={i}
                    className={
                      'events-beat tone-' +
                      b.tone +
                      (i === active ? ' current' : '') +
                      (i < active ? ' past' : '')
                    }
                  >
                    <button
                      className="events-beat-hit"
                      onClick={() => {
                        setPlaying(false);
                        setActive(i);
                      }}
                      aria-current={i === active ? 'true' : undefined}
                    >
                      <span className="events-beat-time">{clock(b.t)}</span>
                      <span className="events-beat-dot" aria-hidden="true" />
                      <span className="events-beat-text">
                        <span className="events-beat-headline">{b.headline}</span>
                        {b.detail ? <span className="events-beat-detail">{b.detail}</span> : null}
                      </span>
                    </button>
                  </li>
                ))}
              </ol>
            )}
          </section>

          <aside className="events-detail" aria-live="polite">
            {activeBeat ? (
              <BeatDetail beat={activeBeat} showTech={showTech} onToggleTech={() => setShowTech((v) => !v)} />
            ) : (
              <p className="panel-sub">Select a moment on the timeline.</p>
            )}
          </aside>
        </div>
      ) : null}
    </main>
  );
}

function BeatDetail({
  beat,
  showTech,
  onToggleTech,
}: {
  beat: StoryBeat;
  showTech: boolean;
  onToggleTech: () => void;
}) {
  const frame = beat.frame;

  return (
    <div className="events-beat-panel">
      <p className="panel-kicker">At {clock(beat.t)}</p>
      <h2 className="events-detail-headline">{beat.headline}</h2>
      {beat.detail ? <p className="events-detail-lead">{beat.detail}</p> : null}

      {frame ? <FrameStory frame={frame} /> : (
        <p className="panel-sub">This moment happened before NEXUS made its first signal decision.</p>
      )}

      {frame ? (
        <>
          <button className="link-btn" onClick={onToggleTech} aria-expanded={showTech}>
            {showTech ? 'Hide technical details' : 'Show technical details'}
          </button>
          {showTech ? <FrameTechnical frame={frame} /> : null}
        </>
      ) : null}
    </div>
  );
}

function FrameStory({ frame }: { frame: ReplayFrame }) {
  const winner = frame.coordination.winner;
  const winnerName =
    winner === 'a2c' || winner === 'dqn' || winner === 'ppo'
      ? AGENT_PRODUCT_NAME[winner as AgentKey]
      : 'Safe default';
  const safety = SAFETY_PRODUCT_STATUS[frame.safety.action_taken] ?? SAFETY_PRODUCT_STATUS.APPLIED;
  const s = frame.state_summary;

  return (
    <dl className="events-frame">
      <div>
        <dt>NEXUS decision</dt>
        <dd>
          {winnerName} recommendation selected. {coordinationBasisText(winner)}
        </dd>
      </div>
      <div>
        <dt>Safety check</dt>
        <dd className={'tone-' + safety.tone}>
          {safety.label}. {safety.detail}
        </dd>
      </div>
      <div>
        <dt>Signal action</dt>
        <dd>{signalActionText(frame.applied_phase)}</dd>
      </div>
      <div>
        <dt>Intersection then</dt>
        <dd>
          {s.total_vehicles} vehicles, {s.total_queue} waiting · {axisWord(s.served_phase)} traffic moving
          {s.emergency_active && s.emergency_approach
            ? ` · emergency on the ${APPROACH_NAME[s.emergency_approach] ?? s.emergency_approach} approach`
            : ''}
        </dd>
      </div>
    </dl>
  );
}

function FrameTechnical({ frame }: { frame: ReplayFrame }) {
  const recs = Object.entries(frame.recommendations) as [string, ReplayFrame['recommendations'][string]][];
  return (
    <div className="events-tech">
      <p>
        <span className="events-tech-k">Winner</span> {frame.coordination.winner} · basis{' '}
        {frame.coordination.basis}
      </p>
      <p>
        <span className="events-tech-k">Candidate phase</span> {frame.coordination.candidate_phase} ·
        applied {frame.applied_phase}
      </p>
      <p>
        <span className="events-tech-k">Safety</span> {frame.safety.action_taken}
        {frame.safety.violated_rules.length ? ` · ${frame.safety.violated_rules.join(', ')}` : ''}
      </p>
      {recs.length ? (
        <ul className="events-tech-recs">
          {recs.map(([k, r]) => (
            <li key={k}>
              {AGENT_LABEL[k as AgentKey] ?? k.toUpperCase()} → {r.target_phase} (score{' '}
              {Number.isFinite(r.score) ? r.score.toFixed(2) : '—'})
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
