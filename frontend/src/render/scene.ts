import { Application, Container, Graphics, Sprite, Text, Texture } from 'pixi.js';

import type { Approach, CompactState, SignalColor, VehicleArrays } from '../lib/types';

/**
 * PixiJS 2D renderer for the intersection.
 *
 * World frame matches the backend exactly: origin at the intersection centre, +x East,
 * +y North, metres (backend/app/simulation/geometry.py). Screen y is flipped because
 * canvas y grows downward.
 *
 * Vehicle positions are the simulation's own output. The only client-side liberty is
 * visual easing between the 2 Hz physics ticks and the 60 fps canvas - documented in
 * docs/assumptions.md A16. No position is ever extrapolated past the latest snapshot.
 */

export interface SceneGeometry {
  laneWidth: number;
  lanes: number;
  boxSize: number;
  stopLineDist: number;
  approachLength: number;
}

export const DEFAULT_GEOMETRY: SceneGeometry = {
  laneWidth: 3.4,
  lanes: 3,
  boxSize: 24,
  stopLineDist: 14,
  approachLength: 220,
};

const COLORS = {
  ground: 0x0b0f16,
  asphalt: 0x1c2230,
  asphaltEdge: 0x2b3446,
  laneDash: 0x3d4860,
  centreLine: 0xd8b64a,
  stopLine: 0xe7ecf5,
  box: 0x212938,
  green: 0x2ee06a,
  yellow: 0xf5c542,
  red: 0xf2506a,
  car: 0x8fa6c9,
  suv: 0x7f93b8,
  bus: 0x59b0d8,
  truck: 0x9b8ac4,
  ambulance: 0xff4d6d,
  fire_truck: 0xff7a3d,
  police: 0x4d8dff,
  violator: 0xff2d55,
  label: 0x8494ad,
} as const;

const SIGNAL_TINT: Record<SignalColor, number> = {
  GREEN: COLORS.green,
  YELLOW: COLORS.yellow,
  RED: COLORS.red,
};

const VEHICLE_TINT: Record<string, number> = {
  car: COLORS.car,
  suv: COLORS.suv,
  bus: COLORS.bus,
  truck: COLORS.truck,
  ambulance: COLORS.ambulance,
  fire_truck: COLORS.fire_truck,
  police: COLORS.police,
};

const VEHICLE_LENGTH_M: Record<string, number> = {
  car: 4.6,
  suv: 5.0,
  bus: 11.0,
  truck: 9.0,
  ambulance: 6.2,
  fire_truck: 9.5,
  police: 4.8,
};

const APPROACHES: Approach[] = ['N', 'E', 'S', 'W'];

/** Incoming travel direction per approach, mirroring APPROACH_DIR in geometry.py. */
const DIR: Record<Approach, [number, number]> = {
  N: [0, -1],
  S: [0, 1],
  E: [-1, 0],
  W: [1, 0],
};

interface VehicleNode {
  sprite: Sprite;
  halo: Graphics | null;
  x: number;
  y: number;
  rot: number;
  seen: number;
}

export class IntersectionScene {
  readonly app = new Application();

  private geo: SceneGeometry = DEFAULT_GEOMETRY;
  private world = new Container();
  private staticLayer = new Container();
  private signalLayer = new Container();
  private vehicleLayer = new Container();
  private overlayLayer = new Container();

  private nodes = new Map<string, VehicleNode>();
  private signalLamps = new Map<Approach, Graphics>();
  private queueLabels = new Map<Approach, Text>();
  private frameTick = 0;

  private latest: CompactState | null = null;
  private viewRadius = 95;
  private scale = 1;
  private ready = false;
  private destroyed = false;

  async init(host: HTMLElement, geometry?: Partial<SceneGeometry>): Promise<void> {
    this.geo = { ...DEFAULT_GEOMETRY, ...(geometry ?? {}) };
    await this.app.init({
      background: COLORS.ground,
      antialias: true,
      resolution: Math.min(window.devicePixelRatio || 1, 2),
      autoDensity: true,
      resizeTo: host,
    });
    if (this.destroyed) {
      this.app.destroy(true);
      return;
    }
    host.appendChild(this.app.canvas);

    this.world.addChild(this.staticLayer, this.signalLayer, this.vehicleLayer, this.overlayLayer);
    this.app.stage.addChild(this.world);

    this.drawStatic();
    this.buildSignals();
    this.layout();
    this.ready = true;

    this.app.renderer.on('resize', () => this.layout());
    this.app.ticker.add(() => this.animate());
  }

