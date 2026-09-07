"""Intersection geometry + world-pose computation for rendering (docs/simulation.md section 2).

Coordinate frame: origin at intersection centre, +x East, +y North, metres.
A vehicle's longitudinal position ``pos`` is the signed distance to its stop line:
  pos > 0   : on the approach, still upstream of the stop line
  pos == 0  : at the stop line
  pos < 0   : inside the intersection box / on the exit road
``pos`` is monotonically decreasing along the whole entry->cross->exit path, so
car-following works uniformly in every regime.
"""

from __future__ import annotations

import functools
import math

from app.core.config import get_config
from app.schemas.enums import Approach, Movement

Vec = tuple[float, float]


def _rot_ccw(v: Vec) -> Vec:
    return (-v[1], v[0])


def _rot_cw(v: Vec) -> Vec:
    return (v[1], -v[0])


def _add(a: Vec, b: Vec) -> Vec:
    return (a[0] + b[0], a[1] + b[1])


def _scale(a: Vec, k: float) -> Vec:
    return (a[0] * k, a[1] * k)


def _sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1])


def _norm(a: Vec) -> float:
    return math.hypot(a[0], a[1])


# incoming travel direction for each approach
APPROACH_DIR: dict[Approach, Vec] = {
    Approach.N: (0.0, -1.0),  # comes from the north, travels south
    Approach.S: (0.0, 1.0),
    Approach.E: (-1.0, 0.0),
    Approach.W: (1.0, 0.0),
}


def _lane_offset_dir(a: Approach) -> Vec:
    # right-hand traffic: incoming lanes sit on the right of the road centreline
    return _rot_cw(APPROACH_DIR[a])


def exit_dir(a: Approach, movement: Movement) -> Vec:
    d = APPROACH_DIR[a]
    if movement == Movement.THROUGH:
        return d
    if movement == Movement.LEFT:
        return _rot_ccw(d)
    return _rot_cw(d)


def destination_approach(a: Approach, movement: Movement) -> Approach:
    e = exit_dir(a, movement)
    for approach, direction in APPROACH_DIR.items():
        if math.isclose(direction[0], e[0]) and math.isclose(direction[1], e[1]):
            # the outgoing road whose *incoming* dir equals e is the opposite label
            return approach.opposite
    return a.opposite


class Geometry:
    """Resolved, cached geometry derived from ``config.yaml -> geometry``."""

    def __init__(self) -> None:
        g = get_config().geometry
        self.approach_length: float = float(g.approach_length_m)
        self.lanes: int = int(g.lanes_per_approach)
        self.box: float = float(g.intersection_size_m)
        self.stop_offset: float = float(g.stop_line_offset_m)
        self.lane_width: float = float(g.lane_width_m)
        self.vehicle_length: float = float(g.vehicle_length_m)
        self.min_gap: float = float(g.min_gap_m)
        self.free_flow_mps: float = float(g.free_flow_speed_kmh) / 3.6
        self.stop_line_dist: float = self.box / 2.0 + self.stop_offset
        self.exit_length: float = self.approach_length - self.stop_line_dist

    # -- lane geometry ----------------------------------------------------------
    def lane_center_offset(self, a: Approach, lane: int) -> Vec:
        off_dir = _lane_offset_dir(a)
        return _scale(off_dir, (lane + 0.5) * self.lane_width)

    def entry_point(self, a: Approach, lane: int) -> Vec:
        d = APPROACH_DIR[a]
        base = _scale(d, -(self.stop_line_dist + self.approach_length))
        return _add(base, self.lane_center_offset(a, lane))

    def stop_line_point(self, a: Approach, lane: int) -> Vec:
        d = APPROACH_DIR[a]
        return _add(_scale(d, -self.stop_line_dist), self.lane_center_offset(a, lane))

    def _exit_lane(self, a: Approach, movement: Movement) -> int:
        if movement == Movement.LEFT:
            return 0
        if movement == Movement.RIGHT:
            return self.lanes - 1
        return 1 if self.lanes >= 2 else 0

    def exit_point(self, a: Approach, movement: Movement) -> Vec:
        dest = destination_approach(a, movement)
        e = exit_dir(a, movement)
        lane = self._exit_lane(a, movement)
        off = _scale(_rot_cw(e), (lane + 0.5) * self.lane_width)
        return _add(_scale(e, self.stop_line_dist), off)

    @functools.lru_cache(maxsize=256)
    def _cross_path(self, a: Approach, lane: int, movement: Movement) -> tuple[Vec, Vec, Vec, float]:
        p0 = self.stop_line_point(a, lane)
        p2 = self.exit_point(a, movement)
        d = APPROACH_DIR[a]
        e = exit_dir(a, movement)
        if movement == Movement.THROUGH:
            p1 = _scale(_add(p0, p2), 0.5)
        else:
            p1 = _line_intersection(p0, d, p2, e) or _scale(_add(p0, p2), 0.5)
        # approximate arc length
        length = 0.0
        prev = p0
        for i in range(1, 17):
            cur = _bezier(p0, p1, p2, i / 16.0)
            length += _norm(_sub(cur, prev))
            prev = cur
        return p0, p1, p2, length

    def cross_length(self, a: Approach, lane: int, movement: Movement) -> float:
        return self._cross_path(a, lane, movement)[3]

    def total_path_length(self, a: Approach, lane: int, movement: Movement) -> float:
        return self.approach_length + self.cross_length(a, lane, movement) + self.exit_length

    def world_pose(self, a: Approach, lane: int, movement: Movement, pos: float) -> tuple[float, float, float]:
        """Return (x, y, heading_radians) for a vehicle at longitudinal position ``pos``."""
        d = APPROACH_DIR[a]
        if pos >= 0.0:
            point = _add(_scale(d, -(self.stop_line_dist + pos)), self.lane_center_offset(a, lane))
            return point[0], point[1], math.atan2(d[1], d[0])

        p0, p1, p2, clen = self._cross_path(a, lane, movement)
        if -pos <= clen:
            t = min(1.0, max(0.0, (-pos) / clen)) if clen > 1e-6 else 1.0
            point = _bezier(p0, p1, p2, t)
            deriv = _bezier_deriv(p0, p1, p2, t)
            return point[0], point[1], math.atan2(deriv[1], deriv[0])

        e = exit_dir(a, movement)
        dd = (-pos) - clen
        point = _add(p2, _scale(e, dd))
        return point[0], point[1], math.atan2(e[1], e[0])


def _bezier(p0: Vec, p1: Vec, p2: Vec, t: float) -> Vec:
    u = 1.0 - t
    x = u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0]
    y = u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]
    return (x, y)


def _bezier_deriv(p0: Vec, p1: Vec, p2: Vec, t: float) -> Vec:
    u = 1.0 - t
    x = 2 * u * (p1[0] - p0[0]) + 2 * t * (p2[0] - p1[0])
    y = 2 * u * (p1[1] - p0[1]) + 2 * t * (p2[1] - p1[1])
    n = math.hypot(x, y) or 1.0
    return (x / n, y / n)


def _line_intersection(p: Vec, dp: Vec, q: Vec, dq: Vec) -> Vec | None:
    # p + s*dp == q + u*dq
    denom = dp[0] * (-dq[1]) - dp[1] * (-dq[0])
    if abs(denom) < 1e-9:
        return None
    rhs = _sub(q, p)
    s = (rhs[0] * (-dq[1]) - rhs[1] * (-dq[0])) / denom
    return _add(p, _scale(dp, s))


@functools.lru_cache(maxsize=1)
def get_geometry() -> Geometry:
    return Geometry()
