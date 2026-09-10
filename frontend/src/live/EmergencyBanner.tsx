import { emergencyRead } from '../lib/situation';
import { useAgentStore, useSimStore } from '../store';

/**
 * One of the strongest product moments (R11 §16). Shown only while an emergency
 * vehicle is actually being tracked; the wording follows the real approach, ETA and
 * coordinator state.
 */
export function EmergencyBanner() {
  const state = useSimStore((s) => s.state);
  const winner = useAgentStore((s) => s.coordination?.coordination.winner ?? null);
  const em = emergencyRead(state);
  if (!em) return null;

  const priority = state?.emergency?.active && (winner === 'a2c' || (state?.signal?.last_action ?? ''));
  const stage = priority ? 'Priority activated' : 'Emergency vehicle approaching';

  return (
    <div className="emergency-banner" role="alert">
      <span className="emergency-pulse" aria-hidden="true" />
      <div className="emergency-banner-text">
        <span className="emergency-banner-stage">{stage}</span>
        <span className="emergency-banner-detail">
          {em.type} · {em.approachName} approach
          {em.etaSeconds !== null ? ` · about ${Math.round(em.etaSeconds)}s away` : ''}
        </span>
      </div>
      <span className="emergency-banner-action">
        {priority ? 'Clearing a path' : 'Preparing priority'}
      </span>
    </div>
  );
}
