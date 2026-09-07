/**
 * Scenario Lab — browse the eight R9 §8A preset scenarios and build / edit / duplicate /
 * delete custom ones (MASTER_PROMPT §8A, §8B, §35 P2).
 *
 * Presets are read-only (they are code). A custom scenario is the full `ScenarioConfig`
 * blob; every user-facing knob is exposed here, validated by the backend on save, and
 * previewed in plain English before it runs. There is deliberately no control for the
 * safety layer — it is authoritative and has no scenario-level switch (§113).
 */

import { useCallback, useEffect, useMemo, useState } from 'react';

import { Badge, Empty, Panel, SectionLabel } from '../components/common/Primitives';
import { ApiError, api } from '../lib/api';
import { NO_DATA, clock } from '../lib/format';
import type { ScenarioConfig, ScenarioDifficulty, ScenarioSummary } from '../lib/types';
import { useSimStore } from '../store';

const APPROACHES = ['N', 'E', 'S', 'W'] as const;
const DIFFICULTIES: ScenarioDifficulty[] = ['easy', 'moderate', 'hard', 'extreme'];
const WEATHER = ['clear', 'rain', 'fog', 'snow', 'storm'];
const TIME_OF_DAY = ['day', 'night', 'dawn', 'dusk'];
const LANES = [0, 1, 2];

function difficultyTone(d: ScenarioDifficulty): 'good' | 'info' | 'warn' | 'bad' {
  return d === 'easy' ? 'good' : d === 'moderate' ? 'info' : d === 'hard' ? 'warn' : 'bad';
}

function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 64);
}

function blankScenario(): ScenarioConfig {
  return {
    id: '',
    name: '',
    description: '',
    objective: '',
    ai_focus: '',
    difficulty: 'moderate',
    demand: {
      weights: { N: 0.25, E: 0.25, S: 0.25, W: 0.25 },
      arrivals_vph: 1600,
      turn_split: { left: 0.2, through: 0.6, right: 0.2 },
    },
    scheduled_changes: [],
    emergency_probability_per_min: 0,
    violation_probability_scale: 1,
    accident_probability_per_min: 0,
    blocked_lanes: [],
    weather: 'clear',
    time_of_day: 'day',
    duration_s: 3600,
    seed: 42,
  };
}

/* ------------------------------------------------------------------ preview */

function describe(c: ScenarioConfig): string {
  const w = c.demand.weights;
  const total = APPROACHES.reduce((s, a) => s + (Number(w[a]) || 0), 0) || 1;
  const shares = APPROACHES.map((a) => ({ a, pct: ((Number(w[a]) || 0) / total) * 100 }));
  const heaviest = [...shares].sort((x, y) => y.pct - x.pct)[0];
  const lightest = [...shares].sort((x, y) => x.pct - y.pct)[0];
  const balanced = heaviest.pct - lightest.pct < 6;

  const parts: string[] = [];
  parts.push(
    `~${Math.round(c.demand.arrivals_vph).toLocaleString()} veh/h, ` +
      (balanced
        ? 'roughly balanced across all four approaches'
        : `heaviest from ${heaviest.a} (${heaviest.pct.toFixed(0)}%), lightest from ${lightest.a} (${lightest.pct.toFixed(0)}%)`) +
      '.',
  );
  if (c.emergency_probability_per_min > 0)
    parts.push(`Emergency vehicles about ${c.emergency_probability_per_min.toFixed(2)}/min.`);
  if (c.violation_probability_scale !== 1)
    parts.push(`Red-running pressure ×${c.violation_probability_scale.toFixed(2)}.`);
  if (c.accident_probability_per_min > 0)
    parts.push(`Accidents about ${c.accident_probability_per_min.toFixed(2)}/min.`);
  if (c.blocked_lanes.length)
    parts.push(
      `Closed ${c.blocked_lanes.length === 1 ? 'lane' : 'lanes'} ` +
        c.blocked_lanes.map((b) => `${b.approach}${b.lane}`).join(', ') +
        '.',
    );
  if (c.weather !== 'clear' || c.time_of_day !== 'day')
    parts.push(`Conditions: ${c.weather}, ${c.time_of_day}.`);
  if (c.scheduled_changes.length)
    parts.push(
      `${c.scheduled_changes.length} mid-episode demand change` +
        (c.scheduled_changes.length === 1 ? '' : 's') +
        ' at ' +
        c.scheduled_changes.map((s) => clock(s.at_s)).join(', ') +
        '.',
    );
  parts.push(`Episode ${clock(c.duration_s)} long, seed ${c.seed}.`);
  return parts.join(' ');
}

