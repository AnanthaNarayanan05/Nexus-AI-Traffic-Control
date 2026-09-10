import { useMemo, useState } from 'react';

import { ApiError, api } from '../lib/api';
import type { Route } from '../lib/hashRoute';
import type { ScenarioConfig, ScenarioDifficulty } from '../lib/types';
import { socket } from '../lib/ws';
import { useSimStore } from '../store';

/**
 * Guided custom-scenario builder a customer meets (R11 §21). Plain-language choices
 * map to a valid `ScenarioConfig`; the full technical editor stays available behind
 * the "Advanced scenario editor" disclosure in ScenariosView (§51). No control here
 * touches the safety layer — it is authoritative and has no scenario-level switch
 * (MASTER_PROMPT §113).
 */

type BusyLevel = 'light' | 'moderate' | 'heavy' | 'very_heavy';
type Bias = 'balanced' | 'ns' | 'ew';
type Emergencies = 'none' | 'occasional' | 'frequent';
type RedLight = 'normal' | 'elevated';
type Weather = 'clear' | 'rain' | 'fog';
type Length = 'short' | 'standard' | 'long';

const BUSY: Record<
  BusyLevel,
  { label: string; vph: number; difficulty: ScenarioDifficulty; note: string }
> = {
  light: { label: 'Light', vph: 900, difficulty: 'easy', note: 'quiet, free-flowing traffic' },
  moderate: { label: 'Moderate', vph: 1500, difficulty: 'moderate', note: 'steady city traffic' },
  heavy: { label: 'Heavy', vph: 2200, difficulty: 'hard', note: 'rush-hour pressure' },
  very_heavy: { label: 'Very heavy', vph: 3000, difficulty: 'extreme', note: 'near-gridlock demand' },
};

const BIAS: Record<Bias, { label: string; weights: Record<string, number>; note: string }> = {
  balanced: {
    label: 'Balanced',
    weights: { N: 0.25, E: 0.25, S: 0.25, W: 0.25 },
    note: 'similar demand from every direction',
  },
  ns: {
    label: 'North–South',
    weights: { N: 0.35, S: 0.35, E: 0.15, W: 0.15 },
    note: 'the north–south road carries most of the traffic',
  },
  ew: {
    label: 'East–West',
    weights: { N: 0.15, S: 0.15, E: 0.35, W: 0.35 },
    note: 'the east–west road carries most of the traffic',
  },
};

const EMERGENCIES: Record<Emergencies, { label: string; perMin: number; note: string }> = {
  none: { label: 'None', perMin: 0, note: 'no emergency vehicles' },
  occasional: { label: 'Occasional', perMin: 0.3, note: 'an emergency vehicle every few minutes' },
  frequent: { label: 'Frequent', perMin: 0.8, note: 'close to one emergency vehicle a minute' },
};

const RED_LIGHT: Record<RedLight, { label: string; scale: number; note: string }> = {
  normal: { label: 'Normal', scale: 1, note: 'a typical rate of red-light running' },
  elevated: { label: 'Elevated', scale: 2, note: 'drivers push the lights more often' },
};

const WEATHER: Record<Weather, string> = { clear: 'Clear', rain: 'Rain', fog: 'Fog' };

const LENGTH: Record<Length, { label: string; seconds: number; phrase: string }> = {
  short: { label: 'Short · 10 min', seconds: 600, phrase: '10 minutes of simulated time' },
  standard: { label: 'Standard · 30 min', seconds: 1800, phrase: '30 minutes of simulated time' },
  long: { label: 'Long · 60 min', seconds: 3600, phrase: '60 minutes of simulated time' },
};

function slugify(text: string): string {
  return (
    text
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 58) || 'custom-scenario'
  );
}

