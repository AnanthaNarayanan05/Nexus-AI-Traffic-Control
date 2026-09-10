import { useEffect, useRef, useState } from 'react';

import { api } from '../lib/api';
import { NO_DATA, clock, int, num } from '../lib/format';
import type { CompactState } from '../lib/types';
import { DEFAULT_GEOMETRY, IntersectionScene } from '../render/scene';
import type { SceneGeometry } from '../render/scene';
import { onSimulationState, useSimStore } from '../store';
import { Badge, Panel } from './common/Primitives';

interface GeometryConfig {
  approach_length_m?: number;
  lanes_per_approach?: number;
  lane_width_m?: number;
  intersection_size_m?: number;
  stop_line_offset_m?: number;
}

function toSceneGeometry(g: GeometryConfig | undefined): SceneGeometry {
  if (!g) return DEFAULT_GEOMETRY;
  const box = g.intersection_size_m ?? DEFAULT_GEOMETRY.boxSize;
  return {
    laneWidth: g.lane_width_m ?? DEFAULT_GEOMETRY.laneWidth,
    lanes: g.lanes_per_approach ?? DEFAULT_GEOMETRY.lanes,
    boxSize: box,
    stopLineDist: box / 2 + (g.stop_line_offset_m ?? 2),
    approachLength: g.approach_length_m ?? DEFAULT_GEOMETRY.approachLength,
  };
}

const LEGEND: [string, string][] = [
  ['#8fa6c9', 'car'],
  ['#59b0d8', 'bus'],
  ['#9b8ac4', 'truck'],
  ['#ff4d6d', 'emergency'],
  ['#ff2d55', 'violator'],
];

export function SimulationStage({ minimalChrome = false }: { minimalChrome?: boolean } = {}) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const sceneRef = useRef<IntersectionScene | null>(null);
  const [radius, setRadius] = useState(95);
  const [fps, setFps] = useState<number | null>(null);

  const connection = useSimStore((s) => s.connection);
  const state = useSimStore((s) => s.state);
  const status = useSimStore((s) => s.status);

  // Mount the Pixi application once. Geometry comes from the backend config so the
  // drawing and the physics never drift apart.
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const scene = new IntersectionScene();
    sceneRef.current = scene;
    let disposed = false;

    (async () => {
      let geometry: SceneGeometry = DEFAULT_GEOMETRY;
      try {
        const cfg = (await api.config()) as { geometry?: GeometryConfig };
        geometry = toSceneGeometry(cfg.geometry);
      } catch {
        /* offline: fall back to the documented defaults rather than a blank canvas */
      }
      if (disposed) return;
      await scene.init(host, geometry);
    })();

    return () => {
      disposed = true;
      sceneRef.current = null;
      scene.destroy();
    };
  }, []);

  // Vehicle poses bypass React entirely: 20 Hz store writes would re-render the tree.
  useEffect(
    () =>
      onSimulationState((s: CompactState) => {
        sceneRef.current?.update(s);
      }),
    [],
  );

  useEffect(() => {
    sceneRef.current?.setViewRadius(radius);
  }, [radius]);

  // Rendered frame rate, measured in this browser - not a backend metric.
  useEffect(() => {
    let frames = 0;
    let last = performance.now();
    let raf = 0;
    const loop = () => {
      frames += 1;
      const now = performance.now();
      if (now - last >= 1000) {
        setFps((frames * 1000) / (now - last));
        frames = 0;
        last = now;
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);

  const signal = state?.signal;
  const phase = signal?.current_phase ?? NO_DATA;
  const transition = signal?.transition;
  const emergency = state?.emergency;

  return (
    <Panel
      title="Intersection"
      accent="var(--accent)"
      sub={
        minimalChrome
          ? undefined
          : state
            ? `t=${clock(state.sim_time)} · step ${int(state.step)} · ${status?.adapter ?? NO_DATA}`
            : undefined
      }
      flex
      bodyClass="stage"
    >
      <div className="stage-canvas" ref={hostRef} />

      <div className="stage-overlay">
        <Badge tone={connection === 'open' ? 'good' : connection === 'connecting' ? 'warn' : 'bad'}>
          {connection.toUpperCase()}
        </Badge>
        <Badge tone={phase === 'ALL_RED' || phase === 'YELLOW' ? 'warn' : 'info'}>
          PHASE {phase}
        </Badge>
        {transition ? (
          <Badge tone="warn">
            {transition.kind} {num(transition.elapsed_s)}/{num(transition.total_s)}s →{' '}
            {transition.to_phase}
          </Badge>
        ) : null}
        {emergency?.active ? (
          <Badge tone="bad">
            EMERGENCY {emergency.type ?? ''} {emergency.approach ?? ''}
            {emergency.eta_s !== null && emergency.eta_s !== undefined
              ? ` · ETA ${num(emergency.eta_s)}s`
              : ''}
          </Badge>
        ) : null}
        <Badge tone="neutral">{int(state?.totals.vehicles)} veh</Badge>
      </div>

      <div className="stage-legend">
        {LEGEND.map(([color, name]) => (
          <span className="legend-item" key={name}>
            <span className="legend-dot" style={{ background: color }} />
            {name}
          </span>
        ))}
      </div>

      <div className="stage-controls">
        <span>view {radius} m</span>
        <input
          type="range"
          min={40}
          max={240}
          step={5}
          value={radius}
          onChange={(e) => setRadius(Number(e.target.value))}
          style={{ width: 96, padding: 0 }}
          aria-label="View radius in metres"
        />
        {minimalChrome ? null : <span>{fps === null ? NO_DATA : `${Math.round(fps)} fps`}</span>}
      </div>
    </Panel>
  );
}
