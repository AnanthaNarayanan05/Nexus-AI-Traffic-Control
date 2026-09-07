"""Vehicle model + longitudinal dynamics (spec section 11, docs/simulation.md section 4)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.core.config import get_config
from app.schemas.enums import Approach, Movement, SignalColor, VehicleType

# IDM-lite parameters
_A_MAX = 2.6          # m/s^2 comfortable acceleration
_B_COMF = 3.5         # m/s^2 comfortable deceleration
_B_MAX = 7.0          # m/s^2 emergency deceleration
_DELTA = 4.0
_T_HEADWAY = 1.4      # s desired time headway
_S0 = 2.0             # m minimum standstill gap

# Stop / idle detection band. A vehicle is "standing" below _STOP_SPEED_MPS and is
# only considered released once it exceeds _RELEASE_SPEED_MPS, so one queue-and-go
# counts as exactly one stop however gradually it decelerates.
_STOP_SPEED_MPS = 0.3
_RELEASE_SPEED_MPS = 1.2

_TYPE_SPEED_MULT = {
    VehicleType.CAR: 1.0, VehicleType.SUV: 0.98, VehicleType.BUS: 0.85,
    VehicleType.TRUCK: 0.82, VehicleType.AMBULANCE: 1.15,
    VehicleType.FIRE_TRUCK: 1.05, VehicleType.POLICE: 1.2,
}


@dataclass
class Vehicle:
    id: str
    vtype: VehicleType
    approach: Approach
    lane: int
    movement: Movement
    pos: float                      # distance to stop line (see geometry.py)
    speed: float = 0.0
    accel: float = 0.0
    entered_t: float = 0.0
    wait_s: float = 0.0
    stops: int = 0
    fuel_l: float = 0.0
    co2_kg: float = 0.0
    is_violator: bool = False       # will disregard a red phantom (spec section 24)
    violation_recorded: bool = False
    crossed_stop_line: bool = False
    departed_t: float | None = None

    _prev_speed: float = field(default=0.0, repr=False)
    _standing: bool = field(default=False, repr=False)

    def __post_init__(self) -> None:
        # A vehicle that enters at rest is already standing, so its release is not
        # counted as a stop. Only a *later* return to standstill is a real stop.
        self._standing = self.speed < _STOP_SPEED_MPS
        self._prev_speed = self.speed

    # -- properties -----------------------------------------------------------
    @property
    def is_emergency(self) -> bool:
        return self.vtype.is_emergency

    @property
    def desired_speed(self) -> float:
        ff = get_config().geometry.free_flow_speed_kmh / 3.6
        return ff * _TYPE_SPEED_MULT.get(self.vtype, 1.0)

    @property
    def state(self) -> str:
        if self.departed_t is not None:
            return "departed"
        if -34.0 < self.pos <= 0.0:
            return "crossing"
        if self.pos > 0.0 and self.speed < _RELEASE_SPEED_MPS:
            return "queued"
        return "driving"

    # -- dynamics -----------------------------------------------------------
    def idm_accel(self, gap: float | None, leader_speed: float) -> float:
        """IDM acceleration given the gap to the effective leader (m) and its speed."""
        v = self.speed
        v0 = self.desired_speed
        a_max = _A_MAX * (1.35 if self.is_emergency else 1.0)
        free = a_max * (1.0 - (v / v0) ** _DELTA) if v0 > 0 else 0.0
        if gap is None:
            return free
        gap = max(gap, 0.05)
        dv = v - leader_speed
        t_head = _T_HEADWAY * (0.6 if self.is_emergency else 1.0)
        s_star = _S0 + max(0.0, v * t_head + (v * dv) / (2.0 * math.sqrt(a_max * _B_COMF)))
        interaction = a_max * (s_star / gap) ** 2
        return free - interaction

    def integrate(self, accel: float, dt: float, now: float) -> None:
        accel = max(-_B_MAX, min(_A_MAX * 1.4, accel))
        self.accel = accel
        self._prev_speed = self.speed
        self.speed = max(0.0, self.speed + accel * dt)
        self.pos -= self.speed * dt

        # waiting + stop counting (hysteresis band, see _STOP_SPEED_MPS above)
        if self.speed < _STOP_SPEED_MPS:
            self.wait_s += dt
            if not self._standing:
                self.stops += 1
                self._standing = True
        elif self.speed > _RELEASE_SPEED_MPS:
            self._standing = False

        self._accrue_fuel(dt)

    def _accrue_fuel(self, dt: float) -> None:
        f = get_config().fuel
        em = get_config().emissions
        mult = float(f.type_multiplier.get(self.vtype.value, 1.0))
        litres = 0.0
        if self.speed < _STOP_SPEED_MPS:
            litres += float(f.idle_l_per_s) * dt
        litres += float(f.cruise_l_per_m) * self.speed * dt
        if self.accel > 0:
            litres += float(f.accel_l_per_ms2_s) * self.accel * dt
        litres *= mult
        self.fuel_l += litres
        self.co2_kg += litres * float(em.co2_kg_per_litre)

    def register_stop_fuel(self) -> None:
        f = get_config().fuel
        em = get_config().emissions
        mult = float(f.type_multiplier.get(self.vtype.value, 1.0))
        litres = float(f.per_stop_l) * mult
        self.fuel_l += litres
        self.co2_kg += litres * float(em.co2_kg_per_litre)
