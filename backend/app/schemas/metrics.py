"""Metric snapshot contract (spec sections 38-39, 52; docs/metrics.md)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TrafficMetrics(BaseModel):
    avg_waiting_s: float = 0.0
    avg_queue: float = 0.0
    throughput_vph: float = 0.0
    avg_travel_time_s: float = 0.0
    avg_speed_mps: float = 0.0
    stops_per_veh: float = 0.0
    idle_time_s: float = 0.0


class EnvironmentalMetrics(BaseModel):
    """ESTIMATED - parametric model, not measured (docs/assumptions.md A12-A13)."""

    fuel_l_per_veh: float = 0.0
    co2_kg_per_veh: float = 0.0
    fuel_l_total: float = 0.0
    co2_kg_total: float = 0.0


class EmergencyMetrics(BaseModel):
    emergency_wait_s: float = 0.0
    emergency_travel_time_s: float = 0.0
    emergency_delay_s: float = 0.0
    emergency_cleared: int = 0


class SafetyMetrics(BaseModel):
    red_light_violations: int = 0
    other_violations: int = 0
    unsafe_transitions: int = 0


class DevMetrics(BaseModel):
    fps: float = 0.0
    frame_time_ms: float = 0.0
    ai_latency_ms: float = 0.0
    sim_step_ms: float = 0.0
    ws_latency_ms: float = 0.0
    memory_mb: float = 0.0


class MetricSnapshot(BaseModel):
    sim_time: float = 0.0
    window: str = "rolling"  # rolling | episode
    traffic: TrafficMetrics = Field(default_factory=TrafficMetrics)
    environmental: EnvironmentalMetrics = Field(default_factory=EnvironmentalMetrics)
    emergency: EmergencyMetrics = Field(default_factory=EmergencyMetrics)
    safety: SafetyMetrics = Field(default_factory=SafetyMetrics)
    dev: DevMetrics | None = None

    def flat(self) -> dict[str, float]:
        """Flatten to family.metric -> value for persistence / CSV."""
        out: dict[str, float] = {}
        for family in ("traffic", "environmental", "emergency", "safety"):
            for k, v in getattr(self, family).model_dump().items():
                out[f"{family}.{k}"] = float(v)
        return out
