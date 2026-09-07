import { NO_DATA, int, num } from '../lib/format';
import { useSimStore } from '../store';
import { Badge, Panel, Stat } from './common/Primitives';

/**
 * Every figure here is read straight from the backend MetricSnapshot. Nothing is
 * derived, smoothed or compared against a baseline in the browser: a comparison against
 * fixed-time is a measured experiment, not a display trick (MASTER_PROMPT sections 84, 114).
 */
export function MetricsRow() {
  const metrics = useSimStore((s) => s.metrics);
  const mode = useSimStore((s) => s.status?.mode);

  const t = metrics?.traffic;
  const env = metrics?.environmental;
  const em = metrics?.emergency;
  const safety = metrics?.safety;

  return (
    <Panel
      title="Measured metrics"
      accent="var(--green)"
      sub={
        metrics ? `${metrics.window} window · t=${num(metrics.sim_time, 0)}s · ${mode ?? ''}` : undefined
      }
      actions={metrics ? null : <Badge tone="neutral">awaiting first snapshot</Badge>}
      bodyClass="tight"
    >
      <div className="metrics-row">
        <Stat label="Avg wait" value={num(t?.avg_waiting_s)} unit="s" />
        <Stat label="Avg queue" value={num(t?.avg_queue)} unit="veh" />
        <Stat label="Throughput" value={int(t?.throughput_vph)} unit="vph" />
        <Stat label="Travel time" value={num(t?.avg_travel_time_s)} unit="s" />
        <Stat label="Avg speed" value={num(t?.avg_speed_mps)} unit="m/s" />
        <Stat label="Stops / veh" value={num(t?.stops_per_veh, 2)} />
        <Stat
          label="Fuel / veh"
          value={num(env?.fuel_l_per_veh, 3)}
          unit="L"
          note={<span className="estimated-tag">ESTIMATED</span>}
          title="Parametric estimate (idle + per-stop + cruise + acceleration), docs/assumptions.md A12"
        />
        <Stat
          label="CO₂ / veh"
          value={num(env?.co2_kg_per_veh, 3)}
          unit="kg"
          note={<span className="estimated-tag">ESTIMATED</span>}
          title="CO2 = fuel x 2.31 kg/L, docs/assumptions.md A13"
        />
        <Stat
          label="Emergency wait"
          value={num(em?.emergency_wait_s)}
          unit="s"
          tone="var(--a2c)"
          note={em ? `${int(em.emergency_cleared)} cleared` : undefined}
        />
        <Stat
          label="Violations"
          value={
            safety
              ? int(safety.red_light_violations + safety.other_violations)
              : NO_DATA
          }
          tone={
            safety && safety.red_light_violations + safety.other_violations > 0
              ? 'var(--orange)'
              : undefined
          }
          note={safety ? `${int(safety.red_light_violations)} red-light` : undefined}
        />
        <Stat
          label="Unsafe transitions"
          value={int(safety?.unsafe_transitions)}
          tone={safety && safety.unsafe_transitions > 0 ? 'var(--red)' : 'var(--green)'}
        />
      </div>
    </Panel>
  );
}
