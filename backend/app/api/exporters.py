"""Serialisers for the export surface (spec §23, §64-79; docs/exports.md).

Turn a stored experiment or replay record into a downloadable CSV or JSON blob. These
are pure functions over the dict the persistence layer already returns - no new
measurement, nothing synthesised (spec §84). JSON is the whole record (every per-episode
/ per-decision number included); CSV is the flat, analysis-ready view.
"""

from __future__ import annotations

import csv
import io
import json
import re

EXPORT_FORMATS = ("csv", "json")

_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9_-]+")


def safe_filename(stem: str, suffix: str) -> str:
    """A download filename stem restricted to ``[A-Za-z0-9_-]`` (spec §88) - no dots or
    separators, so nothing in a caller-supplied id can walk a path or spoof an extension."""
    clean = _UNSAFE_FILENAME.sub("-", stem).strip("-") or "export"
    return f"{clean}.{suffix}"


def to_json(record: dict) -> str:
    return json.dumps(record, indent=2, default=str)


def _rows_to_csv(rows: list[dict], fieldnames: list[str]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


# --------------------------------------------------------------------- experiments
_SUMMARY_KEYS = ("n", "mean", "median", "std", "min", "max", "ci_half_width")

_EXPERIMENT_FIELDS = [
    "experiment_id", "scenario", "metric", "family", "lower_is_better",
    "controller", "label", "model_mode", "model_version", "is_baseline",
    *_SUMMARY_KEYS,
    "improvement_pct_vs_baseline",
]


def experiment_rows(record: dict) -> list[dict]:
    """One tidy row per (metric, controller): the full ``summarise_series`` stats plus
    the honest improvement % vs the baseline taken straight from the comparison blob."""
    results = record.get("results") or []
    comparison = record.get("comparison") or {}
    metric_blob = comparison.get("metrics") or {}
    baseline = comparison.get("baseline")
    eid = record.get("id", "")
    scenario = record.get("scenario", "")

    rows: list[dict] = []
    for res in results:
        label = res.get("label") or res.get("controller") or "?"
        for metric, agg in (res.get("aggregates") or {}).items():
            values = metric_blob.get(metric, {}).get("values", {}).get(label, {})
            row = {
                "experiment_id": eid,
                "scenario": scenario,
                "metric": metric,
                "family": metric.split(".", 1)[0] if "." in metric else "",
                "lower_is_better": metric_blob.get(metric, {}).get("lower_is_better"),
                "controller": res.get("controller", ""),
                "label": label,
                "model_mode": res.get("model_mode", ""),
                "model_version": res.get("model_version") or "",
                "is_baseline": label == baseline,
                "improvement_pct_vs_baseline": values.get("improvement_pct_vs_baseline"),
            }
            for key in _SUMMARY_KEYS:
                row[key] = agg.get(key)
            rows.append(row)
    return rows


def experiment_csv(record: dict) -> str:
    return _rows_to_csv(experiment_rows(record), _EXPERIMENT_FIELDS)


# --------------------------------------------------------------------- replays
_REPLAY_BASE_FIELDS = [
    "replay_id", "index", "t", "step",
    "candidate_phase", "winner", "basis", "applied_phase", "safety_changed_phase",
    "safety_action", "safety_approved", "violated_rules",
]
# family.metric columns, in MetricSnapshot order (app/schemas/metrics.py)
_REPLAY_METRIC_FIELDS = [
    "traffic.avg_waiting_s", "traffic.avg_queue", "traffic.throughput_vph",
    "traffic.avg_travel_time_s", "traffic.avg_speed_mps", "traffic.stops_per_veh",
    "traffic.idle_time_s",
    "environmental.fuel_l_per_veh", "environmental.co2_kg_per_veh",
    "environmental.fuel_l_total", "environmental.co2_kg_total",
    "emergency.emergency_wait_s", "emergency.emergency_travel_time_s",
    "emergency.emergency_delay_s", "emergency.emergency_cleared",
    "safety.red_light_violations", "safety.other_violations", "safety.unsafe_transitions",
]


def _flatten_metrics(metrics: dict | None) -> dict:
    out: dict[str, float] = {}
    for family in ("traffic", "environmental", "emergency", "safety"):
        for key, value in (metrics or {}).get(family, {}).items():
            out[f"{family}.{key}"] = value
    return out


def _replay_agents(timeline: list[dict]) -> list[str]:
    return sorted({a for frame in timeline for a in (frame.get("rewards") or {})})


def replay_rows(record: dict) -> list[dict]:
    """One row per decision frame: coordinator candidate -> authoritative applied phase,
    the safety verdict, each agent's total reward, and the metric snapshot at that point."""
    timeline = record.get("timeline") or []
    rid = record.get("id", "")
    agents = _replay_agents(timeline)

    rows: list[dict] = []
    for i, frame in enumerate(timeline):
        coord = frame.get("coordination") or {}
        safety = frame.get("safety") or {}
        rewards = frame.get("rewards") or {}
        candidate = coord.get("candidate_phase")
        applied = frame.get("applied_phase")
        row = {
            "replay_id": rid,
            "index": i,
            "t": frame.get("t"),
            "step": frame.get("step"),
            "candidate_phase": candidate,
            "winner": coord.get("winner"),
            "basis": coord.get("basis"),
            "applied_phase": applied,
            "safety_changed_phase": applied != candidate,
            "safety_action": safety.get("action_taken"),
            "safety_approved": safety.get("approved"),
            "violated_rules": ";".join(safety.get("violated_rules") or []),
        }
        for agent in agents:
            row[f"reward.{agent}"] = rewards.get(agent)
        row.update(_flatten_metrics(frame.get("metrics")))
        rows.append(row)
    return rows


def replay_csv(record: dict) -> str:
    timeline = record.get("timeline") or []
    fieldnames = [
        *_REPLAY_BASE_FIELDS,
        *(f"reward.{agent}" for agent in _replay_agents(timeline)),
        *_REPLAY_METRIC_FIELDS,
    ]
    return _rows_to_csv(replay_rows(record), fieldnames)