  destroy(): void {
    this.destroyed = true;
    if (this.ready) this.app.destroy(true, { children: true });
  }

  setViewRadius(metres: number): void {
    this.viewRadius = Math.max(35, Math.min(260, metres));
    if (this.ready) this.layout();
  }

  getViewRadius(): number {
    return this.viewRadius;
  }

  /** Feed one snapshot. Called at the stream rate, independent of the render loop. */
  update(state: CompactState): void {
    this.latest = state;
    if (this.ready) this.syncVehicles(state.vehicles);
  }

  /* ---------------------------------------------------------------- layout */

  private layout(): void {
    const { width, height } = this.app.renderer;
    const res = this.app.renderer.resolution;
    const w = width / res;
    const h = height / res;
    this.scale = Math.min(w, h) / (2 * this.viewRadius);
    this.world.scale.set(this.scale, this.scale);
    this.world.position.set(w / 2, h / 2);
  }

  /* ---------------------------------------------------------------- static art */

  private get roadHalfWidth(): number {
    return this.geo.lanes * this.geo.laneWidth;
  }

  private drawStatic(): void {
    this.staticLayer.removeChildren();
    const hw = this.roadHalfWidth;
    const reach = this.geo.stopLineDist + this.geo.approachLength;

    const g = new Graphics();
    // two crossing carriageways + the conflict box
    g.rect(-hw, -reach, hw * 2, reach * 2).fill(COLORS.asphalt);
    g.rect(-reach, -hw, reach * 2, hw * 2).fill(COLORS.asphalt);
    g.rect(-hw, -hw, hw * 2, hw * 2).fill(COLORS.box);
    this.staticLayer.addChild(g);

    // lane dashes: skip the box, dash along each carriageway
    const dashes = new Graphics();
    const dashLen = 5;
    const gapLen = 6;
    for (let lane = 1; lane < this.geo.lanes * 2; lane += 1) {
      const off = -hw + lane * this.geo.laneWidth;
      if (Math.abs(off) < 0.01) continue; // centreline drawn separately
      for (let d = hw; d < reach; d += dashLen + gapLen) {
        dashes.rect(off - 0.16, -d - dashLen, 0.32, dashLen).fill(COLORS.laneDash);
        dashes.rect(off - 0.16, d, 0.32, dashLen).fill(COLORS.laneDash);
        dashes.rect(-d - dashLen, off - 0.16, dashLen, 0.32).fill(COLORS.laneDash);
        dashes.rect(d, off - 0.16, dashLen, 0.32).fill(COLORS.laneDash);
      }
    }
    // carriageway centrelines
    for (let d = hw; d < reach; d += 1) {
      dashes.rect(-0.2, -d, 0.4, 1).fill({ color: COLORS.centreLine, alpha: 0.5 });
      dashes.rect(-0.2, d - 1, 0.4, 1).fill({ color: COLORS.centreLine, alpha: 0.5 });
      dashes.rect(-d, -0.2, 1, 0.4).fill({ color: COLORS.centreLine, alpha: 0.5 });
      dashes.rect(d - 1, -0.2, 1, 0.4).fill({ color: COLORS.centreLine, alpha: 0.5 });
    }
    this.staticLayer.addChild(dashes);

    // stop lines: one per approach, spanning that approach's incoming lanes only
    const stops = new Graphics();
    const s = this.geo.stopLineDist;
    const laneSpan = this.geo.lanes * this.geo.laneWidth;
    stops.rect(-laneSpan, -s - 0.7, laneSpan, 0.7).fill(COLORS.stopLine); // N
    stops.rect(0, s, laneSpan, 0.7).fill(COLORS.stopLine); // S
    stops.rect(s, 0, 0.7, laneSpan).fill(COLORS.stopLine); // E
    stops.rect(-s - 0.7, -laneSpan, 0.7, laneSpan).fill(COLORS.stopLine); // W
    this.staticLayer.addChild(stops);
  }

