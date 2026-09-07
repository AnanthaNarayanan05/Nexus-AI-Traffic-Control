"""MetricsAggregator - rolling + episode snapshots from real simulation data.

The aggregator is the only place traffic/environmental/emergency/safety numbers are
assembled for the UI and for persistence. It reads completed-trip records and event
counters straight off the adapter; it never fabricates or extrapolates (spec section 84).

`idle_time_s` is reported as the low-speed time accumulator the simulation already
tracks per vehicle (docs/metrics.md, docs/limitations.md).
"""

from __future__ import annotations

import statistics
from collections import deque
from typing import Any, Protocol

from app.schemas.metrics import (
    DevMetrics,
    EmergencyMetrics,
    EnvironmentalMetrics,
    MetricSnapshot,
    SafetyMetrics,
    TrafficMetrics,
)
from app.schemas.simulation import SimulationState

_ROLLING_TRIP_WINDOW_S = 60.0


class _Adapter(Protocol):
    def completed_trips(self) -> list[dict[str, float]]: ...
    def emergency_trips(self) -> list[dict[str, float]]: ...
    def throughput_vph(self) -> float: ...
    def violation_totals(self) -> tuple[int, int]: ...


def _mean(xs: list[float]) -> float:
    return float(sum(xs) / len(xs)) if xs else 0.0


class MetricsAggregator:
    def __init__(self, adapter: _Adapter) -> None:
        self._adapter = adapter
        self._seen_trips = 0
        self._rolling_trips: deque[tuple[float, dict[str, float]]] = deque()
        self._dev = DevMetrics()
        self._history: deque[dict[str, Any]] = deque(maxlen=2000)

    # ------------------------------------------------------------------ ingest
    def _ingest(self, sim_time: float) -> None:
        trips = self._adapter.completed_trips()
        if len(trips) < self._seen_trips:  # adapter trimmed its buffer
            self._seen_trips = 0
            self._rolling_trips.clear()
        for record in trips[self._seen_trips:]:
            self._rolling_trips.append((sim_time, record))
        self._seen_trips = len(trips)
        lo = sim_time - _ROLLING_TRIP_WINDOW_S
        while self._rolling_trips and self._rolling_trips[0][0] < lo:
            self._rolling_trips.popleft()

    # ------------------------------------------------------------------ dev metrics
    def record_dev(self, **kw: float) -> None:
        self._dev = self._dev.model_copy(update={k: float(v) for k, v in kw.items()})

    def dev_metrics(self) -> DevMetrics:
        return self._dev

    # ------------------------------------------------------------------ snapshots
    def rolling(self, state: SimulationState, *, unsafe_transitions: int = 0,
                include_dev: bool = False) -> MetricSnapshot:
        self._ingest(state.sim_time)
        recent = [r for _, r in self._rolling_trips]
        snap = self._assemble(state, recent, "rolling", unsafe_transitions, include_dev)
        self._history.append({"t": round(state.sim_time, 1), **snap.flat()})
        return snap

    def episode(self, state: SimulationState, *, unsafe_transitions: int = 0) -> MetricSnapshot:
        all_trips = list(self._adapter.completed_trips())
        return self._assemble(state, all_trips, "episode", unsafe_transitions, include_dev=False)

    def history(self, window: int | None = None) -> list[dict[str, Any]]:
        items = list(self._history)
        return items[-window:] if window else items

    def reset(self) -> None:
        self._seen_trips = 0
        self._rolling_trips.clear()
        self._history.clear()
        self._dev = DevMetrics()

    # ------------------------------------------------------------------ internals
    def _assemble(self, state: SimulationState, trips: list[dict[str, float]], window: str,
                  unsafe_transitions: int, include_dev: bool) -> MetricSnapshot:
        present = state.vehicles
        approaches = list(state.approaches.values())

        traffic = TrafficMetrics(
            avg_waiting_s=round(_mean([v.wait_s for v in present]), 2),
            avg_queue=round(_mean([float(a.queue_length) for a in approaches]), 2),
            throughput_vph=round(self._adapter.throughput_vph(), 1),
            avg_travel_time_s=round(_mean([t["travel_time"] for t in trips]), 2),
            avg_speed_mps=round(_mean([v.speed_mps for v in present]), 2),
            stops_per_veh=round(_mean([float(t["stops"]) for t in trips]), 3),
            idle_time_s=round(_mean([t["wait"] for t in trips]), 2),
        )

        env_trips = trips
        environmental = EnvironmentalMetrics(
            fuel_l_per_veh=round(_mean([t["fuel"] for t in env_trips]), 5),
            co2_kg_per_veh=round(_mean([t["co2"] for t in env_trips]), 5),
            fuel_l_total=round(state.estimates.fuel_l_total, 4),
            co2_kg_total=round(state.estimates.co2_kg_total, 4),
        )

        etrips = self._adapter.emergency_trips()
        emergency = EmergencyMetrics(
            emergency_wait_s=round(_mean([t["wait"] for t in etrips]), 2),
            emergency_travel_time_s=round(_mean([t["travel_time"] for t in etrips]), 2),
            emergency_delay_s=round(_mean([t["delay"] for t in etrips]), 2),
            emergency_cleared=state.emergency.cleared_this_episode,
        )

        red, other = self._adapter.violation_totals()
        safety = SafetyMetrics(
            red_light_violations=red,
            other_violations=other,
            unsafe_transitions=unsafe_transitions,
        )

        return MetricSnapshot(
            sim_time=round(state.sim_time, 2), window=window,
            traffic=traffic, environmental=environmental,
            emergency=emergency, safety=safety,
            dev=(self._dev if include_dev else None),
        )


def summarise_series(values: list[float], confidence_level: float = 0.95) -> dict[str, float]:
    """mean / median / std / min / max / CI half-width (spec section 53, docs/metrics.md).

    CI uses Student-t for n < 30 when scipy is available, else the normal approximation.
    Returns ``ci_half_width = 0.0`` when n < 2 (no spread can be estimated).
    """
    n = len(values)
    if n == 0:
        return {"n": 0, "mean": 0.0, "median": 0.0, "std": 0.0, "min": 0.0, "max": 0.0,
                "ci_half_width": 0.0}
    mean = statistics.fmean(values)
    median = statistics.median(values)
    if n < 2:
        return {"n": n, "mean": mean, "median": median, "std": 0.0,
                "min": min(values), "max": max(values), "ci_half_width": 0.0}
    std = statistics.stdev(values)
    sem = std / (n ** 0.5)
    try:
        from scipy import stats  # type: ignore

        crit = float(stats.t.ppf(0.5 + confidence_level / 2.0, df=n - 1))
    except Exception:  # noqa: BLE001 - scipy optional
        crit = 1.959963984540054  # normal approx for 95%
    return {"n": n, "mean": mean, "median": median, "std": std,
            "min": min(values), "max": max(values), "ci_half_width": crit * sem}
