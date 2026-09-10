import { useEffect, useRef } from 'react';

import { emergencyRead } from '../lib/situation';
import { socket } from '../lib/ws';
import { useSimStore } from '../store';
import { useSettings } from '../store/settings';

/**
 * Applies the customer preferences (R11 §30) as live side effects. Rendered once,
 * near the app root, and draws nothing.
 *
 *   motion / contrast  → data-attributes on <html>; product.css honours them
 *   defaultSpeed       → sent once per fresh WS connection
 *   sound / notifications → an audible / desktop cue the first moment an emergency
 *                           vehicle becomes active (never disables anything)
 */
export function SettingsEffects() {
  const motion = useSettings((s) => s.motion);
  const contrast = useSettings((s) => s.contrast);
  const defaultSpeed = useSettings((s) => s.defaultSpeed);
  const sound = useSettings((s) => s.sound);
  const notifications = useSettings((s) => s.notifications);

  useEffect(() => {
    const root = document.documentElement;
    if (motion === 'system') delete root.dataset.motion;
    else root.dataset.motion = motion;
  }, [motion]);

  useEffect(() => {
    const root = document.documentElement;
    if (contrast === 'high') root.dataset.contrast = 'high';
    else delete root.dataset.contrast;
  }, [contrast]);

  // Apply the preferred speed once each time the socket (re)connects.
  const connection = useSimStore((s) => s.connection);
  const appliedRef = useRef(false);
  useEffect(() => {
    if (connection !== 'open') {
      appliedRef.current = false;
      return;
    }
    if (appliedRef.current) return;
    appliedRef.current = true;
    if (defaultSpeed !== 1) socket.command('set_speed', { speed: defaultSpeed });
  }, [connection, defaultSpeed]);

  // Emergency cue on the rising edge of emergency.active.
  const emergencyActive = useSimStore((s) => Boolean(s.state?.emergency?.active));
  const wasActiveRef = useRef(false);
  useEffect(() => {
    if (emergencyActive && !wasActiveRef.current) {
      if (sound) playEmergencyTone();
      if (
        notifications &&
        typeof document !== 'undefined' &&
        document.hidden &&
        'Notification' in window &&
        Notification.permission === 'granted'
      ) {
        const em = emergencyRead(useSimStore.getState().state);
        try {
          new Notification('NEXUS — emergency vehicle', {
            body: em
              ? `${em.type} approaching from the ${em.approachName}.`
              : 'Emergency priority activated.',
            tag: 'nexus-emergency',
          });
        } catch {
          /* notification construction can throw on some platforms */
        }
      }
    }
    wasActiveRef.current = emergencyActive;
  }, [emergencyActive, sound, notifications]);

  return null;
}

let audioCtx: AudioContext | null = null;

function playEmergencyTone(): void {
  try {
    const Ctor =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctor) return;
    audioCtx ??= new Ctor();
    const ctx = audioCtx;
    const now = ctx.currentTime;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(660, now);
    osc.frequency.setValueAtTime(880, now + 0.18);
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(0.16, now + 0.03);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.55);
    osc.connect(gain).connect(ctx.destination);
    osc.start(now);
    osc.stop(now + 0.6);
  } catch {
    /* audio unavailable — the on-screen banner still appears */
  }
}