  private buildSignals(): void {
    this.signalLayer.removeChildren();
    this.overlayLayer.removeChildren();
    this.signalLamps.clear();
    this.queueLabels.clear();

    const s = this.geo.stopLineDist;
    const hw = this.roadHalfWidth;
    // lamp sits just outside the box, on the near side of each approach
    const spot: Record<Approach, [number, number]> = {
      N: [-hw - 4.5, -s - 3],
      S: [hw + 4.5, s + 3],
      E: [s + 3, -hw - 4.5],
      W: [-s - 3, hw + 4.5],
    };

    for (const a of APPROACHES) {
      const [wx, wy] = spot[a];
      const lamp = new Graphics();
      lamp.position.set(wx, -wy);
      this.signalLayer.addChild(lamp);
      this.signalLamps.set(a, lamp);

      const label = new Text({
        text: `${a} 0`,
        style: { fontFamily: 'ui-monospace, monospace', fontSize: 9, fill: COLORS.label },
      });
      label.anchor.set(0.5);
      label.scale.set(0.42);
      label.position.set(wx, -wy - 6.5);
      this.overlayLayer.addChild(label);
      this.queueLabels.set(a, label);
    }
  }

  /* ---------------------------------------------------------------- vehicles */

  private syncVehicles(v: VehicleArrays): void {
    this.frameTick += 1;
    const n = v.id.length;
    for (let i = 0; i < n; i += 1) {
      const id = v.id[i];
      let node = this.nodes.get(id);
      const sx = v.x[i];
      const sy = -v.y[i];
      const rot = -v.heading[i];

      if (!node) {
        const sprite = new Sprite(Texture.WHITE);
        sprite.anchor.set(0.5);
        const len = VEHICLE_LENGTH_M[v.type[i]] ?? 4.6;
        sprite.width = len;
        sprite.height = 2.0;
        sprite.tint = v.violator[i]
          ? COLORS.violator
          : (VEHICLE_TINT[v.type[i]] ?? COLORS.car);
        this.vehicleLayer.addChild(sprite);

        let halo: Graphics | null = null;
        if (v.emergency[i]) {
          halo = new Graphics();
          halo.circle(0, 0, 5.5).fill({ color: COLORS.ambulance, alpha: 0.22 });
          this.vehicleLayer.addChildAt(halo, 0);
        }
        node = { sprite, halo, x: sx, y: sy, rot, seen: this.frameTick };
        this.nodes.set(id, node);
      }

      node.seen = this.frameTick;
      node.sprite.tint = v.violator[i] ? COLORS.violator : (VEHICLE_TINT[v.type[i]] ?? COLORS.car);
      // target pose; the ticker eases the sprite toward it
      node.x = sx;
      node.y = sy;
      node.rot = rot;
    }

    for (const [id, node] of this.nodes) {
      if (node.seen !== this.frameTick) {
        node.sprite.destroy();
        node.halo?.destroy();
        this.nodes.delete(id);
      }
    }
  }

  private animate(): void {
    const t = this.app.ticker;
    // frame-rate independent easing toward the last received pose
    const k = 1 - Math.exp(-t.deltaMS / 55);
    for (const node of this.nodes.values()) {
      const s = node.sprite;
      const dx = node.x - s.position.x;
      const dy = node.y - s.position.y;
      // a large jump means a respawn or a wrap: snap rather than slide across the map
      if (Math.abs(dx) > 25 || Math.abs(dy) > 25) {
        s.position.set(node.x, node.y);
        s.rotation = node.rot;
      } else {
        s.position.set(s.position.x + dx * k, s.position.y + dy * k);
        let dr = node.rot - s.rotation;
        while (dr > Math.PI) dr -= Math.PI * 2;
        while (dr < -Math.PI) dr += Math.PI * 2;
        s.rotation += dr * k;
      }
      if (node.halo) {
        node.halo.position.copyFrom(s.position);
        const pulse = 0.75 + 0.25 * Math.sin(performance.now() / 220);
        node.halo.scale.set(pulse);
      }
    }
    this.paintSignals();
  }

  private paintSignals(): void {
    const state = this.latest;
    if (!state) return;
    const colors = state.signal.approach_colors;
    for (const a of APPROACHES) {
      const lamp = this.signalLamps.get(a);
      if (!lamp) continue;
      const color = colors?.[a] ?? 'RED';
      const tint = SIGNAL_TINT[color];
      lamp.clear();
      lamp.circle(0, 0, 3.4).fill({ color: tint, alpha: 0.16 });
      lamp.circle(0, 0, 1.9).fill(tint);

      const label = this.queueLabels.get(a);
      const ap = state.approaches?.[a];
      if (label && ap) label.text = `${a} ${ap.queue_length}`;
    }
  }

  /** Direction unit vector of an approach, for callers that need it (tests). */
  static direction(a: Approach): [number, number] {
    return DIR[a];
  }
}