function Seg<T extends string>({
  label,
  help,
  value,
  options,
  onChange,
}: {
  label: string;
  help: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <div className="settings-row">
      <div className="settings-label">
        <span className="settings-name">{label}</span>
        <span className="settings-help">{help}</span>
      </div>
      <div className="settings-control seg" role="group" aria-label={label}>
        {options.map((o) => (
          <button
            key={o.value}
            type="button"
            className={o.value === value ? 'seg-btn active' : 'seg-btn'}
            aria-pressed={o.value === value}
            onClick={() => onChange(o.value)}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export function CustomScenarioForm({ go }: { go: (r: Route) => void }) {
  const online = useSimStore((s) => s.connection === 'open');
  const setScenarios = useSimStore((s) => s.setScenarios);

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [busy, setBusy] = useState<BusyLevel>('moderate');
  const [bias, setBias] = useState<Bias>('balanced');
  const [emergencies, setEmergencies] = useState<Emergencies>('occasional');
  const [redLight, setRedLight] = useState<RedLight>('normal');
  const [weather, setWeather] = useState<Weather>('clear');
  const [length, setLength] = useState<Length>('standard');

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<{ id: string; name: string } | null>(null);
  const [startingNow, setStartingNow] = useState(false);

  const config = useMemo<Omit<ScenarioConfig, 'id'>>(() => {
    const trimmedName = name.trim() || 'Custom scenario';
    return {
      name: trimmedName,
      description:
        description.trim() ||
        `${BUSY[busy].label} traffic — ${BIAS[bias].note}, ${EMERGENCIES[emergencies].note}.`,
      objective: '',
      ai_focus: '',
      difficulty: BUSY[busy].difficulty,
      demand: {
        weights: { ...BIAS[bias].weights },
        arrivals_vph: BUSY[busy].vph,
        turn_split: { left: 0.2, through: 0.6, right: 0.2 },
      },
      scheduled_changes: [],
      emergency_probability_per_min: EMERGENCIES[emergencies].perMin,
      violation_probability_scale: RED_LIGHT[redLight].scale,
      accident_probability_per_min: 0,
      blocked_lanes: [],
      weather,
      time_of_day: 'day',
      duration_s: LENGTH[length].seconds,
      seed: 42,
    };
  }, [name, description, busy, bias, emergencies, redLight, weather, length]);

  const preview = useMemo(() => {
    const parts = [
      `About ${BUSY[busy].vph.toLocaleString()} vehicles per hour, ${BIAS[bias].note}.`,
      emergencies === 'none'
        ? 'No emergency vehicles.'
        : `Emergency vehicles: ${EMERGENCIES[emergencies].note}.`,
    ];
    if (redLight === 'elevated') parts.push('Drivers run red lights more often than usual.');
    if (weather !== 'clear') parts.push(`${WEATHER[weather]} conditions.`);
    parts.push(`Runs for ${LENGTH[length].phrase}.`);
    return parts.join(' ');
  }, [busy, bias, emergencies, redLight, weather, length]);

  const save = async () => {
    setSaving(true);
    setError(null);
    const base = slugify(name);
    for (let attempt = 0; attempt < 6; attempt++) {
      const id = attempt === 0 ? base : `${base}-${attempt + 1}`;
      try {
        const created = await api.createScenario({ ...config, id });
        const list = await api.scenarios();
        setScenarios(list.scenarios);
        setSaved({ id: created.id, name: created.name });
        setSaving(false);
        return;
      } catch (err) {
        if (err instanceof ApiError && err.status === 409) continue;
        setError(
          'Could not save this scenario. Please adjust your choices and try again.',
        );
        setSaving(false);
        return;
      }
    }
    setError('Could not find an available name — try a different scenario name.');
    setSaving(false);
  };

  const startNow = () => {
    if (!saved || !online || startingNow) return;
    setStartingNow(true);
    socket.command('set_mode', { mode: 'AI' });
    window.setTimeout(() => socket.command('load_scenario', { id: saved.id }), 120);
    window.setTimeout(() => socket.command('start'), 300);
    window.setTimeout(() => go('live'), 360);
  };

  return (
    <div className="scn-guided">
      <div className="settings-group">
        <h2>Name it</h2>
        <div className="settings-row scn-guided-text">
          <label className="settings-label" htmlFor="scn-name">
            <span className="settings-name">Scenario name</span>
            <span className="settings-help">Shown on the scenario card.</span>
          </label>
          <input
            id="scn-name"
            type="text"
            value={name}
            maxLength={80}
            placeholder="e.g. Evening rush from the east"
            onChange={(e) => {
              setName(e.target.value);
              setSaved(null);
            }}
          />
        </div>
        <div className="settings-row scn-guided-text">
          <label className="settings-label" htmlFor="scn-desc">
            <span className="settings-name">Description</span>
            <span className="settings-help">Optional — a line about what this scenario is.</span>
          </label>
          <input
            id="scn-desc"
            type="text"
            value={description}
            maxLength={160}
            placeholder="Optional"
            onChange={(e) => {
              setDescription(e.target.value);
              setSaved(null);
            }}
          />
        </div>
      </div>

      <div className="settings-group">
        <h2>Traffic</h2>
        <Seg
          label="How busy is it?"
          help={BUSY[busy].note}
          value={busy}
          onChange={(v) => {
            setBusy(v);
            setSaved(null);
          }}
          options={(Object.keys(BUSY) as BusyLevel[]).map((k) => ({ value: k, label: BUSY[k].label }))}
        />
        <Seg
          label="Busier direction?"
          help={BIAS[bias].note}
          value={bias}
          onChange={(v) => {
            setBias(v);
            setSaved(null);
          }}
          options={(Object.keys(BIAS) as Bias[]).map((k) => ({ value: k, label: BIAS[k].label }))}
        />
      </div>

      <div className="settings-group">
        <h2>Events &amp; conditions</h2>
        <Seg
          label="Emergency vehicles"
          help={EMERGENCIES[emergencies].note}
          value={emergencies}
          onChange={(v) => {
            setEmergencies(v);
            setSaved(null);
          }}
          options={(Object.keys(EMERGENCIES) as Emergencies[]).map((k) => ({
            value: k,
            label: EMERGENCIES[k].label,
          }))}
        />
        <Seg
          label="Red-light running"
          help={RED_LIGHT[redLight].note}
          value={redLight}
          onChange={(v) => {
            setRedLight(v);
            setSaved(null);
          }}
          options={(Object.keys(RED_LIGHT) as RedLight[]).map((k) => ({
            value: k,
            label: RED_LIGHT[k].label,
          }))}
        />
        <Seg
          label="Weather"
          help="Affects how cautiously vehicles drive."
          value={weather}
          onChange={(v) => {
            setWeather(v);
            setSaved(null);
          }}
          options={(Object.keys(WEATHER) as Weather[]).map((k) => ({ value: k, label: WEATHER[k] }))}
        />
        <Seg
          label="How long?"
          help="How much simulated time the scenario covers."
          value={length}
          onChange={(v) => {
            setLength(v);
            setSaved(null);
          }}
          options={(Object.keys(LENGTH) as Length[]).map((k) => ({ value: k, label: LENGTH[k].label }))}
        />
      </div>

      <div className="scn-guided-preview">
        <span className="scn-guided-preview-label">Preview</span>
        <p>{preview}</p>
      </div>

      {error ? <p className="cmp-run-error">{error}</p> : null}

      {saved ? (
        <div className="scn-guided-saved">
          <p>
            Saved <strong>{saved.name}</strong>. It is now in your scenario list.
          </p>
          <div className="scn-guided-actions">
            <button
              className="btn-cta primary"
              type="button"
              onClick={startNow}
              disabled={!online || startingNow}
            >
              {startingNow ? 'Starting…' : 'Start it now'}
            </button>
            <button className="btn-cta ghost" type="button" onClick={() => setSaved(null)}>
              Make another
            </button>
          </div>
        </div>
      ) : (
        <div className="scn-guided-actions">
          <button className="btn-cta primary" type="button" onClick={save} disabled={saving}>
            {saving ? 'Saving…' : 'Save scenario'}
          </button>
        </div>
      )}

      <p className="settings-safety">
        The authoritative safety layer always runs. No scenario can turn it off or weaken
        it.
      </p>
    </div>
  );
}