/* ------------------------------------------------------------------ list */

function ScenarioList({
  rows,
  selectedId,
  onSelect,
  onNew,
}: {
  rows: ScenarioSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
}) {
  const presets = rows.filter((r) => r.preset);
  const custom = rows.filter((r) => !r.preset);

  const item = (r: ScenarioSummary) => (
    <button
      key={r.id}
      type="button"
      className={r.id === selectedId ? 'scn-item active' : 'scn-item'}
      onClick={() => onSelect(r.id)}
    >
      <span className="scn-item-head">
        <span className="scn-item-name">{r.name}</span>
        <Badge tone={difficultyTone(r.difficulty)}>{r.difficulty}</Badge>
      </span>
      <span className="scn-item-obj">{r.objective || r.description || NO_DATA}</span>
      {r.ai_focus ? <span className="scn-item-focus">{r.ai_focus}</span> : null}
    </button>
  );

  return (
    <Panel
      title="SCENARIOS"
      accent="var(--accent)"
      sub={`${presets.length} preset · ${custom.length} custom`}
      actions={
        <button className="btn" type="button" onClick={onNew}>
          + New
        </button>
      }
    >
      <SectionLabel>PRESETS · R9 §8A</SectionLabel>
      <div className="scn-list">{presets.map(item)}</div>
      <SectionLabel>CUSTOM</SectionLabel>
      {custom.length === 0 ? (
        <Empty>No custom scenarios yet. “+ New” starts one from the standard defaults.</Empty>
      ) : (
        <div className="scn-list">{custom.map(item)}</div>
      )}
    </Panel>
  );
}

/* ------------------------------------------------------------------ number field */

function NumField({
  label,
  value,
  onChange,
  step = 'any',
  min,
  max,
  suffix,
}: {
  label: string;
  value: number;
  onChange: (n: number) => void;
  step?: string | number;
  min?: number;
  max?: number;
  suffix?: string;
}) {
  return (
    <label>
      <span>
        {label}
        {suffix ? ` (${suffix})` : ''}
      </span>
      <input
        type="number"
        value={Number.isFinite(value) ? value : ''}
        step={step}
        min={min}
        max={max}
        onChange={(e) => onChange(e.target.value === '' ? NaN : Number(e.target.value))}
      />
    </label>
  );
}

/* ------------------------------------------------------------------ editor */

