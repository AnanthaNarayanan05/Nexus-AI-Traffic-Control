import { useState } from 'react';

import { SPEED_OPTIONS, useSettings } from '../store/settings';

/**
 * Customer preferences (R11 §30). Presentation only — motion, contrast, the speed a
 * run starts at, and the emergency cues. No API base URL, model paths, backend URLs,
 * database paths or debug flags: those never belong on the product surface (R11 §4, §28).
 */
export function SettingsView() {
  const s = useSettings();
  const [notifyNote, setNotifyNote] = useState<string | null>(null);

  async function onToggleNotifications(next: boolean) {
    if (!next) {
      s.update('notifications', false);
      setNotifyNote(null);
      return;
    }
    if (!('Notification' in window)) {
      setNotifyNote('This browser does not support desktop notifications.');
      return;
    }
    let perm = Notification.permission;
    if (perm === 'default') {
      try {
        perm = await Notification.requestPermission();
      } catch {
        perm = Notification.permission;
      }
    }
    if (perm === 'granted') {
      s.update('notifications', true);
      setNotifyNote(null);
    } else {
      s.update('notifications', false);
      setNotifyNote('Notifications are blocked for this site in your browser settings.');
    }
  }

  return (
    <main className="page settings">
      <header className="page-head">
        <h1>Settings</h1>
        <p>Preferences for how NEXUS looks and behaves on this device. They&apos;re saved in this browser.</p>
      </header>

      <section className="settings-group">
        <h2>Appearance</h2>

        <div className="settings-row">
          <div className="settings-label">
            <span className="settings-name">Motion</span>
            <span className="settings-help">How much the interface animates.</span>
          </div>
          <div className="settings-control seg">
            {(
              [
                ['system', 'Match device'],
                ['full', 'Full'],
                ['reduced', 'Reduced'],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                className={s.motion === value ? 'seg-btn active' : 'seg-btn'}
                aria-pressed={s.motion === value}
                onClick={() => s.update('motion', value)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="settings-row">
          <div className="settings-label">
            <span className="settings-name">Contrast</span>
            <span className="settings-help">Stronger borders and brighter text.</span>
          </div>
          <div className="settings-control seg">
            {(
              [
                ['normal', 'Normal'],
                ['high', 'High'],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                className={s.contrast === value ? 'seg-btn active' : 'seg-btn'}
                aria-pressed={s.contrast === value}
                onClick={() => s.update('contrast', value)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </section>

      <section className="settings-group">
        <h2>Simulation</h2>

        <div className="settings-row">
          <div className="settings-label">
            <span className="settings-name">Starting speed</span>
            <span className="settings-help">The speed a run begins at when NEXUS connects.</span>
          </div>
          <div className="settings-control">
            <select
              value={s.defaultSpeed}
              onChange={(e) => s.update('defaultSpeed', Number(e.target.value))}
            >
              {SPEED_OPTIONS.map((v) => (
                <option key={v} value={v}>
                  {v}×{v === 1 ? ' (real time)' : ''}
                </option>
              ))}
            </select>
          </div>
        </div>
      </section>

      <section className="settings-group">
        <h2>Emergency alerts</h2>

        <div className="settings-row">
          <div className="settings-label">
            <span className="settings-name">Sound cue</span>
            <span className="settings-help">A short tone when an emergency vehicle is detected.</span>
          </div>
          <div className="settings-control">
            <label className="switch">
              <input
                type="checkbox"
                checked={s.sound}
                onChange={(e) => s.update('sound', e.target.checked)}
              />
              <span className="switch-track" aria-hidden="true" />
              <span className="sr-only">Sound cue for emergencies</span>
            </label>
          </div>
        </div>

        <div className="settings-row">
          <div className="settings-label">
            <span className="settings-name">Desktop notification</span>
            <span className="settings-help">
              A notification if an emergency happens while this tab is in the background.
            </span>
          </div>
          <div className="settings-control">
            <label className="switch">
              <input
                type="checkbox"
                checked={s.notifications}
                onChange={(e) => onToggleNotifications(e.target.checked)}
              />
              <span className="switch-track" aria-hidden="true" />
              <span className="sr-only">Desktop notifications for emergencies</span>
            </label>
          </div>
        </div>
        {notifyNote ? <p className="settings-note">{notifyNote}</p> : null}
      </section>

      <section className="settings-group">
        <button className="btn-cta sm ghost" onClick={() => s.reset()}>
          Reset to defaults
        </button>
      </section>

      <p className="settings-safety">
        The safety layer that checks every signal change is always on and is not a
        setting.
      </p>
    </main>
  );
}
