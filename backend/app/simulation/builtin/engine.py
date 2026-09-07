"""Built-in pure-python traffic microsimulation (docs/simulation.md section 2).

Deterministic given (scenario, seed, action sequence). No external engine.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

import numpy as np

from app.core.config import get_config
from app.logging import get_logger
from app.schemas.enums import (
    Approach,
    ControlMode,
    Movement,
    Phase,
    SignalColor,
    VehicleType,
)
from app.schemas.safety import PhaseCommand
from app.schemas.scenario import ScenarioConfig
from app.schemas.simulation import (
    ApproachState,
    EmergencyState,
    EnvironmentState,
    LaneState,
    LiveEstimates,
    SafetySnapshot,
    SimulationState,
    VehicleSnapshot,
    ViolationEvent,
)
from app.simulation.adapter import SimEvent
from app.simulation.geometry import Geometry
from app.simulation.signals import SignalController
from app.simulation.vehicle import Vehicle

log = get_logger("SIMULATION")

_DETECTOR_M = 120.0          # upstream detector length for speed/wait/density
_QUEUE_SPEED_MPS = 2.0
_WINDOW_S = 60.0
_CAR_TYPES = [VehicleType.CAR, VehicleType.CAR, VehicleType.CAR, VehicleType.SUV, VehicleType.BUS, VehicleType.TRUCK]
_MOVEMENT_LANE = {Movement.LEFT: 0, Movement.THROUGH: 1, Movement.RIGHT: 2}


class BuiltinAdapter:
    name = "builtin"

    def __init__(self) -> None:
        self.geo = Geometry()
        self.scenario = ScenarioConfig()
        self.signals = SignalController()
        self.rng = np.random.default_rng(42)
        self._reset_containers()

    # ------------------------------------------------------------------ reset
    def _reset_containers(self) -> None:
        self._t = 0.0
        self._step = 0
        self._veh_counter = 0
        self._emerg_counter = 0
        self.vehicles: dict[str, Vehicle] = {}
        self.lanes: dict[tuple[Approach, int], list[str]] = defaultdict(list)
        self._events: list[dict[str, Any]] = []
        self._arrival_accum: dict[Approach, float] = dict.fromkeys(Approach, 0.0)
        self._spawn_window: dict[Approach, deque[float]] = {a: deque() for a in Approach}
        self._departures: deque[float] = deque()
        self._stop_events: dict[Approach, deque[float]] = {a: deque() for a in Approach}
        self._violation_window: deque[tuple[float, str]] = deque()
        self._recent_violations: deque[ViolationEvent] = deque(maxlen=8)
        self._violations_total = 0
        self._red_light_total = 0
        self._other_violation_total = 0
        self._completed: list[dict[str, float]] = []
        self._emergency_trips: list[dict[str, float]] = []
        self._emergency_cleared = 0
        self._co2_completed = 0.0
        self._fuel_completed = 0.0
        self._co2_total = 0.0
        self._fuel_total = 0.0
        self._co2_rate = 0.0
        self._fuel_rate = 0.0
        self._prev_total_co2 = 0.0
        self._prev_total_fuel = 0.0
        self._departures_since_mark = 0
        self._active_emergencies: set[str] = set()
        self._blocked: set[tuple[Approach, int]] = set()
        self._surge: tuple[float, Approach | None, float] | None = None
        self._demand = self.scenario.demand
        self._pending_changes: list = []

    def reset(self, scenario: ScenarioConfig, seed: int) -> None:
        self.geo = Geometry()
        self.scenario = scenario
        self.rng = np.random.default_rng(seed)
        self.signals = SignalController()
        self._reset_containers()
        self._demand = scenario.demand
        self._pending_changes = sorted(scenario.scheduled_changes, key=lambda c: c.at_s)
        for spec in scenario.blocked_lanes:
            try:
                self._blocked.add((Approach(spec["approach"]), int(spec["lane"])))
            except Exception:  # noqa: BLE001
                pass
        log.info("simulation reset", scenario=scenario.id, seed=seed)

    # ------------------------------------------------------------------ step
    def step(self, dt: float) -> None:
        self._t += dt
        self._step += 1
        self._apply_scheduled_changes()
        self.signals.step(dt)
        self._spawn(dt)
        self._maybe_random_emergency(dt)
        self._update_vehicles(dt)
        self._update_estimates(dt)
        self._prune_windows()

    def _update_estimates(self, dt: float) -> None:
        active_co2 = sum(v.co2_kg for v in self.vehicles.values())
        active_fuel = sum(v.fuel_l for v in self.vehicles.values())
        cur_co2 = self._co2_completed + active_co2
        cur_fuel = self._fuel_completed + active_fuel
        d_co2 = max(0.0, cur_co2 - self._prev_total_co2) / max(dt, 1e-6)
        d_fuel = max(0.0, cur_fuel - self._prev_total_fuel) / max(dt, 1e-6)
        self._co2_rate = 0.9 * self._co2_rate + 0.1 * d_co2
        self._fuel_rate = 0.9 * self._fuel_rate + 0.1 * d_fuel
        self._prev_total_co2, self._prev_total_fuel = cur_co2, cur_fuel
        self._co2_total, self._fuel_total = cur_co2, cur_fuel

    def _apply_scheduled_changes(self) -> None:
        while self._pending_changes and self._pending_changes[0].at_s <= self._t:
            change = self._pending_changes.pop(0)
            self._demand = change.profile
            self._emit("TRAFFIC", "notice", f"Demand profile changed at t={self._t:.0f}s")

    # ------------------------------------------------------------------ spawn
    def _approach_rate_vps(self, a: Approach) -> float:
        weights = self._demand.normalised()
        rate = self._demand.arrivals_vph * weights.get(a, 0.25) / 3600.0
        if self._surge is not None:
            until, target, factor = self._surge
            if self._t <= until and (target is None or target == a):
                rate *= factor
            elif self._t > until:
                self._surge = None
        return rate

    def _spawn(self, dt: float) -> None:
        cap = int(get_config().simulation.max_vehicles)
        if len(self.vehicles) >= cap:
            return
        splits = self._demand.turn_split
        moves = [Movement.LEFT, Movement.THROUGH, Movement.RIGHT]
        probs = np.array([splits.get("left", 0.2), splits.get("through", 0.6), splits.get("right", 0.2)])
        probs = probs / probs.sum()
        for a in Approach:
            n = self.rng.poisson(self._approach_rate_vps(a) * dt)
            for _ in range(int(n)):
                if len(self.vehicles) >= cap:
                    return
                move = moves[int(self.rng.choice(3, p=probs))]
                lane = _MOVEMENT_LANE[move] if self.geo.lanes >= 3 else 0
                if (a, lane) in self._blocked:
                    lane = next((ln for ln in range(self.geo.lanes) if (a, ln) not in self._blocked), lane)
                self._spawn_one(a, lane, move)
                self._spawn_window[a].append(self._t)

    def _spawn_one(
        self, a: Approach, lane: int, move: Movement, *, vtype: VehicleType | None = None,
        pos: float | None = None, speed: float = 0.0, violator: bool = False,
    ) -> str:
        lane_ids = self.lanes[(a, lane)]
        back_pos = self.geo.approach_length
        if lane_ids:
            last = self.vehicles[lane_ids[-1]]
            back_pos = max(back_pos, last.pos + self.geo.vehicle_length + self.geo.min_gap + 1.0)
        if pos is not None:
            back_pos = pos
        if vtype is None:
            vtype = _CAR_TYPES[int(self.rng.integers(0, len(_CAR_TYPES)))]
        self._veh_counter += 1
        vid = f"v{self._veh_counter}"
        if not violator:
            vscale = self.scenario.violation_probability_scale
            violator = bool(self.rng.random() < get_config().violations.base_red_run_probability * vscale)
        veh = Vehicle(
            id=vid, vtype=vtype, approach=a, lane=lane, movement=move,
            pos=back_pos, speed=speed, entered_t=self._t, is_violator=violator,
        )
        veh.co2_kg += float(get_config().emissions.cold_start_penalty_kg)
        self.vehicles[vid] = veh
        lane_ids.append(vid)
        return vid

    # ------------------------------------------------------------------ emergencies
    def _maybe_random_emergency(self, dt: float) -> None:
        p = self.scenario.emergency_probability_per_min
        if p <= 0:
            return
        if self.rng.random() < p * (dt / 60.0):
            a = Approach(list(Approach)[int(self.rng.integers(0, 4))])
            self.inject(SimEvent("spawn_emergency", {"approach": a.value}))

    # ------------------------------------------------------------------ vehicle update
    def _update_vehicles(self, dt: float) -> None:
        for (a, lane), ids in self.lanes.items():
            ids.sort(key=lambda vid: self.vehicles[vid].pos)
            for i, vid in enumerate(ids):
                veh = self.vehicles[vid]
                leader_gap: float | None = None
                leader_speed = 0.0
                if i > 0:
                    lead = self.vehicles[ids[i - 1]]
                    leader_gap = veh.pos - lead.pos - self.geo.vehicle_length
                    leader_speed = lead.speed

                phantom_gap = self._signal_phantom_gap(veh, a)
                block_gap = self._blockage_gap(veh, a, lane)

                accels = [veh.idm_accel(None, 0.0)]
                if leader_gap is not None:
                    accels.append(veh.idm_accel(leader_gap, leader_speed))
                if phantom_gap is not None:
                    accels.append(veh.idm_accel(phantom_gap, 0.0))
                if block_gap is not None:
                    accels.append(veh.idm_accel(block_gap, 0.0))

                prev_pos = veh.pos
                prev_stops = veh.stops
                veh.integrate(min(accels), dt, self._t)
                if veh.stops > prev_stops:
                    veh.register_stop_fuel()
                    self._stop_events[a].append(self._t)

                if prev_pos > 0.0 >= veh.pos and not veh.crossed_stop_line:
                    veh.crossed_stop_line = True
                    self._check_violation(veh, a)

        self._remove_departed()

    def _signal_phantom_gap(self, veh: Vehicle, a: Approach) -> float | None:
        if veh.pos <= 0.2:
            return None
        color = self.signals.movement_color(a, veh.movement)
        if color == SignalColor.GREEN:
            return None
        if color == SignalColor.YELLOW:
            # dilemma zone: if the vehicle cannot stop comfortably, let it clear
            needed = (veh.speed ** 2) / (2.0 * max(veh.pos, 0.1))
            if needed > 3.2:
                return None
        if veh.is_violator and color == SignalColor.RED and veh.pos < 22.0:
            return None  # violator commits to running the red
        return veh.pos

    def _blockage_gap(self, veh: Vehicle, a: Approach, lane: int) -> float | None:
        if (a, lane) not in self._blocked or veh.pos <= 0:
            return None
        incident_pos = 45.0
        if veh.pos <= incident_pos:
            return None
        return veh.pos - incident_pos

    def _check_violation(self, veh: Vehicle, a: Approach) -> None:
        color = self.signals.movement_color(a, veh.movement)
        in_transition = self.signals.in_transition
        vtype = None
        if veh.is_violator and color == SignalColor.RED and not in_transition:
            vtype = "red_light"
            self._red_light_total += 1
        elif in_transition and self.signals.current_phase == Phase.ALL_RED and veh.speed > 2.5:
            vtype = "unsafe_crossing"
            self._other_violation_total += 1
        if vtype is None:
            return
        veh.violation_recorded = True
        self._violations_total += 1
        self._violation_window.append((self._t, vtype))
        ev = ViolationEvent(
            id=f"vio{self._violations_total}", t=round(self._t, 1), approach=a, type=vtype,
            signal_state=color.value, severity="warning" if vtype == "red_light" else "critical",
        )
        self._recent_violations.append(ev)
        self._emit("VIOLATION", ev.severity, f"{vtype.replace('_', ' ').title()} - {a.value} approach", vehicle=veh.id)

    def _remove_departed(self) -> None:
        gone: list[str] = []
        for vid, veh in self.vehicles.items():
            total = self.geo.total_path_length(veh.approach, veh.lane, veh.movement)
            if veh.pos <= -(total - self.geo.approach_length):
                veh.departed_t = self._t
                gone.append(vid)
        for vid in gone:
            veh = self.vehicles.pop(vid)
            self.lanes[(veh.approach, veh.lane)].remove(vid)
            self._departures.append(self._t)
            tt = self._t - veh.entered_t
            ff = self.geo.total_path_length(veh.approach, veh.lane, veh.movement) / max(veh.desired_speed, 1.0)
            record = {"travel_time": tt, "free_flow": ff, "stops": veh.stops,
                      "fuel": veh.fuel_l, "co2": veh.co2_kg, "wait": veh.wait_s}
            self._completed.append(record)
            self._co2_completed += veh.co2_kg
            self._fuel_completed += veh.fuel_l
            if veh.is_emergency:
                self._emergency_cleared += 1
                self._emergency_trips.append({"travel_time": tt, "delay": max(0.0, tt - ff), "wait": veh.wait_s})
                self._active_emergencies.discard(vid)
                self._emit("EMERGENCY", "notice", f"{veh.vtype.value.replace('_', ' ').title()} cleared the intersection", vehicle=vid)
            else:
                self._departures_since_mark += 1
            if len(self._completed) > 4000:
                self._completed = self._completed[-3000:]

    def _prune_windows(self) -> None:
        lo = self._t - _WINDOW_S
        for dq in (self._departures, *self._spawn_window.values(), *self._stop_events.values()):
            while dq and dq[0] < lo:
                dq.popleft()
        while self._violation_window and self._violation_window[0][0] < lo:
            self._violation_window.popleft()

    # ------------------------------------------------------------------ commands
    def apply_phase(self, command: PhaseCommand) -> None:
        self.signals.apply(command)

    # ------------------------------------------------------------------ inject
    def inject(self, event: SimEvent) -> list[str]:
        kind = event.kind
        args = event.args
        if kind == "spawn_emergency":
            return [self._spawn_emergency(args)]
        if kind == "traffic_surge":
            target = Approach(args["approach"]) if args.get("approach") else None
            factor = float(args.get("factor", 3.0))
            dur = float(args.get("duration", 90.0))
            self._surge = (self._t + dur, target, factor)
            self._emit("TRAFFIC", "warning", f"Traffic surge{' on ' + target.value if target else ''} (x{factor:.0f})")
            return []
        if kind == "block_lane":
            a, lane = Approach(args["approach"]), int(args.get("lane", 1))
            self._blocked.add((a, lane))
            self._emit("TRAFFIC", "warning", f"Lane blocked - {a.value} lane {lane}")
            return []
        if kind == "unblock_lane":
            self._blocked.discard((Approach(args["approach"]), int(args.get("lane", 1))))
            return []
        if kind == "create_violation":
            return self._force_violation(args)
        if kind == "incident":
            if self.rng.random() < 0.5:
                self.inject(SimEvent("block_lane", {"approach": args.get("approach", "E"), "lane": 1}))
            else:
                self.inject(SimEvent("traffic_surge", {"factor": 2.5, "duration": 120}))
            return []
        log.warning("unknown inject event", kind=kind)
        return []

    def _spawn_emergency(self, args: dict[str, Any]) -> str:
        a = Approach(args.get("approach", "N"))
        tname = args.get("type", "ambulance")
        vtype = VehicleType(tname) if tname in {t.value for t in VehicleType} else VehicleType.AMBULANCE
        self._emerg_counter += 1
        lane = 1 if self.geo.lanes >= 2 else 0
        vid = self._spawn_one(a, lane, Movement.THROUGH, vtype=vtype, pos=None, speed=8.0)
        veh = self.vehicles[vid]
        veh.id = f"e{self._emerg_counter}"
        self.vehicles.pop(vid)
        self.vehicles[veh.id] = veh
        self.lanes[(a, lane)][-1] = veh.id
        self._active_emergencies.add(veh.id)
        self._emit("EMERGENCY", "critical", f"{vtype.value.replace('_', ' ').title()} detected - {a.value} approach", vehicle=veh.id)
        return veh.id

    def _force_violation(self, args: dict[str, Any]) -> list[str]:
        for a in Approach:
            for lane in range(self.geo.lanes):
                if self.signals.movement_color(a, Movement.THROUGH) == SignalColor.RED:
                    vid = self._spawn_one(a, lane, Movement.THROUGH, pos=14.0, speed=9.0, violator=True)
                    return [vid]
        vid = self._spawn_one(Approach.N, 1, Movement.THROUGH, pos=14.0, speed=9.0, violator=True)
        return [vid]

    # ------------------------------------------------------------------ state
    def get_state(self) -> SimulationState:
        emergency = self._emergency_state()
        approaches = {a: self._approach_state(a) for a in Approach}
        signal = self.signals.to_state(emergency.active)
        safety = SafetySnapshot(
            violations_last_window=len(self._violation_window),
            violations_total=self._violations_total,
            unsafe_transitions_total=0,
            recent=list(self._recent_violations),
        )
        env = EnvironmentState(
            weather=self.scenario.weather, time_of_day=self.scenario.time_of_day,
            blocked_lanes=[{"approach": a.value, "lane": ln} for (a, ln) in self._blocked],
        )
        estimates = LiveEstimates(
            throughput_vph=round(self.throughput_vph(), 1),
            departures_last_interval=self._departures_since_mark,
            fuel_l_per_s=round(self._fuel_rate, 6),
            co2_kg_per_s=round(self._co2_rate, 6),
            fuel_l_total=round(self._fuel_total, 4),
            co2_kg_total=round(self._co2_total, 4),
        )
        return SimulationState(
            sim_time=round(self._t, 2), step=self._step,
            control_mode=ControlMode(self._mode), signal=signal, approaches=approaches,
            emergency=emergency, safety=safety, environment=env, estimates=estimates,
            vehicles=[self._veh_snapshot(v) for v in self.vehicles.values()],
        )

    def mark_interval(self) -> int:
        """Return non-emergency departures since the last call and reset the counter."""
        n, self._departures_since_mark = self._departures_since_mark, 0
        return n

    # control mode is owned by the SimulationManager; it calls set_mode() so the
    # adapter can stamp it onto the state snapshot.
    _mode: str = "AI"

    def set_mode(self, mode: str) -> None:
        self._mode = mode

    def _approach_state(self, a: Approach) -> ApproachState:
        vehs = [v for v in self.vehicles.values() if v.approach == a and v.pos > -2.0]
        upstream = [v for v in vehs if 0.0 < v.pos <= _DETECTOR_M]
        queue = [v for v in vehs if v.pos > 0.0 and v.speed < _QUEUE_SPEED_MPS]
        mean_speed = float(np.mean([v.speed for v in upstream])) if upstream else self.geo.free_flow_mps
        waits = [v.wait_s for v in vehs if v.pos > 0.0]
        mean_wait = float(np.mean(waits)) if waits else 0.0
        max_wait = float(np.max(waits)) if waits else 0.0
        density = len(upstream) / (_DETECTOR_M * self.geo.lanes) * 1000.0
        spawn_dq = self._spawn_window[a]
        arrival_vph = len(spawn_dq) / _WINDOW_S * 3600.0 if spawn_dq else 0.0
        lanes = []
        for ln in range(self.geo.lanes):
            lids = [v for v in vehs if v.lane == ln]
            lanes.append(LaneState(
                index=ln, vehicle_count=len(lids),
                queue_length=len([v for v in lids if v.pos > 0 and v.speed < _QUEUE_SPEED_MPS]),
                blocked=(a, ln) in self._blocked,
            ))
        return ApproachState(
            approach=a, vehicle_count=len(vehs), queue_length=len(queue),
            mean_speed_mps=round(mean_speed, 2), mean_wait_s=round(mean_wait, 2),
            max_wait_s=round(max_wait, 2), density_veh_per_km=round(density, 1),
            arrival_rate_vph=round(arrival_vph, 1),
            stops_last_window=len(self._stop_events[a]), lanes=lanes,
        )

    def _emergency_state(self) -> EmergencyState:
        candidates = [
            self.vehicles[vid] for vid in self._active_emergencies
            if vid in self.vehicles and self.vehicles[vid].pos > -self.geo.box
        ]
        if not candidates:
            return EmergencyState(active=False, cleared_this_episode=self._emergency_cleared)
        veh = min(candidates, key=lambda v: v.pos)
        return EmergencyState(
            active=True, vehicle_id=veh.id, type=veh.vtype, approach=veh.approach,
            distance_m=round(max(veh.pos, 0.0), 1), speed_mps=round(veh.speed, 2),
            eta_s=round(max(veh.pos, 0.0) / max(veh.speed, 1.0), 1),
            cleared_this_episode=self._emergency_cleared,
        )

    def _veh_snapshot(self, v: Vehicle) -> VehicleSnapshot:
        x, y, heading = self.geo.world_pose(v.approach, v.lane, v.movement, v.pos)
        return VehicleSnapshot(
            id=v.id, type=v.vtype, approach=v.approach, lane=v.lane, movement=v.movement.value,
            x=round(x, 2), y=round(y, 2), heading=round(heading, 3),
            speed_mps=round(v.speed, 2), accel_mps2=round(v.accel, 2),
            wait_s=round(v.wait_s, 1), stops=v.stops,
            fuel_l=round(v.fuel_l, 5), co2_kg=round(v.co2_kg, 5),
            is_emergency=v.is_emergency, is_violator=v.is_violator and v.violation_recorded,
            state=v.state,
        )

    # ------------------------------------------------------------------ misc
    def drain_events(self) -> list[dict[str, Any]]:
        out, self._events = self._events, []
        return out

    def _emit(self, category: str, severity: str, description: str, **meta: Any) -> None:
        self._events.append({
            "t": round(self._t, 2), "category": category, "severity": severity,
            "description": description, "meta": meta,
        })

    @property
    def sim_time(self) -> float:
        return self._t

    # -- internal accessors used by MetricsAggregator -------------------------
    def completed_trips(self) -> list[dict[str, float]]:
        return self._completed

    def emergency_trips(self) -> list[dict[str, float]]:
        return self._emergency_trips

    def throughput_vph(self) -> float:
        return len(self._departures) / _WINDOW_S * 3600.0

    def violation_totals(self) -> tuple[int, int]:
        return self._red_light_total, self._other_violation_total