function ScenarioEditor({
  draft,
  isPreset,
  isNew,
  busy,
  error,
  onChange,
  onSave,
  onDuplicate,
  onDelete,
  onLoadIntoSim,
}: {
  draft: ScenarioConfig;
  isPreset: boolean;
  isNew: boolean;
  busy: boolean;
  error: string | null;
  onChange: (next: ScenarioConfig) => void;
  onSave: () => void;
  onDuplicate: () => void;
  onDelete: () => void;
  onLoadIntoSim: () => void;
}) {
  const set = <K extends keyof ScenarioConfig>(key: K, value: ScenarioConfig[K]) =>
    onChange({ ...draft, [key]: value });
  const setDemand = (patch: Partial<ScenarioConfig['demand']>) =>
    onChange({ ...draft, demand: { ...draft.demand, ...patch } });
  const setWeight = (a: string, n: number) =>
    setDemand({ weights: { ...draft.demand.weights, [a]: n } });
  const setTurn = (k: string, n: number) =>
    setDemand({ turn_split: { ...draft.demand.turn_split, [k]: n } });

  const readOnly = isPreset;
  const title = isNew ? 'NEW SCENARIO' : isPreset ? 'PRESET (READ-ONLY)' : 'EDIT SCENARIO';

  return (
    <Panel
      title={title}
      accent={isPreset ? 'var(--text-dim)' : 'var(--accent)'}
      actions={<Badge tone={difficultyTone(draft.difficulty)}>{draft.difficulty}</Badge>}
    >
      <fieldset className="scn-form" disabled={readOnly || busy}>
        <div className="train-form-grid">
          <label>
            <span>Name</span>
            <input
              type="text"
              value={draft.name}
              onChange={(e) => {
                const name = e.target.value;
                onChange({
                  ...draft,
                  name,
                  id: isNew && (draft.id === '' || draft.id === slugify(draft.name))
                    ? slugify(name)
                    : draft.id,
                });
              }}
            />
          </label>
          <label>
            <span>Id (slug)</span>
            <input
              type="text"
              value={draft.id}
              disabled={!isNew}
              onChange={(e) => set('id', slugify(e.target.value))}
            />
          </label>
        </div>

        <label>
          <span>Description</span>
          <input type="text" value={draft.description} onChange={(e) => set('description', e.target.value)} />
        </label>

        <div className="train-form-grid">
          <label>
            <span>Objective (what to watch for)</span>
            <input type="text" value={draft.objective} onChange={(e) => set('objective', e.target.value)} />
          </label>
          <label>
            <span>AI focus</span>
            <input type="text" value={draft.ai_focus} onChange={(e) => set('ai_focus', e.target.value)} />
          </label>
        </div>

        <label>
          <span>Difficulty</span>
          <select
            value={draft.difficulty}
            onChange={(e) => set('difficulty', e.target.value as ScenarioDifficulty)}
          >
            {DIFFICULTIES.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </label>

        <SectionLabel>DEMAND</SectionLabel>
        <div className="train-form-grid">
          <NumField
            label="Arrivals"
            suffix="veh/h"
            value={draft.demand.arrivals_vph}
            step={50}
            min={1}
            onChange={(n) => setDemand({ arrivals_vph: n })}
          />
          <div />
        </div>
        <div className="scn-weights">
          {APPROACHES.map((a) => (
            <NumField
              key={a}
              label={`${a} weight`}
              value={Number(draft.demand.weights[a] ?? 0)}
              step={0.05}
              min={0}
              onChange={(n) => setWeight(a, n)}
            />
          ))}
        </div>
        <div className="scn-weights">
          {(['left', 'through', 'right'] as const).map((k) => (
            <NumField
              key={k}
              label={`Turn ${k}`}
              value={Number(draft.demand.turn_split[k] ?? 0)}
              step={0.05}
              min={0}
              onChange={(n) => setTurn(k, n)}
            />
          ))}
        </div>

        <SectionLabel>EVENTS</SectionLabel>
        <div className="train-form-grid">
          <NumField
            label="Emergency rate"
            suffix="/min"
            value={draft.emergency_probability_per_min}
            step={0.05}
            min={0}
            onChange={(n) => set('emergency_probability_per_min', n)}
          />
          <NumField
            label="Violation pressure"
            suffix="×"
            value={draft.violation_probability_scale}
            step={0.1}
            min={0}
            onChange={(n) => set('violation_probability_scale', n)}
          />
          <NumField
            label="Accident rate"
            suffix="/min"
            value={draft.accident_probability_per_min}
            step={0.05}
            min={0}
            onChange={(n) => set('accident_probability_per_min', n)}
          />
          <div />
        </div>

        <SectionLabel>CLOSED LANES</SectionLabel>
        {draft.blocked_lanes.length === 0 ? (
          <p className="train-form-owner">None — all lanes open.</p>
        ) : (
          <div className="scn-lanes">
            {draft.blocked_lanes.map((b, i) => (
              <div key={i} className="scn-lane-row">
                <select
                  aria-label={`closed lane ${i + 1} approach`}
                  value={b.approach}
                  onChange={(e) => {
                    const next = draft.blocked_lanes.slice();
                    next[i] = { ...b, approach: e.target.value };
                    set('blocked_lanes', next);
                  }}
                >
                  {APPROACHES.map((a) => (
                    <option key={a} value={a}>
                      {a}
                    </option>
                  ))}
                </select>
                <select
                  aria-label={`closed lane ${i + 1} index`}
                  value={b.lane}
                  onChange={(e) => {
                    const next = draft.blocked_lanes.slice();
                    next[i] = { ...b, lane: Number(e.target.value) };
                    set('blocked_lanes', next);
                  }}
                >
                  {LANES.map((l) => (
                    <option key={l} value={l}>
                      lane {l}
                    </option>
                  ))}
                </select>
                <button
                  className="btn"
                  type="button"
                  onClick={() =>
                    set(
                      'blocked_lanes',
                      draft.blocked_lanes.filter((_, j) => j !== i),
                    )
                  }
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
        )}
        {!readOnly && draft.blocked_lanes.length < 8 ? (
          <button
            className="btn"
            type="button"
            onClick={() => set('blocked_lanes', [...draft.blocked_lanes, { approach: 'N', lane: 0 }])}
          >
            + Close a lane
          </button>
        ) : null}

        <SectionLabel>MID-EPISODE DEMAND CHANGES</SectionLabel>
        {draft.scheduled_changes.length === 0 ? (
          <p className="train-form-owner">None — demand is steady for the whole episode.</p>
        ) : (
          <div className="scn-changes">
            {draft.scheduled_changes.map((ch, i) => (
              <div key={i} className="scn-change-row">
                <NumField
                  label={`Change ${i + 1} at`}
                  suffix="s"
                  value={ch.at_s}
                  step={30}
                  min={0}
                  onChange={(n) => {
                    const next = draft.scheduled_changes.slice();
                    next[i] = { ...ch, at_s: n };
                    set('scheduled_changes', next);
                  }}
                />
                <NumField
                  label="then arrivals"
                  suffix="veh/h"
                  value={ch.profile.arrivals_vph}
                  step={50}
                  min={1}
                  onChange={(n) => {
                    const next = draft.scheduled_changes.slice();
                    next[i] = { ...ch, profile: { ...ch.profile, arrivals_vph: n } };
                    set('scheduled_changes', next);
                  }}
                />
                <button
                  className="btn"
                  type="button"
                  onClick={() =>
                    set(
                      'scheduled_changes',
                      draft.scheduled_changes.filter((_, j) => j !== i),
                    )
                  }
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
        )}
        {!readOnly && draft.scheduled_changes.length < 4 ? (
          <button
            className="btn"
            type="button"
            onClick={() =>
              set('scheduled_changes', [
                ...draft.scheduled_changes,
                {
                  at_s: Math.round(draft.duration_s / 2),
                  profile: {
                    weights: { ...draft.demand.weights },
                    arrivals_vph: draft.demand.arrivals_vph,
                    turn_split: { ...draft.demand.turn_split },
                  },
                },
              ])
            }
          >
            + Add a demand change
          </button>
        ) : null}

        <SectionLabel>CONDITIONS</SectionLabel>
        <div className="train-form-grid">
          <label>
            <span>Weather</span>
            <select value={draft.weather} onChange={(e) => set('weather', e.target.value)}>
              {WEATHER.map((w) => (
                <option key={w} value={w}>
                  {w}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Time of day</span>
            <select value={draft.time_of_day} onChange={(e) => set('time_of_day', e.target.value)}>
              {TIME_OF_DAY.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
          <NumField
            label="Episode length"
            suffix="s"
            value={draft.duration_s}
            step={60}
            min={60}
            max={14400}
            onChange={(n) => set('duration_s', n)}
          />
          <NumField
            label="Seed"
            value={draft.seed}
            step={1}
            min={0}
            onChange={(n) => set('seed', Math.round(n))}
          />
        </div>
      </fieldset>

      <SectionLabel>PREVIEW</SectionLabel>
      <p className="scn-preview">
        <strong>
          {draft.name || 'Untitled'} · {draft.difficulty}
        </strong>
        <br />
        {describe(draft)}
      </p>
      {draft.objective ? <p className="scn-preview-obj">Watch for: {draft.objective}</p> : null}

      {error ? <p className="train-form-error">{error}</p> : null}

      <div className="train-form-actions">
        {isPreset ? (
          <button className="btn primary" type="button" onClick={onDuplicate} disabled={busy}>
            Duplicate to edit
          </button>
        ) : (
          <>
            <button className="btn primary" type="button" onClick={onSave} disabled={busy}>
              {busy ? 'Saving…' : isNew ? 'Save scenario' : 'Save changes'}
            </button>
            <button className="btn" type="button" onClick={onDuplicate} disabled={busy || isNew}>
              Duplicate
            </button>
            <button className="btn danger" type="button" onClick={onDelete} disabled={busy || isNew}>
              Delete
            </button>
          </>
        )}
        <button
          className="btn"
          type="button"
          onClick={onLoadIntoSim}
          disabled={busy || isNew}
          title="Reset the live dashboard simulation onto this scenario"
        >
          Load into simulation
        </button>
      </div>
      <p className="panel-sub">
        The authoritative safety layer always runs — no scenario can turn it off. Out-of-range
        values are rejected on save, not silently clamped.
      </p>
    </Panel>
  );
}

/* ------------------------------------------------------------------ page */

export function ScenarioLab() {
  const scenarios = useSimStore((s) => s.scenarios);
  const setScenarios = useSimStore((s) => s.setScenarios);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState<ScenarioConfig | null>(null);
  const [isNew, setIsNew] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const selectedSummary = useMemo(
    () => scenarios.find((s) => s.id === selectedId) ?? null,
    [scenarios, selectedId],
  );
  const isPreset = selectedSummary?.preset ?? false;

  const refreshList = useCallback(async () => {
    const r = await api.scenarios();
    setScenarios(r.scenarios);
    return r.scenarios;
  }, [setScenarios]);

  const loadDraft = useCallback(async (id: string) => {
    setError(null);
    setNotice(null);
    setIsNew(false);
    try {
      const cfg = await api.scenario(id);
      setDraft(cfg);
      setSelectedId(id);
    } catch (err) {
      setError(err instanceof ApiError ? `${err.status} · ${err.message}` : String(err));
    }
  }, []);

  // Pick a sensible first selection once the list arrives.
  useEffect(() => {
    if (selectedId === null && !isNew && scenarios.length) void loadDraft(scenarios[0].id);
  }, [scenarios, selectedId, isNew, loadDraft]);

  const startNew = () => {
    setError(null);
    setNotice(null);
    setIsNew(true);
    setSelectedId(null);
    setDraft(blankScenario());
  };

  const save = async () => {
    if (!draft) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const saved = await api.createScenario(draft);
      await refreshList();
      setIsNew(false);
      setSelectedId(saved.id);
      setDraft(saved);
      setNotice(`Saved “${saved.name}”.`);
    } catch (err) {
      setError(err instanceof ApiError ? `${err.status} · ${err.message}` : String(err));
    } finally {
      setBusy(false);
    }
  };

  const duplicate = async () => {
    if (!draft || !selectedId) return;
    const base = `${selectedId}-copy`;
    const existing = new Set(scenarios.map((s) => s.id));
    let newId = base;
    let n = 2;
    while (existing.has(newId)) newId = `${base}-${n++}`;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const copy = await api.duplicateScenario(selectedId, newId);
      await refreshList();
      setIsNew(false);
      setSelectedId(copy.id);
      setDraft(copy);
      setNotice(`Created “${copy.name}” — editable.`);
    } catch (err) {
      setError(err instanceof ApiError ? `${err.status} · ${err.message}` : String(err));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!selectedId || isPreset) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await api.deleteScenario(selectedId);
      const rows = await refreshList();
      setNotice(`Deleted “${selectedSummary?.name ?? selectedId}”.`);
      setSelectedId(null);
      setDraft(null);
      if (rows.length) void loadDraft(rows[0].id);
    } catch (err) {
      setError(err instanceof ApiError ? `${err.status} · ${err.message}` : String(err));
    } finally {
      setBusy(false);
    }
  };

  const loadIntoSim = async () => {
    if (!selectedId) return;
    setBusy(true);
    setError(null);
    try {
      await api.loadScenario(selectedId);
      setNotice(`Live simulation reset onto “${selectedSummary?.name ?? selectedId}”.`);
    } catch (err) {
      setError(err instanceof ApiError ? `${err.status} · ${err.message}` : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="training-lab">
      <div className="lab-legend">
        <div className="lab-legend-item">
          <SectionLabel>PRESETS</SectionLabel>
          <p>
            The eight R9 §8A scenarios — normal, rush hour, emergency response, unequal demand,
            stop-go efficiency, road blockage, safety/violation, mixed crisis. Read-only; duplicate
            one to start a custom variant.
          </p>
        </div>
        <div className="lab-legend-item">
          <SectionLabel>CUSTOM</SectionLabel>
          <p>
            Every user-facing knob is here — demand, emergencies, violations, closed lanes,
            mid-episode changes, conditions. Saved to the database and available to the Experiment
            Lab and the live dashboard.
          </p>
        </div>
        <div className="lab-legend-item">
          <SectionLabel>SAFETY IS AUTHORITATIVE</SectionLabel>
          <p>
            No scenario can disable or weaken the safety layer. Values outside the allowed range are
            rejected on save with the reason shown, never clamped behind your back.
          </p>
        </div>
      </div>

      {notice ? <p className="scn-notice">{notice}</p> : null}

      <div className="lab-columns">
        <div className="lab-col">
          <ScenarioList
            rows={scenarios}
            selectedId={isNew ? null : selectedId}
            onSelect={loadDraft}
            onNew={startNew}
          />
        </div>
        <div className="lab-col">
          {draft ? (
            <ScenarioEditor
              draft={draft}
              isPreset={isPreset && !isNew}
              isNew={isNew}
              busy={busy}
              error={error}
              onChange={setDraft}
              onSave={save}
              onDuplicate={duplicate}
              onDelete={remove}
              onLoadIntoSim={loadIntoSim}
            />
          ) : (
            <Panel title="SCENARIO" accent="var(--accent)">
              <Empty>Select a scenario on the left, or start a new one.</Empty>
            </Panel>
          )}
        </div>
      </div>
    </main>
  );
}
