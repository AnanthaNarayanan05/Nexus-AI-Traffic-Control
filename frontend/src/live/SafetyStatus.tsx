import { SAFETY_PRODUCT_STATUS } from '../lib/format';
import { useAgentStore, useSimStore } from '../store';

/**
 * The safety layer, shown prominently but simply (R11 §15). It is always present and
 * always authoritative — the customer can read its state at a glance but can never
 * turn it off.
 */
export function SafetyStatus() {
  const update = useAgentStore((s) => s.coordination);
  const safetySnap = useSimStore((s) => s.state?.safety);

  const action = update?.safety.action_taken ?? null;
  const info = action ? SAFETY_PRODUCT_STATUS[action] ?? SAFETY_PRODUCT_STATUS.APPLIED : null;
  const tone = info?.tone ?? 'good';

  return (
    <section className={`safety-status tone-${tone}`} aria-label="Safety check">
      <div className="safety-status-head">
        <span className="safety-shield" aria-hidden="true" />
        <span className="safety-status-title">Safety check</span>
      </div>
      <p className="safety-status-verdict">
        {info ? info.label : 'Standing by'}
      </p>
      <p className="safety-status-detail">
        {info
          ? info.detail
          : 'Every signal change is validated here before it reaches the road.'}
      </p>
      {typeof safetySnap?.violations_total === 'number' ? (
        <p className="safety-status-foot">
          {safetySnap.violations_total === 0
            ? 'No safety violations recorded this run.'
            : `${safetySnap.violations_total} safety event${
                safetySnap.violations_total === 1 ? '' : 's'
              } recorded this run.`}
        </p>
      ) : null}
    </section>
  );
}
