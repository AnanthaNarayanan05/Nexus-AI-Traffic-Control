import { useEffect, useRef, useState } from 'react';

import { useSimStore } from '../store';

/**
 * Rolling client-side history of the headline metric values, sampled once per distinct
 * `metric_update` frame. This exists only to draw the on-screen trend line: it is never
 * persisted, never sent anywhere, and is cleared when the view unmounts.
 *
 * Nothing is interpolated or carried forward — a non-finite reading is simply skipped,
 * so a gap in the data is a gap in the line (MASTER_PROMPT §84, §114).
 */

export interface MetricTrails {
  avg_waiting_s: number[];
  avg_queue: number[];
  throughput_vph: number[];
  avg_travel_time_s: number[];
  avg_speed_mps: number[];
  stops_per_veh: number[];
  fuel_l_per_veh: number[];
  co2_kg_per_veh: number[];
  emergency_wait_s: number[];
}

const KEYS: (keyof MetricTrails)[] = [
  'avg_waiting_s',
  'avg_queue',
  'throughput_vph',
  'avg_travel_time_s',
  'avg_speed_mps',
  'stops_per_veh',
  'fuel_l_per_veh',
  'co2_kg_per_veh',
  'emergency_wait_s',
];

const DEFAULT_CAP = 60;

function empty(): MetricTrails {
  return {
    avg_waiting_s: [],
    avg_queue: [],
    throughput_vph: [],
    avg_travel_time_s: [],
    avg_speed_mps: [],
    stops_per_veh: [],
    fuel_l_per_veh: [],
    co2_kg_per_veh: [],
    emergency_wait_s: [],
  };
}

export function useMetricTrail(cap = DEFAULT_CAP): MetricTrails {
  const metrics = useSimStore((s) => s.metrics);
  const trailsRef = useRef<MetricTrails>(empty());
  const lastSampledAt = useRef<number>(Number.NaN);
  const [, force] = useState(0);

  useEffect(() => {
    if (!metrics) return;
    // one sample per distinct sim_time — the frame can be re-published unchanged.
    if (metrics.sim_time === lastSampledAt.current) return;
    lastSampledAt.current = metrics.sim_time;

    const source: Record<string, number | undefined> = {
      ...metrics.traffic,
      fuel_l_per_veh: metrics.environmental?.fuel_l_per_veh,
      co2_kg_per_veh: metrics.environmental?.co2_kg_per_veh,
      emergency_wait_s: metrics.emergency?.emergency_wait_s,
    };

    let changed = false;
    for (const key of KEYS) {
      const v = source[key];
      if (typeof v !== 'number' || !Number.isFinite(v)) continue;
      const arr = trailsRef.current[key];
      arr.push(v);
      if (arr.length > cap) arr.shift();
      changed = true;
    }
    if (changed) force((n) => n + 1);
  }, [metrics, cap]);

  return trailsRef.current;
}
